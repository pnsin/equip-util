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

from core import calc, seed
from core.db import digits, to_date, to_num, to_str
from core.terms import w

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


INTERNAL_ORG = ("(재)충북테크노파크", "3018213840")  # 활용유형 '내부' = 우리 기관

# 지원개요를 어디서도 찾지 못할 때 쓰는 사용목적별 기본 문구 (2026-11-23)
DEFAULT_OVERVIEW = {
    "시험": "배터리 시험 평가",
    "분석": "배터리 분석",
    "계측": "배터리 계측",
    "생산": "배터리 시제품 제조",
    "교육": "배터리 제조 현장실습 교육",
    "기타": "배터리 연구개발 지원",
}
DEFAULT_PRODUCT = "이차전지"


def _who(rec: dict) -> tuple[str, str, str]:
    """같은 업체·같은 i-Tube 장비·같은 사용목적을 알아보는 열쇠.

    2026-11-24: 사용목적까지 같아야 빌려 씀 (내부 '생산' 실적에 내부 '교육' 실적의 제품명 '배터리 제조 교육'이 들어가던 문제)."""
    code = to_str(rec.get("itube_code")) or to_str(rec.get("equip_code"))
    who = to_str(rec.get("company")) or f"내부:{to_str(rec.get('dept'))}"
    return code, who, to_str(rec.get("purpose"))


def known_details(history: list[dict]) -> dict[tuple[str, str], dict]:
    """다른 실적에 적힌 지원개요·시험법·제품명을 업체+장비별로 모아 둠 (최근 것이 이김)."""
    out: dict[tuple[str, str], dict] = {}
    rows = sorted(history, key=lambda r: (str(r.get("start_date") or ""), str(r.get("id") or "")))
    for r in rows:
        overview, method, _ = seed.parse_detail(r.get("detail"))
        k = _who(r)
        d = out.setdefault(k, {})
        if overview:
            d["overview"] = overview
            if method and method != "-":
                d["method"] = method
        if to_str(r.get("product")):
            d["product"] = to_str(r.get("product"))
    return out


def _fill_defaults(rec: dict, known: dict | None = None) -> dict:
    """내려받기 전에 비어 있는 칸 채우기 (시트의 실적은 그대로 둠).

    지원개요: 실적의 지원개요 → 사용목적(상세) → 같은 업체·장비의 다른 실적 → 사용목적별 기본 문구
    인증/인정/시험법: 없으면 '-' · 지원내용: 없으면 지원개요 · 사용목적(U열): 없으면 지원개요
    제품명: 같은 업체·장비의 다른 실적 → 교육은 '배터리 제조 교육', 그 밖은 세부품목(없으면 이차전지)
    내부 실적: 기업명·사업자번호 = 우리 기관
    """
    rec = dict(rec)
    k = known.get(_who(rec), {}) if known else {}
    overview, method, content = seed.parse_detail(rec.get("detail"))
    purpose = to_str(rec.get("purpose"))
    overview = (overview or to_str(rec.get("purpose_detail")) or k.get("overview")
                or DEFAULT_OVERVIEW.get(purpose, DEFAULT_OVERVIEW["기타"]))
    method = method or k.get("method") or "-"
    rec["detail"] = seed.compose_detail(overview, method, content or overview)
    if not to_str(rec.get("purpose_detail")):
        rec["purpose_detail"] = overview
    if not to_str(rec.get("product")):
        rec["product"] = (k.get("product") or ("배터리 제조 교육" if purpose == "교육" else "")
                          or to_str(rec.get("sub_item")) or DEFAULT_PRODUCT)
    # 2026-11-23 사용자: 휴무일자포함은 모두 N, 주말·공휴일 시간은 뺌 (가동률 계산과 같은 기준).
    # 주말 포함(Y) 실적은 사용시간을 기간 안 평일 몫만 남김 (예: 화~다음 월 7일 148h → 평일 5일 몫 105.7h).
    if to_str(rec.get("include_holidays")) != "N":
        s, e = to_date(rec.get("start_date")), to_date(rec.get("end_date")) or to_date(rec.get("start_date"))
        if s and e and e >= s:
            days = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
            off = calc.kr_holidays({d.year for d in days})
            work = sum(1 for d in days if d.weekday() < 5 and d not in off)
            rec["hours"] = (to_num(rec.get("hours"), 0) or 0) * work / len(days)
    rec["include_holidays"] = "N"
    if to_str(rec.get("usage_type")) == "내부":
        if not to_str(rec.get("company")):
            rec["company"] = INTERNAL_ORG[0]
        if not digits(rec.get("brn")):
            rec["brn"] = INTERNAL_ORG[1]
    return rec


_SUM_KEYS = ("start_date", "end_date", "hours", "fee", "samples")


