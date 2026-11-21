"""장비 가동 현황 (2026-11-21): 어느 장비가 언제 돌고 있는지 한눈에 (예전 '충방전기 현황'을 넓힘).

- 줄 = 장비 목록 순서의 장비 (주장비 아래 세부장비는 들여 씀). 구분은 장비용도(시험·제조·분석), 충방전기는 '시험(충방전)'.
- 막대 = 실적 (달마다 나눠 저장한 기간 실적은 묶음ID로 한 막대). 주말·공휴일에도 시험이 이어지면 막대는 이어서 보이고,
  '휴무일 제외' 실적의 주말·공휴일은 흐리게 (가동률에는 넣지 않음).
- 엑셀의 날짜별 시간 = 가동률(장비 KPI 현황)과 같은 계산 (calc.expand_daily + 충방전기 하루 최대).
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd

from core import calc, db
from core.db import to_date, to_str

CHARGER = "시험(충방전기)"  # views.calendar_entry.CHARGER_GROUP 과 같은 이름
GROUPS = ["시험", CHARGER, "제조", "분석"]
GROUP_LABEL = {"시험": "시험(환경)", CHARGER: "시험(충방전)", "제조": "제조", "분석": "분석"}
PURPOSE_CAT = {"시험": "시험", "생산": "제조", "분석": "분석", "계측": "분석", "교육": "교육", "기타": "지원"}


def window(today: dt.date) -> tuple[dt.date, dt.date]:
    """보는 기간 = 이번 달 1일 ~ 두 달 뒤 말일 (충방전기 현황과 같음)."""
    d0 = today.replace(day=1)
    d1 = (d0 + dt.timedelta(days=95)).replace(day=1) - dt.timedelta(days=1)
    return d0, d1


def device_group(eq: pd.DataFrame, ch: pd.DataFrame | None = None) -> dict[int, str]:
    """장비 ID → 구분 (시험 / 시험(충방전기) / 제조 / 분석 / 기타)."""
    out = {}
    for i, u in zip(eq["id"].astype(int), eq.get("use", pd.Series([""] * len(eq)))):
        u = to_str(u)
        out[i] = "제조" if u in ("생산", "제조") else (u if u in ("시험", "분석") else "기타")
    for i in db.charger_family(eq, ch):  # 충방전기 + 충방전기를 세부장비로 둔 상위 장비
        out[int(i)] = CHARGER
    return out


def bars(logs: pd.DataFrame, w0: dt.date, w1: dt.date) -> pd.DataFrame:
    """보는 기간에 걸친 실적 → 막대 (장비 · 묶음마다 한 줄)."""
    cols = ["equip_id", "key", "start", "end", "company", "purpose", "cat", "skip_off", "staff", "log_ids"]
    if logs.empty:
        return pd.DataFrame(columns=cols)
    lg = logs[logs["start_date"].notna()].copy()
    lg["end_date"] = lg["end_date"].fillna(lg["start_date"])
    lg = lg[(lg["start_date"] <= pd.Timestamp(w1)) & (lg["end_date"] >= pd.Timestamp(w0))]
    if lg.empty:
        return pd.DataFrame(columns=cols)
    ser = lg["series"] if "series" in lg else pd.Series([""] * len(lg), index=lg.index)
    lg["key"] = [to_str(s) or f"#{i}" for s, i in zip(ser, lg["id"])]
    recs = []
    for (eid, key), g in lg.groupby(["equip_id", "key"], sort=False):
        g = g.sort_values("start_date")
        first = g.iloc[0]
        p = to_str(first["purpose"])
        recs.append({"equip_id": int(eid), "key": key, "start": to_date(g["start_date"].min()),
                     "end": to_date(g["end_date"].max()), "company": to_str(first["company"]) or "내부",
                     "purpose": p, "cat": PURPOSE_CAT.get(p, "지원"),
                     "skip_off": all(to_str(v) == "N" for v in g["include_holidays"]),
                     "staff": to_str(first.get("created_by", "")), "log_ids": [int(i) for i in g["id"]]})
    return pd.DataFrame(recs, columns=cols).sort_values(["equip_id", "start"]).reset_index(drop=True)


def kpi_hours(logs: pd.DataFrame, w0: dt.date, w1: dt.date, mode: str = "spread") -> dict[tuple[int, dt.date], float]:
    """(장비ID, 날짜) → 가동률 계산과 같은 시간 (충방전기 하루 최대 · 휴무일 제외 실적의 주말 0)."""
    if logs.empty:
        return {}
    near = logs[(logs["start_date"] <= pd.Timestamp(w1))
                & (logs[["start_date", "end_date"]].max(axis=1) >= pd.Timestamp(w0))]
    if near.empty:
        return {}
    daily = calc.expand_daily(near, mode, db.charger_caps())
    daily = daily[(daily["day"] >= pd.Timestamp(w0)) & (daily["day"] <= pd.Timestamp(w1))]
    g = daily.groupby(["equip_id", "day"])["hours"].sum()
    return {(int(e), d.date()): float(h) for (e, d), h in g.items()}


def rows(eq: pd.DataFrame, groups: dict[int, str], bk: pd.DataFrame, w0: dt.date, w1: dt.date,
         want: str = "전체", center: str = "전체") -> list[dict]:
    """화면·엑셀에 보일 장비 줄 (장비 목록 순서, 구분 → 주장비 묶음; 기간에 실적이 있는 묶음을 위로).

    줄 = 실적을 넣는 맨 아래 장비 + 실적이 직접 붙은 상위 장비 + 그 위 주장비(묶음 머리). 기간에 없던 장비(도입 전·불용)는 뺌.
    """
    if eq.empty:
        return []
    ts0, ts1 = pd.Timestamp(w0), pd.Timestamp(w1)
    act = eq[(eq["retired_on"].isna() | (eq["retired_on"] >= ts0)) & (eq["acquired_on"].isna() | (eq["acquired_on"] <= ts1))]
    cen = db.equip_centers(eq)
    parent = {int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)}
    has_kids = {int(p) for p in act["parent_id"].dropna()}
    with_bars = set(bk["equip_id"].astype(int)) if not bk.empty else set()
    info = {int(r["id"]): r for r in act.to_dict("records")}
    keep = [i for i in info if i not in has_kids or i in with_bars]
    for i in list(keep):  # 세부장비가 보이면 그 위 장비들도 묶음 머리로
        p, seen = parent.get(i), set()
        while p is not None and p in info and p not in seen:
            seen.add(p)
            keep.append(p)
            p = parent.get(p)
    keep = set(keep)
    out = []
    for i in info:  # load_equipment 순서 = 장비 목록 순서
        if i not in keep:
            continue
        g = groups.get(i, "기타")
        if g not in GROUPS or (want != "전체" and g != want):
            continue
        c = cen.get(i, "")
        if center != "전체" and c != center:
            continue
        r = info[i]
        root, p = i, parent.get(i)
        while p is not None and p in info:
            root, p = p, parent.get(p)
        out.append({"id": i, "name": to_str(r["short"]) or to_str(r["name"]), "full": to_str(r["name"]),
                    "depth": int(r.get("depth") or 0), "root": root, "group": g, "center": c,
                    "head": i in has_kids, "own": i in with_bars})
    # 기간에 실적이 있는 묶음(주장비 단위)을 구분 안에서 위로 (2026-11-20 충방전기 현황과 같은 규칙)
    busy_root = {r["root"] for r in out if r["id"] in with_bars}
    order = {g: k for k, g in enumerate(GROUPS)}
    out = [r for _, r in sorted(enumerate(out), key=lambda t: (order[t[1]["group"]], t[1]["root"] not in busy_root, t[0]))]
    return out


def is_off(d: dt.date, hol: set) -> bool:
    return d.weekday() >= 5 or d in hol


def now_next(bs: list[dict], today: dt.date) -> tuple[dict | None, bool]:
    """오늘 돌고 있는 실적 (없으면 다음 예약). (막대, 오늘 진행 중?)"""
    cur = [b for b in bs if b["start"] <= today <= b["end"]]
    if cur:
        return cur[0], True
    nxt = sorted((b for b in bs if b["start"] > today), key=lambda b: b["start"])
    return (nxt[0] if nxt else None), False


# ── 엑셀 ─────────────────────────────────────────────────────────
FILL = {"시험": "FCE4EA", "제조": "DDF7EA", "분석": "E9E4FC", "교육": "FDF0D9", "지원": "DDEFFB"}


def to_excel(rws: list[dict], bk: pd.DataFrame, hours: dict, w0: dt.date, w1: dt.date, today: dt.date,
             title: str, charger_sheet: bytes | None = None) -> bytes:
    """화면과 같은 장비 줄 + 날짜별 시간 (가동률 계산과 같은 값). 주말·공휴일에 이어지는 시험은 0으로 칠해 보임."""
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    hol = calc.kr_holidays({w0.year, w1.year})
    days = [w0 + dt.timedelta(days=k) for k in range((w1 - w0).days + 1)]
    by_eq: dict[int, list[dict]] = {}
    for b in (bk.to_dict("records") if not bk.empty else []):
        by_eq.setdefault(int(b["equip_id"]), []).append(b)

    wb = Workbook()
    ws = wb.active
    ws.title = "장비 가동 현황"
    thin = Side(style="thin", color="BFC7D5")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="E8ECF3")
    off_head = PatternFill("solid", fgColor="F3F4F6")
    grp_fill = PatternFill("solid", fgColor="EEF0FF")
    off_run = PatternFill("solid", fgColor="E5E7EB")
    center = Alignment(horizontal="center", vertical="center")
    WD = "월화수목금토일"

    ws.cell(1, 1, title).font = Font(bold=True, size=13)
    ws.cell(2, 1, f"{today:%Y-%m-%d} 기준 · 칸의 숫자 = 그날 가동시간(h), 가동률 계산과 같음 · "
                  "회색 0 = 주말·공휴일에도 이어지는 시험 (가동률 제외)").font = Font(size=9, color="6B7280")
    fixed = ["구분", "센터", "장비", "업체 (오늘·다음)", "기간", f"{w0.month}~{w1.month}월 합계(h)"]
    nf = len(fixed)
    r0 = 4  # 머리글 3줄: 월 / 일 / 요일
    for j, h in enumerate(fixed, start=1):
        ws.merge_cells(start_row=r0, start_column=j, end_row=r0 + 2, end_column=j)
        c = ws.cell(r0, j, h)
        c.font, c.alignment, c.fill = Font(bold=True), center, head_fill
    col = nf + 1
    for k, d in enumerate(days):
        cc = col + k
        if d.day == 1 or k == 0:
            last = k + sum(1 for x in days[k:] if (x.year, x.month) == (d.year, d.month)) - 1
            ws.merge_cells(start_row=r0, start_column=cc, end_row=r0, end_column=col + last)
            m = ws.cell(r0, cc, f"{d.year}년 {d.month}월")
            m.font, m.alignment, m.fill = Font(bold=True), center, head_fill
        off = is_off(d, hol)
        color = "DC2626" if (d.weekday() == 6 or d in hol) else ("2563EB" if d.weekday() == 5 else "111827")
        for rr, v in ((r0 + 1, d.day), (r0 + 2, WD[d.weekday()])):
            c = ws.cell(rr, cc, v)
            c.font, c.alignment = Font(bold=rr == r0 + 1, color=color, size=9), center
            c.fill = off_head if off else head_fill
        ws.column_dimensions[get_column_letter(cc)].width = 4.2
    for rr in range(r0, r0 + 3):
        for cc in range(1, col + len(days)):
            ws.cell(rr, cc).border = box

    r = r0 + 3
    for x in rws:
        bs = by_eq.get(x["id"], [])
        b, cur = now_next(bs, today)
        name = ("  " * x["depth"] + ("└ " if x["depth"] else "")) + x["name"]
        tot = sum(hours.get((x["id"], d), 0.0) for d in days)
        vals = [GROUP_LABEL.get(x["group"], x["group"]), db.center_short(x["center"]), name,
                (b["company"] + ("" if cur else " (예약)")) if b else "",
                f"{b['start']:%y.%m.%d} ~ {b['end']:%y.%m.%d}" if b else "", round(tot, 1) if bs or tot else None]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(r, j, v)
            c.border = box
            c.alignment = Alignment(horizontal="left" if j == 3 else "center", vertical="center")
            if x["head"]:
                c.fill = grp_fill
                c.font = Font(bold=True)
        for k, d in enumerate(days):
            c = ws.cell(r, col + k)
            c.border, c.alignment = box, center
            run = [bb for bb in bs if bb["start"] <= d <= bb["end"]]
            if not run:
                continue
            h = hours.get((x["id"], d), 0.0)
            c.value = int(h) if float(h).is_integer() else round(h, 1)
            c.number_format = "0.#"
            c.font = Font(size=9, color="9CA3AF" if not h else "111827")
            c.fill = off_run if not h else PatternFill("solid", fgColor=FILL.get(run[0]["cat"], "DDEFFB"))
        r += 1
    for j, wdt in enumerate((11, 9, 34, 18, 18, 10), start=1):
        ws.column_dimensions[get_column_letter(j)].width = wdt
    ws.freeze_panes = ws.cell(r0 + 3, col)

    if charger_sheet:  # 충방전기 챔버 현황표 (예전 '충방전기 장비사용 현황표' 모양)를 두 번째 시트로
        src = load_workbook(io.BytesIO(charger_sheet)).active
        dst = wb.create_sheet("충방전기 챔버")
        for row in src.iter_rows():
            for c in row:
                n = dst.cell(c.row, c.column, c.value)
                if c.has_style:
                    n.font, n.fill, n.border, n.alignment = c.font.copy(), c.fill.copy(), c.border.copy(), c.alignment.copy()
        for k, dim in src.column_dimensions.items():
            dst.column_dimensions[k].width = dim.width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
