"""기간 실적: 며칠~몇 달 도는 시험을 한 번에 입력.

i-Tube 규칙(사용시작일·종료일은 같은 해, 2개월 이내) 때문에 달마다 한 줄씩 나눠 저장하고, 같은 '묶음ID'로 잇습니다.
사용시간 = 하루 사용시간 × 그 달에 센 날수 (주말·공휴일 제외를 고르면 평일만).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core.calc import kr_holidays
from core.db import to_date, to_num, to_str


def count_days(s: dt.date, e: dt.date, skip_off: bool, hol: set | None = None) -> int:
    if e < s:
        return 0
    days = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
    if not skip_off:
        return len(days)
    hol = kr_holidays({s.year, e.year}) if hol is None else hol
    return sum(1 for d in days if d.weekday() < 5 and d not in hol)


def split_period(s: dt.date, e: dt.date, per_day: float, skip_off: bool) -> list[dict]:
    """[{start_date, end_date, hours, days}] 달마다 한 줄 (센 날이 없는 달은 뺌)."""
    if e < s:
        return []
    hol = kr_holidays(set(range(s.year, e.year + 1)))
    out, cur = [], s
    while cur <= e:
        nxt = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        end = min(e, nxt - dt.timedelta(days=1))
        n = count_days(cur, end, skip_off, hol)
        if n:
            out.append({"start_date": cur, "end_date": end, "hours": int(round(per_day * n)), "days": n})
        cur = nxt
    return out


def series_rows(logs: pd.DataFrame, log_id: int) -> pd.DataFrame:
    """이 실적과 같은 묶음의 실적들 (시작일 순). 묶음ID가 없으면 자신만."""
    me = logs[logs["id"] == int(log_id)]
    if me.empty:
        return me
    key = to_str(me.iloc[0].get("series", ""))
    rows = logs[logs["series"].map(to_str) == key] if key and "series" in logs else me
    return rows.sort_values("start_date")


def series_span(rows: pd.DataFrame) -> tuple[dt.date, dt.date]:
    return to_date(rows["start_date"].min()), to_date(rows["end_date"].max())


def per_day_of(rows: pd.DataFrame) -> float:
    """저장된 묶음에서 하루 사용시간을 되짚음."""
    skip = all(to_str(v) == "N" for v in rows.get("include_holidays", pd.Series(["Y"])))
    n = sum(count_days(to_date(a), to_date(b), skip) for a, b in zip(rows["start_date"], rows["end_date"]))
    h = sum(to_num(v, 0) or 0 for v in rows["hours"])
    return round(h / n) if n else 8.0


def is_period(rec) -> bool:
    return to_date(rec["start_date"]) != to_date(rec["end_date"]) or bool(to_str(rec.get("series", "")))


def plan_changes(old: pd.DataFrame, chunks: list[dict], base: dict, series: str) -> tuple[dict, list[dict], list[int]]:
    """고칠 묶음(old)과 새로 나눈 달들(chunks) → (고칠 {id: rec}, 새로 넣을 [rec], 지울 [id]). 같은 달 줄은 고쳐 씀."""
    by_month: dict = {}
    for r in old.to_dict("records"):
        d = to_date(r["start_date"])
        by_month.setdefault((d.year, d.month), []).append(int(r["id"]))
    upd, add = {}, []
    for c in chunks:
        rec = dict(base) | {k: c[k] for k in ("start_date", "end_date", "hours")} | {"series": series}
        ids = by_month.get((c["start_date"].year, c["start_date"].month))
        if ids:
            upd[ids.pop(0)] = rec
        else:
            add.append(rec)
    gone = [i for ids in by_month.values() for i in ids]
    return upd, add, gone
