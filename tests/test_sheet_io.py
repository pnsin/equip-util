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


def test_equip_count_matches_reference_6_15():
    """사용자 기준표(문백 6종 15대): 양극·음극 짝 = 1대, 대수 0 은 빼고, 세부장비가 모두 0 이면 장비 자신."""
    from core import equip_count
    rows = [(1, "전극제조 시스템", "A", None, 1)] + [
        (10 + i, f"{n}({s})", "", 1, 1) for i, (n, s) in enumerate(
            [(n, s) for n in ("5L 믹서", "50L 믹서", "전극 코터", "롤프레스", "슬리터") for s in ("양극", "음극")])] + [
        (30, "바인더믹서", "", 1, 0), (31, "건조오븐", "", 1, 0), (32, "초순수", "", 1, 0),
        (2, "조립 시스템", "B", None, 1), (40, "전극 노칭기(양극)", "", 2, 1), (41, "전극 노칭기(음극)", "", 2, 1),
        (42, "셀 조립장치", "", 2, 1), (43, "핫프레스", "", 2, 1), (44, "디개싱", "", 2, 1),
        (3, "충방전기", "C", None, 1), (50, "활성화", "", 3, 1), (51, "셀 평가", "", 3, 1), (52, "에이징", "", 3, 1),
        (4, "항온항습", "", None, 1), (60, "클린룸", "", 4, 0), (61, "드라이룸", "", 4, 0),
        (5, "PV 챔버", "D", None, 1), (6, "ESS 챔버", "E", None, 1),
        (7, "방폭챔버 묶음", "", None, 4), (70, "방폭챔버", "F", 7, 1), (71, "방폭챔버", "G", 7, 1)]
    eq = pd.DataFrame(rows, columns=["id", "name", "code", "parent_id", "qty"])
    u = equip_count.units(eq).set_index("id")["대수"]
    assert dict(u[[1, 2, 3, 4, 5, 6]]) == {1: 5, 2: 4, 3: 3, 4: 1, 5: 1, 6: 1}  # 6종 15대
    assert set(u.index) == {1, 2, 3, 4, 5, 6, 7} and u[7] == 2  # 묶음은 1종, 대수는 안의 장비 수


def test_retired_rate_items_hidden_from_quote_picker():
    import pandas as pd
    from core import quotes
    rates = pd.DataFrame([
        {"id": 1, "equip_id": None, "name": "열충격시험기", "spec": "", "unit": "hr", "price_req": 12000,
         "price_self": None, "note": "", "retired": "Y"},
        {"id": 2, "equip_id": None, "name": "방폭룸", "spec": "", "unit": "hr", "price_req": 220000,
         "price_self": None, "note": "", "retired": ""}])
    eq = pd.DataFrame(columns=["id", "name", "short", "group"])
    dev, ex = quotes.rate_table(eq, rates)
    assert len(ex) == 2 and list(ex["retired"]) == ["Y", ""]
    assert set(quotes.pick_options(dev, ex)) == {"방폭룸"}
