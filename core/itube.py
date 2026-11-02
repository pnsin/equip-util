"""i-Tube 장비일지 업로드 양식 만들기 / 읽기, 분석 보고서 엑셀 만들기."""
from __future__ import annotations

import datetime as dt
import io
from copy import copy

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from core import seed
from core.db import digits, to_date, to_num, to_str

FIRST_ROW = 4
KEYS = [k for _, k in seed.COLUMNS]

_thin = Side(style="thin", color="000000")
_BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_FONT = Font(name="맑은 고딕", size=11)
_HEADER_FILL = PatternFill("solid", fgColor="FFFF00")
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(vertical="center")
_WRAP = Alignment(vertical="center", wrap_text=True)
_LEFT_COLS = {"company", "brn", "dept", "purpose_detail", "etc"}


def _add_name(wb: Workbook, name: str, ref: str) -> None:
    dn = DefinedName(name, attr_text=ref)
    names = wb.defined_names
    if hasattr(names, "add"):  # openpyxl 3.1+
        names.add(dn)
    else:
        names.append(dn)


def _style_data_cell(cell, key: str) -> None:
    cell.font = _FONT
    cell.border = _BORDER
    if key == "detail":
        cell.alignment = _WRAP
    elif key in _LEFT_COLS:
        cell.alignment = _LEFT
    else:
        cell.alignment = _CENTER
    if key in ("start_date", "end_date"):
        cell.number_format = "yyyy-mm-dd"


