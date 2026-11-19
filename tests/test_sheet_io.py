import io

import openpyxl
import pandas as pd

from core import sheet_io

HEADS = {"name": "업체명", "phone": "연락처"}


def _edit(data: bytes, fn) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(data))
    fn(wb.active)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_roundtrip_update_and_add():
    df = pd.DataFrame({"id": [1, 2], "name": ["가", "나"], "phone": ["010", ""], "note": ["x", "y"]})
    x = sheet_io.to_xlsx(df, HEADS, "업체")

    def change(ws):
        ws["B2"] = "가나다"          # 1번 이름 바꿈
        ws.append([None, "새업체", "02"])  # 새 줄
        ws.delete_rows(3)           # 2번 줄을 파일에서 뺌 → 지우지 않음
    merged, n_add, n_upd, notes = sheet_io.merge(df, _edit(x, change), HEADS)
    assert (n_add, n_upd) == (1, 1)
    assert list(merged["name"]) == ["가나다", "나", "새업체"]
    assert merged.loc[0, "note"] == "x"  # 파일에 없는 열은 그대로
    assert pd.isna(merged.loc[2, "id"])


def test_no_id_column():
    df = pd.DataFrame({"id": [1], "name": ["가"], "phone": [""]})
    buf = io.BytesIO()
    pd.DataFrame({"업체명": ["a"]}).to_excel(buf, index=False)
    _, a, u, notes = sheet_io.merge(df, buf.getvalue(), HEADS)
    assert (a, u) == (0, 0) and notes


def test_merge_edits_keeps_others_changes():
    from views.common import merge_edits
    base = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    mine = pd.DataFrame({"id": [1, 3, None], "name": ["A", "c", "new"]})   # 1 고침, 2 지움, 새 줄
    latest = pd.DataFrame({"id": [1, 2, 3, 4], "name": ["a", "b", "c2", "d"]})  # 남이 3 고치고 4 추가
    out = merge_edits(base, mine, latest)
    assert list(out["name"]) == ["A", "c2", "d", "new"]


def test_equipment_layout_roundtrip_with_summary_first():
    """2026-11-19: 맨 앞 요약 시트 + No. 열 + 맨 뒤 ID 열이어도 다시 올리면 ID 로 맞춰 반영."""
    heads = {"name": "장비명(한글)", "parent_id": "소속 장비 ID", "qty": "대수"}
    df = pd.DataFrame({"id": [7, 3], "name": ["시스템", "세부"], "parent_id": [None, 7], "qty": [1, 2]})
    x = sheet_io.to_xlsx(df, heads, "장비", levels=[0, 1], id_last=("parent_id",))
    x = sheet_io.add_summary(x, "요약", "제목", [("표", pd.DataFrame({"구분": ["합계"], "대수": [3]}))])
    wb = openpyxl.load_workbook(io.BytesIO(x))
    assert wb.sheetnames[0] == "요약" and wb.active.title == "요약"
    ws = wb["장비"]
    assert [c.value for c in ws[1]] == ["No.", "장비명(한글)", "대수", "ID", "소속 장비 ID"]
    assert [ws.cell(r, 1).value for r in (2, 3)] == [1, 2]
    assert sheet_io.merge(df, x, heads)[1:3] == (0, 0)  # 그대로 올리면 바뀐 것 없음
    ws["C3"] = 5
    buf = io.BytesIO()
    wb.save(buf)
    merged, n_add, n_upd, _ = sheet_io.merge(df, buf.getvalue(), heads)
    assert (n_add, n_upd) == (0, 1) and merged.loc[1, "qty"] == 5
