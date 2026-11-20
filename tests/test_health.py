"""core.health 데이터 점검."""
import datetime as dt

import pandas as pd

from core import health
from views.export import fill_from_companies

EQ = pd.DataFrame({
    "id": [1, 2, 3, 4], "parent_id": [None, 1, None, None], "in_kpi": [True, False, False, True],
    "category": ["", "", "", "시스템시설"], "acquired_on": [None] * 4, "retired_on": [None] * 4,
})
CH = pd.DataFrame({"id": [10], "equip_id": [2]})
COMP = pd.DataFrame({"name": ["가업체", "나업체"], "brn": ["1234567890", ""]})


def _log(i, eid, **kw):
    base = dict(id=i, equip_id=eid, equip_name=f"장비{eid}", start_date=pd.Timestamp("2026-03-02"),
                end_date=pd.Timestamp("2026-03-02"), hours=8, company="", purpose="시험", purpose_detail="",
                chambers="10" if eid == 2 else "", ch_part="", series="", itube_code="A-1", usage_type="내부", brn="")
    return base | kw


def _run(rows):
    return {f["key"]: f for f in health.run(pd.DataFrame(rows), EQ, CH, COMP, {2}, today=dt.date(2026, 11, 20))}


def test_clean_data_has_no_findings():
    assert _run([_log(1, 2), _log(2, 4)]) == {}


def test_missing_equipment_and_bad_dates():
    f = _run([_log(1, 99), _log(2, 1, end_date=pd.Timestamp("2026-03-01")), _log(3, 1, hours=0)])
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
