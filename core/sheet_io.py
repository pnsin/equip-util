"""목록(장비·업체·담당자)을 엑셀로 내려받고, 고친 엑셀을 다시 올려 한 번에 반영합니다.

- 맨 앞 'ID' 열이 장비·업체를 가리키는 고정 번호입니다. 이름을 바꿔도 ID가 같으면 같은 것으로 봅니다.
- ID가 비어 있는 줄은 새로 추가합니다.
- 파일에 없는 줄은 지우지 않고 그대로 둡니다 (지우기는 화면에서).
- 파일에 없는 열은 원래 값을 그대로 둡니다.
"""
from __future__ import annotations

import io

import pandas as pd

ID_HEAD = "ID"


def _cell(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA or v is pd.NaT:
        return ""
    if isinstance(v, pd.Timestamp):
        return v.date()
    return v


# ── 보기 좋은 표 (2026-11-19: 정보 보관·공유용으로도 쓰이므로 보고서처럼) ─────────
FONT = "맑은 고딕"
NAVY, LINE, MAIN_BG, NOTE = "26324A", "C9D1DE", "E8ECFA", "6B7280"
NUM_FMT = {"int": "#,##0", "date": "yyyy-mm-dd"}
WIDE_MAX = 46   # 이보다 긴 글은 줄바꿈
NARROW = 8
SEQ_HEAD = "No."  # 읽기용 차례 번호 (올릴 때는 쓰지 않음)
LEFT_HEADS = {"장비명(한글)", "장비명", "주장비(종)", "시스템 구성", "비고", "모델명", "장비위치", "업체명", "주소"}
MUTED_HEADS = {ID_HEAD, "소속 장비 ID"}


def _text_width(v) -> float:
    """엑셀 열 너비 단위로 대략: 한글·전각은 2칸, 나머지는 1칸."""
    import unicodedata
    s = str(v if v is not None else "")
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1.05 for ch in s)


def _side():
    from openpyxl.styles import Border, Side
    t = Side(style="thin", color=LINE)
    return Border(left=t, right=t, top=t, bottom=t)


