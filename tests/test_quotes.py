"""견적서: 금액 계산, 직접 입력 금액 유지, 단가표 합치기, 원래 양식 칸 채우기."""
import datetime as dt
import io

import openpyxl
import pandas as pd

from core import quote_doc as Q
from core import quotes


def _mfg(**kw):
    q = {"form": "제조", "no": "RAT-2611-143", "date": "2026-11-03", "company": "주식회사 아모그린텍",
         "contact": "유 정우 대리님", "phone": "010-2551-3570", "title": "전극 장비 사용", "writer": "박노신",
         "writer_title": "선임연구원", "email": "pnsin@cbtp.or.kr",
         "lines": [{"name": "슬리터", "spec": "400m", "note": "양극 집전체", "qty": 3, "unit": "hr", "price": 101000}],
         "extras": []}
    q.update(kw)
    return q


def test_totals_match_sample_quote():
    # RAT-2610-143: 3hr × 101,000 = 303,000 → 부가세 포함 333,300
    t = Q.totals(_mfg())
    assert t["eq"] == 303000 and t["final"] == 303000 and t["vat"] == 333300


def test_test_form_totals_match_sample():
    # RAT-2601-005: 1 × 500h × 15,000 × 1.0 = 7,500,000, 할인 20%, 기술료 122,000
    q = {"form": "시험", "lines": [{"spec": "리드탭", "name": "온도사이클시험", "count": 1, "qty": 500,
                                   "price": 15000, "difficulty": 1}],
         "disc1": 20, "extras": [{"name": "시험데이터", "qty": 1, "price": 100000},
                                 {"name": "엔지니어지원비", "qty": 1, "price": 22000}]}
    t = Q.totals(q)
    assert (t["eq"], t["d1"], t["after"], t["extras"], t["final"], t["vat"]) == \
        (7500000, 1500000, 6000000, 122000, 6122000, 6734200)


def test_manual_amount_and_rounddown():
    q = _mfg(lines=[{"name": "드라이룸", "qty": 1, "unit": "day", "amount": 500500}], disc1=10)
    t = Q.totals(q)
    assert t["eq"] == 500500 and t["d1"] == 50050 and t["final"] == 450000


def test_fill_writes_values_into_original_cells():
    wb = openpyxl.load_workbook(io.BytesIO(Q.fill_xlsx(_mfg())))
    ws = wb.active
    assert ws["C9"].value == "NO.  : RAT-2611-143"
    assert ws["H9"].value.endswith("2026.11.03.")
    assert ws["C19"].value == "슬리터" and ws["I19"].value == 303000 and ws["J49"].value == 333300
    assert not any(isinstance(c.value, str) and c.value.startswith("=") for row in ws.iter_rows() for c in row)


def test_fill_test_form_customer_page_only():
    q = {"form": "시험", "no": "RAT-2601-005", "date": dt.date(2026, 1, 14), "company": "네패스야하드",
         "lines": [{"spec": "리드탭", "name": "온도사이클시험", "count": 1, "qty": 500, "price": 15000,
                    "difficulty": 1}], "extras": []}
    ws = openpyxl.load_workbook(io.BytesIO(Q.fill_xlsx(q, "customer"))).active
    assert "$A$55" in ws.print_area and ws["C63"].value == "NO.  : RAT-2601-005"
    assert ws["G74"].value == 7500000 and ws["I9"].value.endswith("2026. 1. 14.")


def test_line_edits_fill_price_and_keep_manual():
    opts = {"슬리터 · 오창": {"equip_id": 74, "name": "슬리터", "spec": "50Ah", "unit": "hr",
                            "price_req": 101000, "price_self": 45000}}
    prev = [quotes.new_line("제조")]
    e = dict(prev[0], pick="슬리터 · 오창", qty=3)
    out = quotes.apply_line_edits("제조", prev, [e], opts)[0]
    assert out["name"] == "슬리터" and out["price"] == 101000 and out["amount"] == 303000 and not out["manual"]
    # 직접 사용으로 바꾸면 직접 단가
    out2 = quotes.apply_line_edits("제조", [out], [dict(out, mode="직접")], opts)[0]
    assert out2["price"] == 45000 and out2["amount"] == 135000
    # 금액을 직접 고치면 그대로, 사용량을 바꿔도 그대로
    out3 = quotes.apply_line_edits("제조", [out2], [dict(out2, amount=100000)], opts)[0]
    assert out3["manual"] and out3["amount"] == 100000
    out4 = quotes.apply_line_edits("제조", [out3], [dict(out3, qty=10)], opts)[0]
    assert out4["amount"] == 100000
    # '직접'을 끄면 다시 계산
    out5 = quotes.apply_line_edits("제조", [out4], [dict(out4, manual=False)], opts)[0]
    assert not out5["manual"] and out5["amount"] == 450000


def test_pasted_row_with_amount_is_manual():
    out = quotes.apply_line_edits("제조", [], [{"name": "클린룸", "qty": 1, "price": None, "amount": 300000}], {})[0]
    assert out["manual"] and out["amount"] == 300000 and out["key"]


def test_rate_table_skips_side_variants_and_shows_missing():
    eq = pd.DataFrame([
        {"id": 49, "name": "슬리터", "parent_id": pd.NA, "short": "슬리터", "group": "5Ah 생산", "retired_on": pd.NaT},
        {"id": 50, "name": "슬리터(양극)", "parent_id": 49, "short": "슬리터(양극)", "group": "5Ah 생산",
         "retired_on": pd.NaT},
        {"id": 52, "name": "바인더믹서", "parent_id": pd.NA, "short": "바인더믹서", "group": "5Ah 생산",
         "retired_on": pd.NaT}])
    rates = pd.DataFrame([{"id": 1, "equip_id": 49, "name": "", "spec": "", "unit": "hr", "price_req": 84000,
                           "price_self": 42000, "note": "", "order": 1},
                          {"id": 2, "equip_id": None, "name": "클린룸 (5Ah)", "spec": "", "unit": "hr",
                           "price_req": 117000, "price_self": None, "note": "", "order": 2}])
    dev, ex = quotes.rate_table(eq, rates)
    assert list(dev["equip_id"]) == [49, 52]
    assert not quotes.is_missing(dev.iloc[0].to_dict()) and quotes.is_missing(dev.iloc[1].to_dict())
    assert list(ex["name"]) == ["클린룸 (5Ah)"]
    opts = quotes.pick_options(dev, ex)
    assert quotes.option_price(opts["클린룸 (5Ah)"], "직접") == 117000


def test_numbering():
    assert Q.make_no(dt.date(2026, 11, 4), 145) == "RAT-2611-145"
    assert Q.next_seq(["144", "126-1", "9"]) == 145
    assert quotes.seq_of("RAT-2610-126-1") == "126-1" and quotes.seq_of("RAT-2611-045") == "45"
    assert quotes.requester_of("유 정우 대리님") == "유정우"


def test_quote_save_and_undo(tmp_path, monkeypatch):
    from core import db
    store = db.CsvStore(str(tmp_path))
    monkeypatch.setattr(db, "get_store", lambda: store)
    rid = db.save_quote({"no": "RAT-2611-145", "seq": "145", "issued_on": "2026-11-04", "company": "A"})
    assert list(db.load_quotes()["no"]) == ["RAT-2611-145"]
    db.save_quote({"id": rid, "no": "RAT-2611-145", "seq": "145", "issued_on": "2026-11-04", "company": "B"})
    assert list(db.load_quotes()["company"]) == ["B"]
    db.undo_last()
    assert list(db.load_quotes()["company"]) == ["A"]
