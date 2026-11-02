"""가동률 계산.

- 가용시간 = 연간 기준시간 × (기간 일수 / 해당 연도 일수). 도입일 이전·불용일 이후는 제외.
- 사용시간은 실적의 사용기간에 하루 단위로 고르게 나눠 담습니다. 휴무일자포함이 'N'이면
  주말·공휴일을 빼고 나눕니다. 그래서 월을 걸친 실적도 주·월 단위로 정확히 잘립니다.
"""
from __future__ import annotations

import calendar
import datetime as dt

import pandas as pd
import streamlit as st

from core.db import to_date, to_num

try:
    import holidays as _holidays
except ImportError:  # 패키지가 없으면 주말만 제외
    _holidays = None

PERIOD_KINDS = ["주", "월", "분기", "반기", "연"]
TREND_COUNT = {"주": 12, "월": 12, "분기": 8, "반기": 6, "연": 5}


def _month_end(y: int, m: int) -> dt.date:
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def period_bounds(kind: str, ref: dt.date) -> tuple[dt.date, dt.date, str]:
    y, m = ref.year, ref.month
    if kind == "주":
        s = ref - dt.timedelta(days=ref.weekday())
        e = s + dt.timedelta(days=6)
        iso = ref.isocalendar()
        return s, e, f"{iso[0]}년 {iso[1]}주 ({s:%m/%d}~{e:%m/%d})"
    if kind == "월":
        return dt.date(y, m, 1), _month_end(y, m), f"{y}년 {m}월"
    if kind == "분기":
        q = (m - 1) // 3
        return dt.date(y, q * 3 + 1, 1), _month_end(y, q * 3 + 3), f"{y}년 {q + 1}분기"
    if kind == "반기":
        h = 0 if m <= 6 else 1
        return dt.date(y, h * 6 + 1, 1), _month_end(y, h * 6 + 6), f"{y}년 {'상' if h == 0 else '하'}반기"
    return dt.date(y, 1, 1), dt.date(y, 12, 31), f"{y}년"


def short_label(kind: str, s: dt.date) -> str:
    if kind == "주":
        return f"{s:%m/%d}주"
    if kind == "월":
        return f"{s:%y}.{s.month:02d}"
    if kind == "분기":
        return f"{s:%y}년 {(s.month - 1) // 3 + 1}Q"
    if kind == "반기":
        return f"{s:%y}년 {'상' if s.month <= 6 else '하'}반기"
    return f"{s.year}년"


def year_fraction(s: dt.date, e: dt.date) -> float:
    """s~e(양 끝 포함)가 몇 '년'에 해당하는지. 윤년은 366일로 나눔."""
    total, cur = 0.0, s
    while cur <= e:
        seg_end = min(e, dt.date(cur.year, 12, 31))
        days_in_year = 366 if calendar.isleap(cur.year) else 365
        total += ((seg_end - cur).days + 1) / days_in_year
        cur = seg_end + dt.timedelta(days=1)
    return total


def kr_holidays(years) -> set[dt.date]:
    if _holidays is None:
        return set()
    try:
        return set(_holidays.country_holidays("KR", years=sorted(years)).keys())
    except Exception:
        return set()


@st.cache_data(ttl=30)
def expand_daily(logs: pd.DataFrame, mode: str = "spread") -> pd.DataFrame:
    cols = ["log_id", "equip_id", "day", "hours", "fee"]
    if logs.empty:
        return pd.DataFrame(columns=cols).astype({"day": "datetime64[ns]", "hours": float, "fee": float})
    years = set()
    for s, e in zip(logs["start_date"].dropna(), logs["end_date"].dropna()):
        years.update(range(s.year, e.year + 1))
    hol = kr_holidays(years)
    recs = []
    for r in logs.itertuples(index=False):
        s, e = to_date(r.start_date), to_date(r.end_date)
        if s is None:
            continue
        if e is None or e < s:
            e = s
        if mode == "start":
            days = [s]
        else:
            days = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
            if r.include_holidays == "N":
                work = [d for d in days if d.weekday() < 5 and d not in hol]
                if work:
                    days = work
        n = len(days)
        h, f = to_num(r.hours, 0.0), to_num(r.fee, 0.0)
        for d in days:
            recs.append((r.id, r.equip_id, d, h / n, f / n))
    df = pd.DataFrame(recs, columns=cols)
    df["day"] = pd.to_datetime(df["day"])
    return df