def merge_periods(records: list[dict]) -> list[dict]:
    """하루씩 나뉜 실적을 기간 한 줄로 합침 (2026-11-23, 목록이 너무 길어서).

    시작·종료일과 시간·사용료·시료수만 빼고 모든 칸이 같은 실적끼리, 날짜가 이어지면
    (사이에 주말·공휴일만 있어도 이어진 것으로 봄) 한 줄로: 시작일 = 처음, 종료일 = 끝,
    사용시간·사용료 = 합계, 시료수 = 가장 큰 값. 같은 달 안에서만 합침
    (i-Tube 규칙: 같은 해, 2개월 이내 / 월별 제출과 맞춤).
    """
    if not records:
        return records
    dates = [to_date(r.get("start_date")) for r in records] + [to_date(r.get("end_date")) for r in records]
    off = calc.kr_holidays({d.year for d in dates if d})

    def rest_only(a: dt.date, b: dt.date) -> bool:  # a~b 사이(양 끝 제외)가 모두 쉬는 날인가
        d = a + dt.timedelta(days=1)
        while d < b:
            if d.weekday() < 5 and d not in off:
                return False
            d += dt.timedelta(days=1)
        return True

    def key(r: dict) -> tuple:
        return tuple(_cell_value(k, r) for k in KEYS if k not in _SUM_KEYS)

    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault(key(r), []).append(r)
    out: list[dict] = []
    for rows in groups.values():
        rows.sort(key=lambda r: (to_date(r.get("start_date")) or dt.date.min, to_date(r.get("end_date")) or dt.date.min))
        cur = None
        for r in rows:
            s, e = to_date(r.get("start_date")), to_date(r.get("end_date")) or to_date(r.get("start_date"))
            if (cur is not None and s and cur["_e"] and (s.year, s.month) == (cur["_s"].year, cur["_s"].month)
                    and (e.year, e.month) == (cur["_s"].year, cur["_s"].month)
                    and (s <= cur["_e"] + dt.timedelta(days=1) or rest_only(cur["_e"], s))):
                cur["_e"] = max(cur["_e"], e)
                cur["hours"] = (to_num(cur.get("hours"), 0) or 0) + (to_num(r.get("hours"), 0) or 0)
                cur["fee"] = (to_num(cur.get("fee"), 0) or 0) + (to_num(r.get("fee"), 0) or 0)
                cur["samples"] = max(to_num(cur.get("samples"), 1) or 1, to_num(r.get("samples"), 1) or 1)
                continue
            cur = dict(r, _s=s, _e=e)
            out.append(cur)
    for r in out:
        r["start_date"], r["end_date"] = r.pop("_s"), r.pop("_e")
    out.sort(key=lambda r: (r["start_date"] or dt.date.min, to_str(r.get("equip_name"))))
    return out


def make_itube_file(records: list[dict], equipment_rows: list[tuple[str, str]],
                    template_bytes: bytes | None = None, history: list[dict] | None = None) -> bytes:
    """실적 목록을 i-Tube 업로드 양식에 채워 xlsx 바이트로 돌려줍니다.

    template_bytes 가 있으면(설정에서 올린 공식 양식) 그 파일에 그대로 채우고,
    없으면 build_blank 로 만든 양식에 채웁니다.
    history: 빈칸을 채울 때 참고할 전체 실적 (없으면 records 만 참고).
    """
    known = known_details(list(history or []) + list(records))
    records = merge_periods([_fill_defaults(r, known) for r in records])
    records = [r for r in records if (to_num(r.get("hours"), 0) or 0) > 0]  # 주말에만 쓴 실적은 빠짐
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
        (w("평균 가동률(%)"), round(tot["util"], 1)),
        (w("목표 가동률(%)"), target),
        ("사용료 합계(원)", round(tot["fee"])),
        ("연간 기준시간(h)", annual),
        ("작성일", dt.date.today().isoformat()),
    ]
    eq = summary.drop(columns=["equip_id", "최상위"], errors="ignore").copy()
    eq["KPI"] = eq["KPI"].map({True: "대상", False: "제외"})
    eq["목표달성"] = eq["가동률"].map(lambda v: "" if v is None or pd.isna(v) else ("달성" if v >= target else "미달"))
    eq = eq.sort_values("가동률", ascending=False, na_position="last").round({"사용시간": 1, "가용시간": 1, "가동률": 1, "사용료": 0})

    log_cols = {"start_date": "사용시작일", "end_date": "사용종료일", "equip_name": "장비명", "equip_code": "장비번호",
                "purpose": "사용목적", "usage_type": "활용유형", "company": "기업명", "hours": "사용시간",
                "fee": "사용료", "product": "제품명", "created_by": "담당자"}
    lg = logs[list(log_cols)].rename(columns=log_cols).copy()
    for c in ("사용시작일", "사용종료일"):
        lg[c] = pd.to_datetime(lg[c]).dt.date

    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        pd.DataFrame(summary_rows, columns=["항목", "값"]).to_excel(xw, sheet_name="요약", index=False)
        eq.rename(columns=w).to_excel(xw, sheet_name=w("장비별 가동률"), index=False)
        monthly.round(1).rename(columns=w).to_excel(xw, sheet_name="월별 추이", index=False)
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
