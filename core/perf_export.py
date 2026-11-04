"""실적 내려받기: 예전에 쓰던 '장비가동률 입력시트' 엑셀 양식에 고른 기간의 실적을 채워 만듭니다.

원본 양식(2025_장비가동률 입력시트_신규.xlsx)의 구성을 그대로 따릅니다.
- 가동데이터: 한 줄 = 실적 한 건. 접수번호 ~ 가동일수(A~R) + 오른쪽에 날짜별 사용시간(S~)
- 구분별 일간 시트(원본의 '가동률_제조' 등): 장비별 날짜별 사용시간. 세부장비 시간은 주장비 줄에 더함
- 장비목록: 장비 › 세부장비 목록과 ITUBE번호
원본은 2025년 365일이 고정이었지만, 여기서는 고른 기간의 날짜만 열로 만듭니다.
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from core import calc, seed
from core.db import to_date, to_num, to_str
from core.terms import w

MAX_DAYS = 731  # 한 파일에 2년까지

_FONT = Font(name="맑은 고딕", size=11)
_BOLD = Font(name="맑은 고딕", size=11, bold=True)
_TITLE = Font(name="맑은 고딕", size=14, bold=True)
_GREY = Font(name="맑은 고딕", size=10, color="808080")
_SAT = Font(name="맑은 고딕", size=11, color="1F4E99")
_SUN = Font(name="맑은 고딕", size=11, color="C00000")
_YELLOW = PatternFill("solid", fgColor="FFFF00")  # 원본 머리글 색
_GREEN = PatternFill("solid", fgColor="92D050")   # 원본 가동시간·가동일자 색
_WEEKEND = PatternFill("solid", fgColor="F2F2F2")
_HOLI = PatternFill("solid", fgColor="FCE4E4")
_ROOT = PatternFill("solid", fgColor="FFF8D6")
_TOTAL = PatternFill("solid", fgColor="E2EFDA")
_DONE = PatternFill("solid", fgColor="E2EFDA")
_DOING = PatternFill("solid", fgColor="FFF2CC")
_thin = Side(style="thin", color="000000")
_med = Side(style="medium", color="000000")
_B = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_C = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LFT = Alignment(horizontal="left", vertical="center")
_CN = Alignment(horizontal="center", vertical="center")  # 데이터 칸 (줄바꿈 없음)
_WEEK = "월화수목금토일"

# 원본 가동데이터 시트의 열 너비
_WIDTHS = {"A": 9.3, "B": 20.8, "C": 9, "D": 15, "E": 19.3, "F": 13, "G": 6, "H": 11, "I": 31.3, "J": 9.3,
           "K": 11.1, "L": 5.5, "M": 11.1, "N": 5.5, "O": 8, "P": 38.8, "Q": 7, "R": 7}
FIRST_DAY_COL = 19  # S
DATA_ROW = 9


def _fmt_h(v: float):
    v = round(float(v), 2)
    return int(v) if v == int(v) else v


def _weeknum(d: dt.date) -> int:
    """엑셀 WEEKNUM(d) 과 같은 주차 (일요일 시작, 1월 1일이 든 주가 1주)."""
    jan1 = dt.date(d.year, 1, 1)
    return ((d - jan1).days + (jan1.weekday() + 1) % 7) // 7 + 1


def _days(s: dt.date, e: dt.date) -> list[dt.date]:
    return [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]


def select_logs(logs: pd.DataFrame, s: dt.date, e: dt.date, labels: list[str] | None = None) -> pd.DataFrame:
    """기간과 하루라도 겹치는 실적 (labels 를 주면 그 구분(시험·제조…)만)."""
    if logs.empty:
        return logs
    sel = logs[(logs["start_date"] <= pd.Timestamp(e)) & (logs["end_date"].fillna(logs["start_date"]) >= pd.Timestamp(s))]
    if labels:
        sel = sel[sel["purpose"].map(seed.purpose_label).isin(labels)]
    return sel.sort_values(["start_date", "equip_name", "id"]).reset_index(drop=True)


def _head(ws, title: str, sub: str) -> None:
    ws["A1"], ws["A2"] = title, sub
    ws["A1"].font, ws["A2"].font = _TITLE, _GREY


def _box(ws, rng: str, value, fill=_YELLOW, font=_BOLD) -> None:
    first = rng.split(":")[0]
    if ":" in rng:
        ws.merge_cells(rng)
        for row in ws[rng]:
            for c in row:
                c.border, c.fill = _B, fill
    c = ws[first]
    c.value, c.font, c.fill, c.alignment, c.border = value, font, fill, _C, _B


def _date_header(ws, days: list[dt.date], col0: int, row_date: int, holidays: set) -> None:
    """원본처럼 날짜 아래에 월·주차·요일을 한 줄씩 둡니다."""
    rows = (row_date, row_date + 1, row_date + 2, row_date + 3)
    for j, d in enumerate(days):
        col = col0 + j
        vals = (d, d.month, _weeknum(d), _WEEK[d.weekday()])
        fill = _HOLI if d in holidays else (_WEEKEND if d.weekday() >= 5 else None)
        font = _SUN if d.weekday() == 6 or d in holidays else (_SAT if d.weekday() == 5 else _FONT)
        for r, v in zip(rows, vals):
            c = ws.cell(r, col, v)
            c.font, c.alignment, c.border = font, _C, _B
            if fill:
                c.fill = fill
        ws.cell(row_date, col).number_format = "m/d"
        ws.column_dimensions[L(col)].width = 5.6


def _people(companies: pd.DataFrame) -> dict[str, tuple[str, str]]:
    if companies is None or companies.empty:
        return {}
    return {to_str(n): (to_str(c), to_str(p)) for n, c, p in
            zip(companies["name"], companies.get("contact", ""), companies.get("phone", ""))}


def _data_sheet(ws, sel: pd.DataFrame, per_log: dict, days: list[dt.date], holidays: set,
                people: dict, today: dt.date) -> None:
    for col, wd in _WIDTHS.items():
        ws.column_dimensions[col].width = wd
    _box(ws, "A4:A8", "접수번호")
    _box(ws, "B4:D6", "의뢰자")
    for rng, v in (("B7:B8", "회사명"), ("C7:C8", "담당자"), ("D7:D8", "연락처")):
        _box(ws, rng, v)
    for col, v in zip("EFGHIJ", ("기기명", "모델명", "샘플\n수량", "담당자", "비고", "가동현황")):
        _box(ws, f"{col}4:{col}8", v)
    _box(ws, "K4:Q4", "가동장비")
    _box(ws, "K5:L6", "가동시작")
    _box(ws, "M5:N6", "가동종료")
    for col, v in zip("KLMN", ("월일", "시간", "월일", "시간")):
        _box(ws, f"{col}7:{col}8", v)
    _box(ws, "O5:O8", "구분")
    _box(ws, "P5:P8", "장비명")
    _box(ws, "Q5:Q8", "가동\n시간", fill=_GREEN)
    _box(ws, "R4:R8", "가동\n일수", fill=_GREEN)
    last = FIRST_DAY_COL + len(days) - 1
    _box(ws, f"{L(FIRST_DAY_COL)}4:{L(last)}4" if last > FIRST_DAY_COL else f"{L(FIRST_DAY_COL)}4", "가동일자",
         fill=_GREEN)
    _date_header(ws, days, FIRST_DAY_COL, 5, holidays)
    ws.row_dimensions[4].height = 18
    ws.freeze_panes = f"{L(FIRST_DAY_COL)}{DATA_ROW}"

    for i, r in enumerate(sel.to_dict("records")):
        row = DATA_ROW + i
        s, e = to_date(r["start_date"]), to_date(r["end_date"]) or to_date(r["start_date"])
        company = to_str(r.get("company")) or to_str(r.get("dept"))
        contact, phone = people.get(to_str(r.get("company")), ("", ""))
        note = " / ".join(x for x in (to_str(r.get("purpose_detail")), to_str(r.get("etc"))) if x)
        split = per_log.get(int(r["id"]), {})
        in_period = sum(split.values())
        status = "완료" if e and e <= today else "진행중"
        vals = [None, company, contact, phone, to_str(r.get("product")), None,
                int(to_num(r.get("samples"), 0)) or None, to_str(r.get("created_by")), note, status,
                s, None, e, None, seed.purpose_label(to_str(r.get("purpose"))), to_str(r.get("equip_name")),
                _fmt_h(in_period) if in_period else None, sum(1 for v in split.values() if v > 0) or None]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(row, j, v)
            c.font, c.border = _FONT, _B
            c.alignment = _LFT if j in (2, 5, 9, 16) else _CN
        ws.cell(row, 11).number_format = ws.cell(row, 13).number_format = "mm-dd"
        ws.cell(row, 10).fill = _DONE if status == "완료" else _DOING
        ws.cell(row, 1).fill = _YELLOW  # 원본에서 접수번호 칸은 노란색 (직접 적는 칸)
        ws.cell(row, 17).fill = _GREEN
        for j, d in enumerate(days):
            h = split.get(d)
            c = ws.cell(row, FIRST_DAY_COL + j, _fmt_h(h) if h else None)
            c.font, c.alignment, c.border = _FONT, _CN, _B
    if len(sel):
        ws.auto_filter.ref = f"A8:{L(last)}{DATA_ROW + len(sel) - 1}"


def _tree_rows(eq: pd.DataFrame, used: dict[int, dict]) -> list[dict]:
    """장비 순서대로, 자신+하위 장비 사용시간 합이 있는 장비만. 값은 하위까지 더한 시간."""
    if eq.empty:
        return []
    kids: dict = {}
    for i, p in zip(eq["id"], eq["parent_id"]):
        kids.setdefault(int(p) if pd.notna(p) else None, []).append(int(i))
    by_id = eq.set_index("id")
    known = set(by_id.index)
    memo: dict[int, dict] = {}

    def total(i: int) -> dict:
        if i not in memo:
            acc = dict(used.get(i, {}))
            for k in kids.get(i, []):
                for d, h in total(k).items():
                    acc[d] = acc.get(d, 0) + h
            memo[i] = acc
        return memo[i]

    out = []
    for i in eq["id"].astype(int):
        t = total(i)
        if not any(t.values()):
            continue
        r = by_id.loc[i]
        p = r["parent_id"]
        out.append({"id": i, "depth": int(r["depth"]), "name": r["name"],
                    "parent": by_id.at[int(p), "name"] if pd.notna(p) and int(p) in known else "",
                    "root": by_id.at[int(r["root_id"]), "name"] if int(r["root_id"]) in known else r["name"],
                    "code": r["code"], "category": to_str(r.get("category")), "hours": t})
    # 장비 목록에 없는 장비(지워진 장비)의 실적도 빠뜨리지 않음
    for i, t in used.items():
        if i not in known and any(t.values()):
            out.append({"id": i, "depth": 0, "name": f"(지운 장비 #{i})", "parent": "", "root": "", "code": "",
                        "category": "", "hours": t})
    return out


def _daily_sheet(ws, label: str, rows: list[dict], days: list[dt.date], holidays: set, title: str, sub: str) -> None:
    _head(ws, title, sub)
    first = 6  # F
    for col, wd in zip("ABCDE", (8, 34, 24, 24, 9)):
        ws.column_dimensions[col].width = wd
    for col, v in zip("ABCDE", ("구분", "장비명", "상위 장비", "주장비", "합계")):
        _box(ws, f"{col}4:{col}7", v, fill=_GREEN if col == "E" else _YELLOW)
    _date_header(ws, days, first, 4, holidays)
    ws.freeze_panes = f"{L(first)}8"
    r0 = 8
    grand = {}
    for i, row in enumerate(rows):
        rr = r0 + i
        top = row["depth"] == 0
        name = ("    " * (row["depth"] - 1) + "└ " if not top else "") + row["name"]
        tot = sum(row["hours"].values())
        root_txt = row["root"] + (f" ({row['code']})" if top and row["code"] else "")
        for j, v in enumerate((label, name, row["parent"], root_txt, _fmt_h(tot)), start=1):
            c = ws.cell(rr, j, v)
            c.font, c.border = (_BOLD if top else _FONT), _B
            c.alignment = _LFT if j in (2, 3, 4) else _C
            if top:
                c.fill = _ROOT
        for j, d in enumerate(days):
            h = row["hours"].get(d)
            c = ws.cell(rr, first + j, _fmt_h(h) if h else None)
            c.font, c.alignment, c.border = (_BOLD if top else _FONT), _C, _B
            if top:
                c.fill = _ROOT
                if h:
                    grand[d] = grand.get(d, 0) + h
    rr = r0 + len(rows)
    vals = ("", "합계", "", "", _fmt_h(sum(grand.values())))
    for j, v in enumerate(vals, start=1):
        c = ws.cell(rr, j, v)
        c.font, c.border, c.fill, c.alignment = _BOLD, _B, _TOTAL, _C
    for j, d in enumerate(days):
        h = grand.get(d)
        c = ws.cell(rr, first + j, _fmt_h(h) if h else None)
        c.font, c.border, c.fill, c.alignment = _BOLD, _B, _TOTAL, _C
    ws.cell(rr + 2, 2, "세부장비 시간은 위쪽 주장비(노란 줄) 시간에 더해져 있습니다.").font = _GREY


def _equip_sheet(ws, eq: pd.DataFrame) -> None:
    heads = ("구분", "장비명", "상위 장비", "주장비", "장비구분", "ITUBE번호", "국가연구시설장비번호", "모델명", "장비위치")
    for j, (h, wd) in enumerate(zip(heads, (8, 36, 26, 26, 16, 14, 22, 18, 16)), start=1):
        c = ws.cell(1, j, h)
        c.font, c.fill, c.alignment, c.border = _BOLD, _YELLOW, _C, _B
        ws.column_dimensions[L(j)].width = wd
    if eq.empty:
        return
    by = dict(zip(eq["id"].astype(int), eq["name"]))
    for i, r in enumerate(eq.to_dict("records"), start=2):
        p = r["parent_id"]
        vals = (r.get("category", ""), "    " * int(r["depth"]) + r["name"],
                by.get(int(p), "") if pd.notna(p) else "", by.get(int(r["root_id"]), ""), r["kind"], r["code"],
                r.get("nfec", ""), r.get("model", ""), r.get("location", ""))
        for j, v in enumerate(vals, start=1):
            c = ws.cell(i, j, v)
            c.font, c.border = (_BOLD if int(r["depth"]) == 0 else _FONT), _B
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:I{len(eq) + 1}"


def make_performance_file(logs: pd.DataFrame, eq: pd.DataFrame, companies: pd.DataFrame | None,
                          s: dt.date, e: dt.date, mode: str = "spread", labels: list[str] | None = None,
                          today: dt.date | None = None) -> tuple[bytes, dict]:
    """(엑셀 바이트, 요약 {'count', 'hours', 'labels'}). 시간은 기간 안의 날짜에 해당하는 몫만 셉니다."""
    if (e - s).days + 1 > MAX_DAYS:
        raise ValueError(f"한 번에 {MAX_DAYS // 365}년까지 내려받을 수 있습니다.")
    today = today or dt.date.today()
    days = _days(s, e)
    holidays = calc.kr_holidays(range(s.year, e.year + 1))
    sel = select_logs(logs, s, e, labels)
    daily = calc.window(calc.expand_daily(sel, mode), s, e)
    per_log: dict[int, dict] = {}
    for lid, d, h in zip(daily["log_id"], daily["day"], daily["hours"]):
        per_log.setdefault(int(lid), {})
        per_log[int(lid)][d.date()] = per_log[int(lid)].get(d.date(), 0) + float(h)

    period = f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}"
    made = f"{today:%Y-%m-%d} 앱에서 내려받음"
    wb = Workbook()
    ws = wb.active
    ws.title = f"가동데이터({s.year})" if s.year == e.year else f"가동데이터({s.year}-{e.year})"
    _head(ws, f"장비 실적 · {period}", f"{made} · {len(sel)}건 · 노란 칸(접수번호)은 직접 적어 주세요")
    _data_sheet(ws, sel, per_log, days, holidays, _people(companies), today)

    # 구분별 일간 시트 (원본: 가동률_분석 / 가동률_제조 / 가동률_시험)
    sel_lab = sel.assign(_lab=sel["purpose"].map(seed.purpose_label)) if len(sel) else sel.assign(_lab="")
    order = ["시험", "제조", "분석", "교육", "지원"]
    present = [x for x in order if x in set(sel_lab["_lab"])] + sorted(set(sel_lab["_lab"]) - set(order) - {""})
    groups = [("전체", sel_lab)] + [(lab, sel_lab[sel_lab["_lab"] == lab]) for lab in present]
    for lab, part in groups:
        used: dict[int, dict] = {}
        for r in part.itertuples(index=False):
            if pd.isna(r.equip_id):
                continue
            acc = used.setdefault(int(r.equip_id), {})
            for d, h in per_log.get(int(r.id), {}).items():
                acc[d] = acc.get(d, 0) + h
        sh = wb.create_sheet(w(f"가동률_{lab}"))
        _daily_sheet(sh, "" if lab == "전체" else lab, _tree_rows(eq, used), days, holidays,
                     w(f"일간 사용시간 · {lab}"), f"{period} · {made}")

    _equip_sheet(wb.create_sheet("장비목록"), eq)

    buf = io.BytesIO()
    wb.save(buf)
    total = sum(sum(v.values()) for v in per_log.values())
    return buf.getvalue(), {"count": len(sel), "hours": total, "labels": present}


def file_name(s: dt.date, e: dt.date) -> str:
    if s.day == 1 and (e + dt.timedelta(days=1)).day == 1:
        if (s.year, s.month) == (e.year, e.month):
            return f"장비실적_{s:%Y}년{s.month}월.xlsx"
        if s.year == e.year:
            return f"장비실적_{s:%Y}년{s.month}~{e.month}월.xlsx"
    return f"장비실적_{s:%Y%m%d}-{e:%Y%m%d}.xlsx"
