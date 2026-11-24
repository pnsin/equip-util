"""core.health 데이터 점검."""
import datetime as dt

import pandas as pd

from core import health
from views.export import fill_from_companies

EQ = pd.DataFrame({
    "id": [1, 2, 3, 4], "parent_id": [None, 1, None, None], "in_kpi": [True, False, False, True],
    "category": ["", "", "", "시스템시설"], "acquired_on": [None] * 4, "retired_on": [None] * 4,
    "use": ["시험", "시험", "시험", "제조"],
})
CH = pd.DataFrame({"id": [10], "equip_id": [2]})
COMP = pd.DataFrame({"name": ["가업체", "나업체"], "brn": ["1234567890", ""]})


def _log(i, eid, **kw):
    base = dict(id=i, equip_id=eid, equip_name=f"장비{eid}", start_date=pd.Timestamp("2026-03-03"),
                end_date=pd.Timestamp("2026-03-03"), hours=8, company="", purpose="시험", purpose_detail="",
                chambers="10" if eid == 2 else "", ch_part="", series="", itube_code="A-1", usage_type="내부", brn="")
    return base | kw


def _run(rows):
    return {f["key"]: f for f in health.run(pd.DataFrame(rows), EQ, CH, COMP, {2}, today=dt.date(2026, 11, 20))}


def test_clean_data_has_no_findings():
    assert _run([_log(1, 2), _log(2, 4)]) == {}


def test_missing_equipment_and_bad_dates():
    f = _run([_log(1, 99), _log(2, 1, end_date=pd.Timestamp("2026-03-02")), _log(3, 1, hours=0)])
    assert list(f["no_equip"]["rows"]["ID"]) == [1]
    assert list(f["bad_date"]["rows"]["ID"]) == [2]
    assert list(f["no_hours"]["rows"]["ID"]) == [3]


def test_over_24h_skips_chargers_and_not_kpi():
    f = _run([_log(1, 1, hours=30), _log(2, 2, hours=30), _log(3, 3)])
    assert list(f["over_24h"]["rows"]["ID"]) == [1]
    assert list(f["not_kpi"]["rows"]["ID"]) == [3]  # 2 는 상위 1 이 가동률산정 Y


def test_charger_without_chamber():
    f = _run([_log(1, 2, chambers=""), _log(2, 4, chambers="10")])
    assert list(f["no_chamber"]["rows"]["ID"]) == [1]
    assert list(f["other_chamber"]["rows"]["ID"]) == [2]


def test_duplicates_only_when_saved_separately():
    same = dict(company="가업체", usage_type="외부", brn="1234567890")
    one_batch = [_log(1794911087958000, 1, **same), _log(1794911087958001, 1, **same)]
    assert "dup" not in _run(one_batch)
    two_saves = [_log(1794911087958000, 1, **same), _log(1795000000000000, 1, **same)]
    assert len(_run(two_saves)["dup"]["rows"]) == 2


def test_itube_and_brn():
    f = _run([_log(1, 1, itube_code=""), _log(2, 4, itube_code=""),
              _log(3, 1, usage_type="외부", company="가업체"), _log(4, 1, usage_type="외부", company="나업체"),
              _log(5, 1, usage_type="외부", company="")])
    assert list(f["no_itube"]["rows"]["ID"]) == [1]
    assert list(f["no_itube_facility"]["rows"]["ID"]) == [2]
    assert list(f["ext_no_brn"]["rows"]["ID"]) == [4]  # 가업체는 업체 목록에 번호가 있음
    assert list(f["ext_no_company"]["rows"]["ID"]) == [5]


def test_export_fills_brn_from_company_list():
    sel = pd.DataFrame({"company": ["가업체", "나업체"], "brn": ["", "999"], "industry": ["", ""],
                        "item": ["", ""], "sub_item": ["", ""]})
    out = fill_from_companies(sel, COMP.assign(industry="", item="", sub_item=""))
    assert list(out["brn"]) == ["1234567890", "999"]


def test_device_without_use_is_hidden_from_status_board():
    eq = EQ.assign(use=["시험", "시험", "시험", ""])
    got = {f["key"] for f in health.run(pd.DataFrame([_log(1, 4)]), eq, CH, COMP, {2}, today=dt.date(2026, 11, 20))}
    assert "no_group" in got


def test_confirmed_note_rows_move_to_done_list():
    rows = [_log(1, 4, itube_code=""), _log(2, 4, itube_code=""),
            _log(3, 1, usage_type="외부", company="나업체"), _log(4, 1, usage_type="외부", company="나업체")]
    found = health.run(pd.DataFrame(rows), EQ, CH, COMP, {2}, today=dt.date(2026, 11, 20))
    ok = {"no_itube_facility": {"1": "2026-11-24"}, "ext_no_brn": {"3": "x"}}  # '확인' 항목은 확인으로 못 내림
    show, done = health.split_confirmed(found, ok)
    s = {f["key"]: f for f in show}
    assert list(s["no_itube_facility"]["rows"]["ID"]) == [2]
    assert list(s["ext_no_brn"]["rows"]["ID"]) == [3, 4]
    assert [(f["key"], list(f["rows"]["ID"]), list(f["rows"]["확인"])) for f in done] == [
        ("no_itube_facility", [1], ["2026-11-24"])]
    assert health.summary(show)[1] == 1 and health.summary(done) == (0, 1)
    assert health.brn_needed(show).to_dict("records") == [{"업체": "나업체", "실적": 2}]


def test_off_days_only_and_parent_child():
    # 2026-03-01 일요일 · 03-02 삼일절 대체공휴일 → 가동률 0시간
    f = _run([_log(1, 4, start_date=pd.Timestamp("2026-03-01"), end_date=pd.Timestamp("2026-03-02")),
              _log(2, 1), _log(3, 2), _log(4, 1, start_date=pd.Timestamp("2026-04-01"),
                                              end_date=pd.Timestamp("2026-04-01"))])
    assert list(f["off_days_only"]["rows"]["ID"]) == [1]
    assert sorted(f["parent_child"]["rows"]["ID"]) == [2, 3]  # 4는 다른 날


def test_fee_without_usage():
    led = pd.DataFrame({"id": [1, 2, 3], "tax_date": [dt.date(2026, 3, 20), dt.date(2026, 3, 20), dt.date(2026, 3, 20)],
                        "brn": ["123-45-67890", "999-99-99999", "999-99-99999"], "company": ["가업체", "다업체", "다업체"],
                        "item": ["시험료", "시험료", "현장실습"], "supply": [100, 200, 300], "staff": ["", "", ""],
                        "report_cat": ["", "", ""]})
    eq = EQ.assign(report_cat=["환경시험", "", "", ""], group=["", "", "", ""])
    rows = [_log(1, 1, company="가업체", usage_type="외부", brn="1234567890")]
    got = health.run(pd.DataFrame(rows), eq, CH, COMP, {2}, today=dt.date(2026, 11, 20),
                     ledger=led.assign(report_cat=["환경시험", "환경시험", ""]))
    fee = next(f for f in got if f["key"] == "fee_no_usage")
    assert list(fee["rows"]["ID"]) == [2]  # 1은 실적 있음, 3은 교육(기타)
