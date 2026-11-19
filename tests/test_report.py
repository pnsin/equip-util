import pandas as pd

from core import report


def test_equip_cats_inherit_and_group():
    eq = pd.DataFrame({"id": [1, 2, 3, 4, 5], "parent_id": [None, 1, None, 3, None],
                       "group": ["5Ah 생산", "5Ah 생산", "충방전시험기", "충방전시험기", "알수없음"],
                       "report_cat": ["", "", "환경시험", "", ""]})
    c = report.equip_cats(eq)
    assert c == {1: "5Ah 제조", 2: "5Ah 제조", 3: "환경시험", 4: "환경시험", 5: "기타"}


def test_fee_cat_rules():
    assert report.fee_cat("충방전기 시험수수료") == "충방전시험기"
    assert report.fee_cat("50Ah 현장실습(1)") == "기타"
    assert report.fee_cat("열충격") == "환경시험"
    assert report.fee_cat("충돌, 낙하 장비수수료(RG3)") == "사용환경모사"
    assert report.fee_cat("SMT사용료") == "SMT"
    assert report.fee_cat("") == "기타"
    assert report.fee_cat("한국배터리안전연구원 주식회사", "이상헌") == "진동시험"
    assert report.fee_cat("충방전기 시험수수료", "이상헌") == "충방전시험기"
    assert report.fee_cat("배터리아카데미 6기(1)", "이상헌") == "기타"


def test_kpi_fallback_and_year():
    k = report.kpi({}, 2026)
    assert k["fee"] == 500_000_000 and k["util_total"] == 64 and not k["year_set"]
    cfg = {"kpi": {"2026": {"fee": 600_000_000, "util_total": 70}}}
    k27 = report.kpi(cfg, 2027)
    assert k27["fee"] == 600_000_000 and k27["util_total"] == 70 and not k27["year_set"]
    assert report.kpi(cfg, 2026)["year_set"]


def test_ledger_team_rule():
    import datetime as dt
    from core.fee_ledger import ours
    assert ours("배터리산업팀", dt.date(2026, 3, 1))
    assert not ours("차세대전지팀", dt.date(2026, 9, 28))
    assert ours("차세대전지팀", dt.date(2025, 7, 1))
    assert not ours("다른팀", dt.date(2025, 7, 1))
