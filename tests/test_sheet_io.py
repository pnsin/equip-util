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
