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


def to_xlsx(df: pd.DataFrame, heads: dict[str, str], sheet: str) -> bytes:
    """heads: 내부 열 → 엑셀 열 제목 (id 는 자동으로 맨 앞)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    cols = ["id"] + [c for c in heads if c != "id"]
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append([ID_HEAD] + [heads[c] for c in cols[1:]])
    for r in df.to_dict("records"):
        ws.append([_cell(r.get(c)) for c in cols])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="26324A")
    ws["A1"].fill = PatternFill("solid", fgColor="8A97A8")
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col[:200])
        ws.column_dimensions[col[0].column_letter].width = min(40, max(8, width * 1.6))
    ws.freeze_panes = "B2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _norm(v) -> str:
    v = _cell(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def merge(existing: pd.DataFrame, data: bytes, heads: dict[str, str]) -> tuple[pd.DataFrame, int, int, list[str]]:
    """올린 엑셀을 기존 목록에 합칩니다 → (합친 목록, 추가 수, 수정 수, 안내)."""
    up = pd.read_excel(io.BytesIO(data), dtype=object)
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
