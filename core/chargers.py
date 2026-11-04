"""충방전기 현황: 챔버마다 누가 언제까지 쓰는지 (예전 '충방전기 장비사용 현황표' 엑셀을 대신함)."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd

from core import seed
from core.db import chamber_ids, to_date, to_str


def bookings(logs: pd.DataFrame) -> pd.DataFrame:
    """챔버를 고른 실적을 예약 단위로 (달마다 나눠 저장한 기간 실적은 한 줄로 합침)."""
    cols = ["key", "chamber_id", "start", "end", "company", "purpose", "overview", "staff", "ch_part", "log_ids"]
    if logs.empty or "chambers" not in logs:
        return pd.DataFrame(columns=cols)
    lg = logs[logs["chambers"].map(to_str) != ""].copy()
    if lg.empty:
        return pd.DataFrame(columns=cols)
    lg["key"] = [to_str(s) or f"#{i}" for s, i in zip(lg.get("series", [""] * len(lg)), lg["id"])]
    recs = []
    for key, g in lg.groupby("key", sort=False):
        first = g.sort_values("start_date").iloc[0]
        ov, _, _ = seed.parse_detail(first.get("detail", ""))
        for cid in chamber_ids(first["chambers"]):
            recs.append({"key": key, "chamber_id": cid, "start": to_date(g["start_date"].min()),
                         "end": to_date(g["end_date"].max()), "company": to_str(first["company"]) or "내부",
                         "purpose": to_str(first["purpose"]), "overview": ov, "staff": to_str(first["created_by"]),
                         "ch_part": to_str(first.get("ch_part", "")), "log_ids": [int(i) for i in g["id"]]})
    return pd.DataFrame(recs, columns=cols)


def status(ch: pd.DataFrame, bk: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    """챔버마다 오늘(또는 다음) 예약 한 줄: now = 오늘 쓰는 중, soon = 아직 시작 전."""
    out = ch.copy()
    now, soon = [], []
    for cid in out["id"].astype(int):
        b = bk[bk["chamber_id"] == cid] if not bk.empty else bk
        cur = b[(b["start"] <= day) & (b["end"] >= day)] if not b.empty else b
        nxt = b[b["start"] > day].sort_values("start") if not b.empty else b
        now.append(cur.iloc[0].to_dict() if not cur.empty else None)
        soon.append(nxt.iloc[0].to_dict() if not nxt.empty else None)
    out["now"], out["next"] = now, soon
    return out


def span_text(a: dt.date, b: dt.date, today: dt.date) -> str:
    fa = f"{a:%m.%d}" if a.year == today.year else f"'{a:%y.%m.%d}"
    fb = f"{b:%m.%d}" if b.year == today.year else f"'{b:%y.%m.%d}"
    return f"{fa} ~ {fb}"


def to_excel(st_df: pd.DataFrame, today: dt.date) -> bytes:
    """센터별 현황표 (건물명 · 장비명 · 싸이클러 · 챔버 · 채널 no. · 채널수 · 사용 업체 · 사용기간)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "충방전기 현황"
    thin = Side(style="thin", color="999999")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="D9D9D9")
    use_fill = PatternFill("solid", fgColor="FFFF66")
    center_fill = PatternFill("solid", fgColor="FFC000")
    ws.append([f"충방전기 장비사용 현황표 ({today:%y.%m.%d}.)"])
    ws["A1"].font = Font(bold=True, size=13)
    heads = ["건물명", "장비명", "싸이클러", "챔버", "채널 no.", "채널수", "사용 업체", "사용기간"]
    for center, g in st_df.groupby("center", sort=False):
        ws.append([])
        ws.append(heads)
        for c in ws[ws.max_row]:
            c.fill, c.font, c.border = head_fill, Font(bold=True), box
            c.alignment = Alignment(horizontal="center")
        total = 0
        for r in g.to_dict("records"):
            b = r["now"] or r["next"]
            who = (b["company"] + ("" if r["now"] else " (예약)")) if b else ""
            when = span_text(b["start"], b["end"], today) if b else ""
            ws.append([center, r["unit"], r["cycler"], r["chamber"], r["channels"], int(r["ch_count"] or 0), who, when])
            total += int(r["ch_count"] or 0)
            for c in ws[ws.max_row]:
                c.border = box
                if r["now"] and c.column >= 3:
                    c.fill = use_fill
            ws.cell(ws.max_row, 1).fill = center_fill
        ws.append(["", "", "", "계", "", total, "", ""])
        for c in ws[ws.max_row]:
            c.font, c.border = Font(bold=True), box
    for col, wdt in zip("ABCDEFGH", (12, 12, 11, 12, 10, 8, 14, 18)):
        ws.column_dimensions[col].width = wdt
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