def window(daily: pd.DataFrame, s: dt.date, e: dt.date) -> pd.DataFrame:
    return daily[(daily["day"] >= pd.Timestamp(s)) & (daily["day"] <= pd.Timestamp(e))]


def effective_end(s: dt.date, e: dt.date, cutoff: dt.date | None) -> dt.date:
    """진행 중인 기간이면 오늘까지만 계산."""
    if cutoff and s <= cutoff < e:
        return cutoff
    return e


def same_progress_end(s: dt.date, e_eff: dt.date, e: dt.date, ps: dt.date, pe: dt.date) -> dt.date:
    """진행 중인 기간(s~e 중 e_eff까지)과 같은 만큼 진행된 직전 기간의 끝날.

    예: 4분기를 11/02까지 봤다면 3분기는 08/02까지 (기간 시작부터 같은 날수, 직전 기간 길이를 넘지 않음).
    """
    if e_eff >= e:
        return pe
    return min(pe, ps + (e_eff - s))


def shift_year(d: dt.date, n: int) -> dt.date:
    """n년 앞/뒤 같은 날 (2/29는 2/28로)."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def compare_period(kind: str, s: dt.date, e: dt.date, e_eff: dt.date, mode: str = "직전") -> tuple[dt.date, dt.date, str]:
    """비교할 기간 (시작, 끝, 이름). mode: '직전' = 바로 앞 기간, '전년' = 1년 전 같은 기간.

    진행 중인 기간이면 비교 기간도 같은 만큼만 자릅니다 (4분기 11/02까지 ↔ 3분기 08/02까지).
    """
    if mode == "전년":
        ps, pe = shift_year(s, -1), shift_year(e_eff, -1)
        return ps, pe, f"전년 같은 기간({ps:%y.%m.%d}~{pe:%m/%d})"
    ps, pe, label = period_bounds(kind if kind in PERIOD_KINDS else "월", s - dt.timedelta(days=1))
    if kind not in PERIOD_KINDS:  # 직접 지정: 같은 길이만큼 바로 앞
        length = e - s
        ps, pe = s - length - dt.timedelta(days=1), s - dt.timedelta(days=1)
        label = f"{ps:%m/%d}~{pe:%m/%d}"
    pe_eff = same_progress_end(s, e_eff, e, ps, pe)
    if pe_eff < pe:
        label = f"{label} 같은 기간({ps:%m/%d}~{pe_eff:%m/%d})"
    return ps, pe_eff, label


def group_util(summary: pd.DataFrame, by: str) -> pd.DataFrame:
    """센터·용도 같은 묶음별 사용시간·가용시간·가동률 (산정 대상 장비만)."""
    k = summary[summary["KPI"]] if not summary.empty else summary
    if k.empty:
        return pd.DataFrame(columns=[by, "사용시간", "가용시간", "가동률", "사용료", "대수"])
    g = k.groupby(by).agg(사용시간=("사용시간", "sum"), 가용시간=("가용시간", "sum"), 사용료=("사용료", "sum"),
                          대수=("equip_id", "count")).reset_index()
    g["가동률"] = g["사용시간"] / g["가용시간"].where(g["가용시간"] > 0) * 100
    return g.sort_values("가동률", ascending=False)


def monthly_matrix(daily: pd.DataFrame, equip: pd.DataFrame, end: dt.date, n: int, default_annual: float,
                   cutoff: dt.date | None) -> pd.DataFrame:
    """장비 × 최근 n개월 가동률 표 (행: equip_id, 열: 'yy.mm')."""
    months = []
    cur = dt.date(end.year, end.month, 1)
    for _ in range(n):
        months.append(cur)
        cur = (cur - dt.timedelta(days=1)).replace(day=1)
    out = {}
    for m in reversed(months):
        ms, me, _ = period_bounds("월", m)
        if cutoff and ms > cutoff:
            continue
        me = effective_end(ms, me, cutoff)
        sm = equipment_summary(daily, equip, ms, me, default_annual)
        out[short_label("월", ms)] = sm.set_index("equip_id")["가동률"]
    return pd.DataFrame(out)


def available_hours(eq_row, s: dt.date, e: dt.date, default_annual: float) -> float:
    a, r = to_date(eq_row.acquired_on), to_date(eq_row.retired_on)
    s2 = max(s, a) if a else s
    e2 = min(e, r) if r else e
    if s2 > e2:
        return 0.0
    annual = to_num(eq_row.annual_hours)
    if not annual or annual <= 0:
        annual = default_annual
    return annual * year_fraction(s2, e2)


def equipment_summary(daily: pd.DataFrame, equip: pd.DataFrame, s: dt.date, e: dt.date,
                      default_annual: float) -> pd.DataFrame:
    d = window(daily, s, e)
    g = d.groupby("equip_id").agg(used=("hours", "sum"), fee=("fee", "sum"), cnt=("log_id", "nunique"))
    rows = []
    for r in equip.itertuples(index=False):
        avail = available_hours(r, s, e, default_annual)
        used = float(g["used"].get(r.id, 0.0))
        if avail == 0 and used == 0:
            continue  # 해당 기간에 보유하지 않은 장비
        rows.append({
            "equip_id": r.id,
            "장비명": r.name,
            "장비번호": r.code,
            "센터": getattr(r, "location", "") or "(미입력)",
            "용도": getattr(r, "use", "") or "(미입력)",
            "구분": r.kind,
            "담당자": r.manager,
            "사용시간": used,
            "가용시간": avail,
            "가동률": used / avail * 100 if avail else None,
            "사용료": float(g["fee"].get(r.id, 0.0)),
            "건수": int(g["cnt"].get(r.id, 0)),
            "KPI": bool(r.in_kpi),
        })
    cols = ["equip_id", "장비명", "장비번호", "센터", "용도", "구분", "담당자", "사용시간", "가용시간", "가동률", "사용료", "건수", "KPI"]
    return pd.DataFrame(rows, columns=cols)


def totals(summary: pd.DataFrame) -> dict:
    k = summary[summary["KPI"]] if not summary.empty else summary
    used = float(k["사용시간"].sum()) if not k.empty else 0.0
    avail = float(k["가용시간"].sum()) if not k.empty else 0.0
    return {
        "used": used,
        "avail": avail,
        "util": used / avail * 100 if avail else 0.0,
        "fee": float(summary["사용료"].sum()) if not summary.empty else 0.0,
        "equip_count": int(len(k)),
        "idle_count": int((k["사용시간"] <= 0).sum()) if not k.empty else 0,
    }


def trend(daily: pd.DataFrame, equip: pd.DataFrame, kind: str, ref: dt.date, n: int,
          default_annual: float, cutoff: dt.date | None) -> pd.DataFrame:
    out = []
    s, e, label = period_bounds(kind, ref)
    for _ in range(n):
        e_eff = effective_end(s, e, cutoff)
        if cutoff is None or s <= cutoff:
            t = totals(equipment_summary(daily, equip, s, e_eff, default_annual))
            out.append({"기간": short_label(kind, s), "기간명": label, "시작": s,
                        "사용시간": t["used"], "가용시간": t["avail"], "가동률": t["util"], "사용료": t["fee"]})
        s, e, label = period_bounds(kind, s - dt.timedelta(days=1))
    return pd.DataFrame(out[::-1])


def breakdown(daily: pd.DataFrame, logs: pd.DataFrame, s: dt.date, e: dt.date, by: str) -> pd.DataFrame:
    d = window(daily, s, e).merge(logs[["id", by]], left_on="log_id", right_on="id", how="left")
    if d.empty:
        return pd.DataFrame(columns=[by, "사용시간", "사용료", "건수"])
    d[by] = d[by].replace("", "(미입력)").fillna("(미입력)")
    return (d.groupby(by)
             .agg(사용시간=("hours", "sum"), 사용료=("fee", "sum"), 건수=("log_id", "nunique"))
             .reset_index()
             .sort_values("사용시간", ascending=False))