def build_blank(equipment_rows: list[tuple[str, str]]) -> Workbook:
    """원본 양식과 같은 구조(시트·헤더·드롭다운 목록·이름 정의)의 빈 양식."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    s2 = wb.create_sheet("Sheet2")
    wb.create_sheet("Sheet3")
    s4 = wb.create_sheet("Sheet4")

    ws["A1"] = seed.UPLOAD_NOTE
    ws["A1"].font = Font(name="맑은 고딕", size=10)
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.merge_cells("A1:V1")
    ws.row_dimensions[1].height = 366
    ws.row_dimensions[1].hidden = True
    for i, (header, key) in enumerate(seed.COLUMNS, start=1):
        ws.cell(2, i, i)
        c = ws.cell(3, i, header)
        c.fill = _HEADER_FILL
        c.border = _BORDER
        c.font = _FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=key in ("company", "brn"))
        ws.column_dimensions[get_column_letter(i)].width = seed.COLUMN_WIDTHS[i - 1]
    ws.row_dimensions[3].height = 33
    ws.auto_filter.ref = "A3:V3"

    for col, values in seed.SHEET2_COLUMNS.items():
        for r, v in enumerate(values, start=1):
            s2[f"{col}{r}"] = v
    for ref, v in seed.SHEET2_EXTRA.items():
        s2[ref] = v
    for name, ref in seed.DEFINED_NAMES:
        _add_name(wb, name, ref)

    for r, (name, code) in enumerate(equipment_rows, start=1):
        s4.cell(r, 1, name)
        s4.cell(r, 2, code or "등록중")
    return wb


def _add_validations(ws, last_row: int) -> None:
    def add(dv: DataValidation, sqref: str) -> None:
        dv.showInputMessage = True
        dv.showErrorMessage = True
        ws.add_data_validation(dv)
        for part in sqref.split():
            dv.add(part)

    r0, r1 = FIRST_ROW, last_row
    add(DataValidation(type="list", formula1="활용유형", allow_blank=True), f"B{r0}:B{r1}")
    add(DataValidation(type="list", formula1="사용목적", allow_blank=True), f"A{r0}:A{r1}")
    add(DataValidation(type="list", formula1="업종", allow_blank=True), f"F{r0}:F{r1}")
    add(DataValidation(type="list", formula1="노출여부", allow_blank=True), f"K{r0}:K{r1} R{r0}:R{r1}")
    add(DataValidation(type="date", formula1="43101", formula2="73415", allow_blank=True,
                       error="입력 형식 혹은 2018년 이후인지 확인하여 주십시요"), f"P{r0}:Q{r1}")
    add(DataValidation(type="whole", formula1="0", formula2="10000000", allow_blank=True), f"J{r0}:J{r1} S{r0}:S{r1}")
    add(DataValidation(type="whole", formula1="0", formula2="9999999999999990", allow_blank=True), f"T{r0}:T{r1}")
    add(DataValidation(type="list", formula1="장비구분", allow_blank=True), f"O{r0}:O{r1}")
    add(DataValidation(type="whole", formula1="0", formula2="999999999999", allow_blank=True), f"D{r0}:D{r1}")
    add(DataValidation(type="list", formula1="INDIRECT(F4)", allow_blank=True,
                       errorTitle="선택값 외의 데이터", error="선택값으로 데이터를 넣어주세요."), f"G{r0}:G{r1}")
    add(DataValidation(type="list", formula1="INDIRECT(G4)", allow_blank=True), f"H{r0}:H{r1}")


def _cell_value(key: str, rec: dict):
    v = rec.get(key)
    if key in ("start_date", "end_date"):
        return to_date(v)
    if key == "brn":
        d = digits(v)
        return int(d) if d else None
    if key in ("hours", "fee", "samples"):
        n = to_num(v)
        return None if n is None else int(round(n))
    s = to_str(v)
    return s or None


def make_itube_file(records: list[dict], equipment_rows: list[tuple[str, str]],
                    template_bytes: bytes | None = None) -> bytes:
    """실적 목록을 i-Tube 업로드 양식에 채워 xlsx 바이트로 돌려줍니다.

    template_bytes 가 있으면(설정에서 올린 공식 양식) 그 파일에 그대로 채우고,
    없으면 build_blank 로 만든 양식에 채웁니다.
    """
    if template_bytes:
        wb = load_workbook(io.BytesIO(template_bytes))
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.worksheets[0]
        styles = [copy(ws.cell(FIRST_ROW, c)._style) for c in range(1, len(KEYS) + 1)]
        for row in ws.iter_rows(min_row=FIRST_ROW, max_row=max(ws.max_row, FIRST_ROW)):
            for c in row:
                c.value = None
        for i, rec in enumerate(records):
            r = FIRST_ROW + i
            for j, key in enumerate(KEYS, start=1):
                c = ws.cell(r, j, _cell_value(key, rec))
                c._style = copy(styles[j - 1])
            ws.row_dimensions[r].height = 49.5
    else:
        wb = build_blank(equipment_rows)
        ws = wb["Sheet1"]
        last = max(302, FIRST_ROW + len(records) - 1)
        for r in range(FIRST_ROW, last + 1):
            rec = records[r - FIRST_ROW] if r - FIRST_ROW < len(records) else {}
            for j, key in enumerate(KEYS, start=1):
                c = ws.cell(r, j, _cell_value(key, rec) if rec else None)
                _style_data_cell(c, key)
            ws.row_dimensions[r].height = 49.5
        _add_validations(ws, last)
    wb.active = 0
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def read_itube_file(data: bytes) -> tuple[list[dict], list[tuple[str, str]]]:
    """작성된 i-Tube 양식에서 실적 행과 (Sheet4가 있으면) 장비 목록을 읽습니다."""
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.worksheets[0]
    header_row = FIRST_ROW - 1
    for r in range(1, 11):  # 헤더 위치가 다른 파일 대비
        if to_str(ws.cell(r, 13).value) == "장비명" and to_str(ws.cell(r, 1).value) == "사용목적":
            header_row = r
            break
    rows = []
    for values in ws.iter_rows(min_row=header_row + 1, max_col=len(KEYS), values_only=True):
        rec = {k: v for k, v in zip(KEYS, values)}
        if not to_str(rec.get("equip_name")) or to_num(rec.get("hours")) is None:
            continue
        for k in ("start_date", "end_date"):
            v = rec.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                rec[k] = dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
            else:
                rec[k] = to_date(v)
        rec["brn"] = digits(rec.get("brn"))
        for k in ("purpose", "usage_type", "company", "dept", "industry", "item", "sub_item", "product",
                  "disclose", "detail", "equip_name", "equip_code", "equip_kind", "include_holidays",
                  "purpose_detail", "etc"):
            rec[k] = to_str(rec.get(k))
        rec["disclose"] = rec["disclose"] or "N"
        rec["include_holidays"] = rec["include_holidays"] or "Y"
        rec["samples"] = int(to_num(rec.get("samples"), 1) or 1)
        rec["fee"] = int(to_num(rec.get("fee"), 0) or 0)
        rec["hours"] = int(round(to_num(rec.get("hours"), 0)))
        rows.append(rec)

    master: list[tuple[str, str]] = []
    if "Sheet4" in wb.sheetnames:
        for name, code in wb["Sheet4"].iter_rows(min_col=1, max_col=2, values_only=True):
            name, code = to_str(name), to_str(code)
            if name and not name.startswith("#"):
                master.append((name, "" if code in ("등록중", "#REF!") else code))
    return rows, master


def make_report(period_label: str, summary: pd.DataFrame, tot: dict, monthly: pd.DataFrame,
                by_purpose: pd.DataFrame, by_type: pd.DataFrame, logs: pd.DataFrame,
                target: float, annual: float) -> bytes:
    """가동률 분석 보고서 (요약 / 장비별 / 월별 / 목적·유형별 / 실적목록)."""
    bio = io.BytesIO()
    summary_rows = [
        ("분석기간", period_label),
        ("KPI 대상 장비 수", tot["equip_count"]),
        ("미사용 장비 수", tot["idle_count"]),
        ("총 사용시간(h)", round(tot["used"], 1)),
        ("총 가용시간(h)", round(tot["avail"], 1)),
        ("평균 가동률(%)", round(tot["util"], 1)),
        ("목표 가동률(%)", target),
        ("사용료 합계(원)", round(tot["fee"])),
        ("연간 기준시간(h)", annual),
        ("작성일", dt.date.today().isoformat()),
    ]
    eq = summary.drop(columns=["equip_id"]).copy()
    eq["KPI"] = eq["KPI"].map({True: "대상", False: "제외"})
    eq["목표달성"] = eq["가동률"].map(lambda v: "" if v is None or pd.isna(v) else ("달성" if v >= target else "미달"))
    eq = eq.sort_values("가동률", ascending=False, na_position="last").round({"사용시간": 1, "가용시간": 1, "가동률": 1, "사용료": 0})

    log_cols = {"start_date": "사용시작일", "end_date": "사용종료일", "equip_name": "장비명", "equip_code": "장비번호",
                "purpose": "사용목적", "usage_type": "활용유형", "company": "기업명", "hours": "사용시간",
                "fee": "사용료", "product": "제품명", "created_by": "작성자"}
    lg = logs[list(log_cols)].rename(columns=log_cols).copy()
    for c in ("사용시작일", "사용종료일"):
        lg[c] = pd.to_datetime(lg[c]).dt.date

    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        pd.DataFrame(summary_rows, columns=["항목", "값"]).to_excel(xw, sheet_name="요약", index=False)
        eq.to_excel(xw, sheet_name="장비별 가동률", index=False)
        monthly.round(1).to_excel(xw, sheet_name="월별 추이", index=False)
        by_purpose.round(1).to_excel(xw, sheet_name="사용목적별", index=False)
        by_type.round(1).to_excel(xw, sheet_name="활용유형별", index=False)
        lg.to_excel(xw, sheet_name="실적목록", index=False)
        for ws in xw.book.worksheets:
            for cell in ws[1]:
                cell.font = Font(name="맑은 고딕", bold=True)
                cell.fill = PatternFill("solid", fgColor="DDE7F3")
                cell.alignment = _CENTER
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width * 1.6), 50)
            ws.freeze_panes = "A2"
    return bio.getvalue()
