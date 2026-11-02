"""장비 현황 엑셀(예: '장비 종 대수 분류정리' 전수조사 탭)에서 장비 목록을 읽습니다."""
from __future__ import annotations

import io

import openpyxl

from core.db import to_str

NAME_COLS = ("장비명(한글)", "장비명", "세부장비")
CODE_COLS = ("ITUBE번호", "장비번호")


def _pick_sheet(wb):
    """'전수조사' 탭이 있으면 그것을, 없으면 장비명 열이 있는 첫 탭."""
    order = sorted(wb.worksheets, key=lambda ws: 0 if "전수조사" in ws.title else 1)
    for ws in order:
        head = [to_str(c) for c in next(ws.iter_rows(max_row=1, values_only=True), ())]
        if any(n in head for n in NAME_COLS):
            return ws, head
    raise ValueError("장비명(한글) 또는 장비명 열이 있는 시트를 찾지 못했습니다.")


def read_equipment_file(data: bytes) -> tuple[list[dict], list[str], str]:
    """(가져올 장비, 불용이라 뺀 장비 이름, 읽은 시트 이름)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws, head = _pick_sheet(wb)
    col = {h: i for i, h in enumerate(head) if h}
    name_col = next(n for n in NAME_COLS if n in col)
    code_col = next((c for c in CODE_COLS if c in col), None)
    note_cols = [h for h in head if h.startswith("비고")]

    def get(row, h):
        i = col.get(h)
        return to_str(row[i]) if i is not None and i < len(row) else ""

    out, retired = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = get(row, name_col)
        if not name:
            continue
        if any("불용" in get(row, h) for h in note_cols):
            retired.append(name)
            continue
        kind_raw = get(row, "장비구분")
        info = [get(row, h) for h in ("주장비(ITUBE)", "구분", "장비용도", "장비위치")]
        out.append({
            "name": name,
            "code": get(row, code_col) if code_col else "",
            "kind": "주장비" if kind_raw in ("", "주장비") else "부장비",
            "note": " / ".join(v for v in info if v and v != "-" and v != name),
        })
    return out, retired, ws.title