def style_table(ws, header_row: int = 1, first_col: int = 1, levels: list[int] | None = None,
                money: tuple[str, ...] = (), wrap_min: int = 0, filt: bool = True, freeze_cols: int = 1) -> None:
    """ws 의 header_row 부터 끝까지를 표처럼 꾸밈: 머리글, 테두리, 열 너비, 줄바꿈, 틀 고정, 필터.

    levels: 줄마다 0(주장비) / 1, 2…(세부장비 깊이). 0 줄은 굵게·연한 색, 세부장비는 이름 칸 들여쓰기.
    money: 천 단위 쉼표를 넣을 열 제목.
    """
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    last_row, last_col = ws.max_row, ws.max_column
    if last_col < first_col:
        return
    border = _side()
    heads = [ws.cell(header_row, c).value for c in range(first_col, last_col + 1)]
    for c in range(first_col, last_col + 1):
        h = ws.cell(header_row, c)
        h.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        h.fill = PatternFill("solid", fgColor="8A94A6" if heads[c - first_col] in MUTED_HEADS else NAVY)
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        h.border = border
    ws.row_dimensions[header_row].height = 30
    name_col = next((first_col + i for i, h in enumerate(heads) if str(h or "").startswith(("장비명", "업체명", "이름"))), None)
    widths = {}
    for c in range(first_col, last_col + 1):
        vals = [ws.cell(r, c).value for r in range(header_row + 1, min(last_row, header_row + 400) + 1)]
        body = max([_text_width(v) for v in vals] + [0])
        head = _text_width(heads[c - first_col])
        widths[c] = min(WIDE_MAX, max(NARROW, body + 2, min(head, 14) + 2))
    # 정렬은 열마다 하나로: 긴 글(이름·비고 등)은 왼쪽, 나머지(번호·구분·숫자)는 가운데
    left_cols = {c for c in widths if heads[c - first_col] in LEFT_HEADS or widths[c] >= 30}
    main_fill = PatternFill("solid", fgColor=MAIN_BG)
    for r in range(header_row + 1, last_row + 1):
        lv = levels[r - header_row - 1] if levels and r - header_row - 1 < len(levels) else None
        tall = 1
        for c in range(first_col, last_col + 1):
            cell = ws.cell(r, c)
            v = cell.value
            head = heads[c - first_col]
            left = c in left_cols
            wrap = isinstance(v, str) and _text_width(v) > widths[c] - 1
            if wrap:
                tall = max(tall, min(4, int(_text_width(v) // (widths[c] - 1)) + 1))
            indent = ((lv or 0) * 2 if c == name_col and lv else 0) + (1 if left else 0)
            cell.alignment = Alignment(horizontal="left" if left else "center", vertical="center",
                                       wrap_text=wrap, indent=indent)
            cell.border = border
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.number_format = NUM_FMT["int"] if head in money or float(v).is_integer() else "#,##0.##"
            elif hasattr(v, "year"):
                cell.number_format = NUM_FMT["date"]
            muted = head in MUTED_HEADS or head == SEQ_HEAD
            if lv == 0:
                cell.fill = main_fill
            cell.font = Font(name=FONT, bold=lv == 0 and not muted, size=10,
                             color="8A94A6" if muted else "1F2A44" if lv == 0 else "374151")
        ws.row_dimensions[r].height = 18 * tall + 2
    for c, wd in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = wd
    ws.freeze_panes = ws.cell(header_row + 1, first_col + freeze_cols)
    if filt and last_row > header_row:
        ws.auto_filter.ref = f"{get_column_letter(first_col)}{header_row}:{get_column_letter(last_col)}{last_row}"
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"


def to_xlsx(df: pd.DataFrame, heads: dict[str, str], sheet: str, levels: list[int] | None = None,
            money: tuple[str, ...] = (), id_last: tuple[str, ...] = ()) -> bytes:
    """heads: 내부 열 → 엑셀 열 제목. 1행 = 제목 (다시 올릴 때 이 제목으로 읽음).

    id_last 를 주면 (2026-11-19 장비 목록) 맨 앞은 'ID', id_last 열(소속 장비 ID 등)은 맨 뒤 회색 칸.
    (No. 차례 번호는 ID 와 헷갈려서 뺌 — 사용자 요청 2026-11-19, ID 가 1부터 차례대로라 그대로 씀)
    """
    from openpyxl import Workbook

    body = [c for c in heads if c != "id" and c not in id_last]
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    if id_last or levels is not None:
        tail = [c for c in id_last if c in heads]
        ws.append([ID_HEAD] + [heads[c] for c in body] + [heads[c] for c in tail])
        for r in df.to_dict("records"):
            ws.append([_cell(r.get(c)) for c in ["id"] + body + tail])
        freeze = 2
    else:
        cols = ["id"] + body
        ws.append([ID_HEAD] + [heads[c] for c in body])
        for r in df.to_dict("records"):
            ws.append([_cell(r.get(c)) for c in cols])
        freeze = 1
    style_table(ws, levels=levels, money=money, freeze_cols=freeze)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def add_sheet(data: bytes, name: str, df: pd.DataFrame, money: tuple[str, ...] = ()) -> bytes:
    """내려받는 엑셀 뒤에 참고용 시트를 붙임 (올릴 때는 'ID' 열이 있는 시트만 읽으므로 반영되지 않음)."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data))
    ws = wb.create_sheet(name)
    ws.append(list(df.columns))
    for r in df.itertuples(index=False):
        ws.append([_cell(v) for v in r])
    style_table(ws, money=money, freeze_cols=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def add_summary(data: bytes, name: str, title: str, blocks: list[tuple[str, pd.DataFrame]],
                notes: list[str] = (), first: bool = True) -> bytes:
    """요약 시트 (읽기용): 제목 + 작은 표 여러 개를 위아래로. 각 표의 마지막 줄이 '합계'면 굵게.

    first=True 면 맨 앞 시트로 두고 열었을 때 먼저 보이게 함 (올릴 때는 'ID' 열이 있는 시트만 읽음).
    """
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = load_workbook(io.BytesIO(data))
    ws = wb.create_sheet(name, 0 if first else None)
    ws.sheet_view.showGridLines = False
    ws["B2"] = title
    ws["B2"].font = Font(name=FONT, bold=True, size=15, color="1F2A44")
    ws.row_dimensions[2].height = 26
    r = 4
    border = _side()
    widths: dict[int, float] = {}
    for sub, df in blocks:
        ws.cell(r, 2, sub).font = Font(name=FONT, bold=True, size=11, color="4338CA")
        r += 1
        cols = list(df.columns)
        for j, h in enumerate(cols):
            c = ws.cell(r, 2 + j, h)
            c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
            c.fill = PatternFill("solid", fgColor=NAVY)
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = border
            widths[2 + j] = max(widths.get(2 + j, 0), _text_width(h) + 3)
        ws.row_dimensions[r].height = 24
        for i, row in enumerate(df.itertuples(index=False)):
            r += 1
            total = i == len(df) - 1 and str(row[0]).startswith("합계")
            for j, v in enumerate(row):
                c = ws.cell(r, 2 + j, _cell(v))
                c.border = border
                c.alignment = Alignment(horizontal="left" if j == 0 else "center", vertical="center", indent=1 if j == 0 else 0)
                if isinstance(c.value, (int, float)):
                    c.number_format = "#,##0"
                c.font = Font(name=FONT, bold=total or j == 0, size=10, color="1F2A44")
                if total:
                    c.fill = PatternFill("solid", fgColor=MAIN_BG)
                widths[2 + j] = max(widths.get(2 + j, 0), _text_width(v) + 3)
            ws.row_dimensions[r].height = 20
        r += 2
    for n in notes:
        ws.cell(r, 2, n).font = Font(name=FONT, size=9, color=NOTE)
        r += 1
    ws.column_dimensions["A"].width = 3
    for c, wd in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = max(10, min(36, wd))
    if first:
        wb.active = 0
        for s in wb.worksheets:
            s.sheet_view.tabSelected = s is ws
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _read_table(data: bytes) -> pd.DataFrame:
    """올린 파일에서 1행에 'ID' 열이 있는 첫 시트를 읽음 (요약·참고 시트는 건너뜀). 없으면 첫 시트."""
    book = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=object)
    for df in book.values():
        if ID_HEAD in [str(c).strip() for c in df.columns]:
            return df
    return next(iter(book.values()))


def _norm(v) -> str:
    v = _cell(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def merge(existing: pd.DataFrame, data: bytes, heads: dict[str, str]) -> tuple[pd.DataFrame, int, int, list[str]]:
    """올린 엑셀을 기존 목록에 합칩니다 → (합친 목록, 추가 수, 수정 수, 안내)."""
    up = _read_table(data)
    up.columns = [str(c).strip() for c in up.columns]
    back = {v: k for k, v in heads.items()}
    if ID_HEAD not in up.columns:
        return existing, 0, 0, [f"맨 앞 '{ID_HEAD}' 열이 없어요. 이 화면에서 내려받은 엑셀에 고쳐서 올려 주세요."]
    use = [c for c in up.columns if c in back]
    if not use:
        return existing, 0, 0, ["알아볼 수 있는 열 제목이 없어요. 내려받은 파일의 1행 제목은 그대로 두세요."]
    rows = {int(r["id"]): dict(r) for r in existing.to_dict("records")}
    order = list(rows)
    adds, n_upd, notes = [], 0, []
    for r in up.to_dict("records"):
        vals = {back[c]: _cell(r.get(c)) for c in use}
        if not any(_norm(v) for v in vals.values()):
            continue
        rid = pd.to_numeric(_norm(r.get(ID_HEAD)), errors="coerce")
        if pd.notna(rid) and int(rid) in rows:
            cur = rows[int(rid)]
            if any(_norm(cur.get(k)) != _norm(v) for k, v in vals.items()):
                cur.update(vals)
                n_upd += 1
        elif pd.notna(rid):
            notes.append(f"ID {int(rid)}은(는) 목록에 없어 새로 추가했어요.")
            adds.append(vals | {"id": None})
        else:
            adds.append(vals | {"id": None})
    out = pd.DataFrame([rows[i] for i in order] + adds)
    return out, len(adds), n_upd, notes
