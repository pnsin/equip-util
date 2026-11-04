"""기간 실적 나누기 · 충방전기 하루 8h 계산 · 챔버 현황 테스트."""
import datetime as dt

import pandas as pd
import pytest

from core import calc, chargers, period, rules

D = dt.date


def test_split_period_by_month_and_weekdays_only():
    parts = period.split_period(D(2026, 11, 4), D(2027, 1, 15), 8, skip_off=True)
    assert [(p["start_date"], p["end_date"]) for p in parts] == [
        (D(2026, 11, 4), D(2026, 11, 30)), (D(2026, 12, 1), D(2026, 12, 31)), (D(2027, 1, 1), D(2027, 1, 15))]
    assert parts[1]["days"] == 22  # 12월 평일 23일 - 성탄절
    assert parts[0]["hours"] == 8 * parts[0]["days"]
    for p in parts:  # 달마다 나누면 i-Tube 규칙(같은 해 · 2개월 이내)에 걸리지 않음
        rec = {"start_date": p["start_date"], "end_date": p["end_date"], "hours": p["hours"]}
        assert not [e for e in rules.validate(rec) if "규칙 7" in e or "규칙 8" in e or "사용기간" in e]


def test_split_period_keeps_weekends_when_asked():
    parts = period.split_period(D(2026, 11, 7), D(2026, 11, 8), 24, skip_off=False)  # 토·일
    assert parts == [{"start_date": D(2026, 11, 7), "end_date": D(2026, 11, 8), "hours": 48, "days": 2}]
    assert period.split_period(D(2026, 11, 7), D(2026, 11, 8), 8, skip_off=True) == []


def test_plan_changes_reuses_same_month_rows():
    old = pd.DataFrame([{"id": 1, "start_date": pd.Timestamp("2026-11-04")},
                        {"id": 2, "start_date": pd.Timestamp("2026-12-01")},
                        {"id": 3, "start_date": pd.Timestamp("2027-01-01")}])
    chunks = period.split_period(D(2026, 11, 4), D(2026, 12, 10), 8, True)  # 1월 줄은 없어짐
    upd, add, gone = period.plan_changes(old, chunks, {"equip_id": 5}, "S1")
    assert set(upd) == {1, 2} and add == [] and gone == [3]
    assert upd[2]["end_date"] == D(2026, 12, 10) and upd[2]["series"] == "S1"


def _log(i, s, e, h, eid=7, hol="N"):
    return dict(id=i, equip_id=eid, start_date=pd.Timestamp(s), end_date=pd.Timestamp(e), include_holidays=hol,
                hours=h, fee=0)


def test_charger_day_capped_at_8h_and_weekends_dropped():
    # 같은 충방전기 챔버 3개가 같은 날 8h씩 → 장비 시간은 하루 8h
    logs = pd.DataFrame([_log(i, "2026-11-02", "2026-11-02", 8) for i in (1, 2, 3)]
                        + [_log(4, "2026-11-07", "2026-11-07", 8, hol="Y")])  # 토요일
    d = calc.expand_daily(logs, "spread", {7: 8.0})
    by_day = d.groupby(d["day"].dt.date)["hours"].sum()
    assert by_day[D(2026, 11, 2)] == pytest.approx(8)
    assert by_day[D(2026, 11, 7)] == pytest.approx(0)
    # 다른 장비는 그대로 더함
    other = calc.expand_daily(logs.assign(equip_id=9), "spread", {7: 8.0})
    assert other["hours"].sum() == pytest.approx(32)


def test_bookings_merge_series_and_status():
    logs = pd.DataFrame([
        dict(id=1, equip_id=7, start_date=pd.Timestamp("2026-11-03"), end_date=pd.Timestamp("2026-11-30"),
             chambers="5,6", series="S1", company="KBST", purpose="시험", detail="", created_by="김", ch_part=""),
        dict(id=2, equip_id=7, start_date=pd.Timestamp("2026-12-01"), end_date=pd.Timestamp("2026-12-31"),
             chambers="5,6", series="S1", company="KBST", purpose="시험", detail="", created_by="김", ch_part=""),
        dict(id=3, equip_id=7, start_date=pd.Timestamp("2026-12-10"), end_date=pd.Timestamp("2026-12-20"),
             chambers="7", series="", company="NBTS", purpose="시험", detail="", created_by="", ch_part="1-8"),
    ])
    bk = chargers.bookings(logs)
    s1 = bk[bk["key"] == "S1"]
    assert len(s1) == 2 and s1["start"].min() == D(2026, 11, 3) and s1["end"].max() == D(2026, 12, 31)
    ch = pd.DataFrame({"id": [5, 6, 7, 8], "center": "제조검증", "unit": "5V50A", "cycler": "cycler 3",
                       "chamber": ["chamber5", "chamber6", "chamber7", "chamber8"], "channels": "1-16", "ch_count": 16})
    st_ = chargers.status(ch, bk, D(2026, 11, 4))
    assert st_.loc[0, "now"]["company"] == "KBST"
    assert st_.loc[2, "now"] is None and st_.loc[2, "next"]["company"] == "NBTS"
    assert st_.loc[3, "now"] is None and st_.loc[3, "next"] is None
    assert chargers.to_excel(st_, D(2026, 11, 4))[:2] == b"PK"


def test_chargers_under_same_parent_share_8h():
    logs = pd.DataFrame([_log(1, "2026-11-02", "2026-11-02", 8, eid=82), _log(2, "2026-11-02", "2026-11-02", 8, eid=83)])
    d = calc.expand_daily(logs, "spread", {82: (8.0, 6), 83: (8.0, 6)})
    assert d["hours"].sum() == pytest.approx(8)
    assert d.loc[d["equip_id"] == 82, "hours"].sum() == pytest.approx(4)
