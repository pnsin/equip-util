"""핵심 계산·검사·저장 로직 테스트 (구글 시트 없이 CSV 저장소로 실행)."""
import datetime as dt

import pandas as pd
import pytest

from core import calc, db, itube, rules

D = dt.date


def _log(**kw):
    base = dict(id=1, equip_id=1, start_date=pd.Timestamp("2026-07-01"), end_date=pd.Timestamp("2026-07-01"),
                include_holidays="Y", hours=10, fee=0)
    base.update(kw)
    return base


def test_year_fraction_leap_and_split():
    assert calc.year_fraction(D(2026, 1, 1), D(2026, 12, 31)) == pytest.approx(1.0)
    assert calc.year_fraction(D(2028, 1, 1), D(2028, 12, 31)) == pytest.approx(1.0)  # 윤년
    assert calc.year_fraction(D(2026, 12, 31), D(2027, 1, 1)) == pytest.approx(1 / 365 * 2)


def test_expand_daily_spreads_across_month_boundary():
    logs = pd.DataFrame([_log(start_date=pd.Timestamp("2026-07-30"), end_date=pd.Timestamp("2026-08-02"), hours=8)])
    d = calc.expand_daily(logs, "spread")
    assert len(d) == 4 and d["hours"].sum() == pytest.approx(8)
    july = calc.window(d, D(2026, 7, 1), D(2026, 7, 31))
    assert july["hours"].sum() == pytest.approx(4)


def test_expand_daily_skips_weekend_when_N():
    # 2026-08-01(토)~08-03(월): 휴무 제외면 월요일 하루에 전부
    logs = pd.DataFrame([_log(start_date=pd.Timestamp("2026-08-01"), end_date=pd.Timestamp("2026-08-03"),
                              include_holidays="N", hours=6)])
    d = calc.expand_daily(logs, "spread")
    assert list(d["day"].dt.date) == [D(2026, 8, 3)]


def test_available_hours_respects_acquired_and_retired():
    row = pd.Series({"acquired_on": pd.Timestamp("2026-07-01"), "retired_on": None, "annual_hours": None})
    h = calc.available_hours(row, D(2026, 1, 1), D(2026, 12, 31), 2000)
    assert h == pytest.approx(2000 * 184 / 365)


def _valid():
    return dict(purpose="시험", usage_type="외부", company="가나다", brn="123-45-67890",
                industry="전기전자", item="이차전지_에너지", sub_item=rules.seed.SUBITEMS["이차전지_에너지"][0],
                start_date=D(2026, 7, 1), end_date=D(2026, 7, 1), hours=5, fee=0)


def test_validate_ok_and_errors():
    assert rules.validate(_valid()) == []
    assert any("같은 해" in e for e in rules.validate(dict(_valid(), end_date=D(2027, 1, 2), start_date=D(2026, 12, 30))))
    assert any("10자리" in e for e in rules.validate(dict(_valid(), brn="12345")))
    assert any("정수" in e for e in rules.validate(dict(_valid(), hours=1.5)))
    assert any("24h" in e for e in rules.validate(dict(_valid(), hours=25)))


def test_itube_roundtrip():
    rec = dict(_valid(), equip_name="코인셀 충방전기", equip_code="NFEC-1", equip_kind="주장비", samples=2,
               disclose="N", include_holidays="Y", detail="", dept="", product="", purpose_detail="", etc="")
    data = itube.make_itube_file([rec], [("코인셀 충방전기", "NFEC-1")])
    rows, master = itube.read_itube_file(data)
    assert len(rows) == 1
    r = rows[0]
    assert (r["equip_name"], r["hours"], r["brn"], r["start_date"]) == ("코인셀 충방전기", 5, "1234567890", D(2026, 7, 1))
    assert ("코인셀 충방전기", "NFEC-1") in master


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = db.CsvStore(str(tmp_path))
    monkeypatch.setattr(db, "get_store", lambda: s)
    db.clear_caches()
    s.rewrite("equipment", db._rows("equipment", [{"id": 1, "name": "장비A", "in_kpi": True}]))
    yield s
    db.clear_caches()


def test_update_and_delete_touch_only_target_rows(store):
    rec = dict(equip_id=1, start_date=D(2026, 7, 1), end_date=D(2026, 7, 1), hours=3, purpose="시험",
               usage_type="내부", company="")
    db.insert_logs([rec, dict(rec, hours=4), dict(rec, hours=5)], "tester")
    ids = list(store.read("usage")["id"])
    assert db.update_logs({int(ids[0]): {"hours": 7}}) == 1
    assert db.delete_logs([int(ids[1])]) == 1
    df = store.read("usage").set_index("id")
    assert list(df.index) == [ids[0], ids[2]]
    assert df.loc[ids[0], "hours"] == "7" and df.loc[ids[2], "hours"] == "5"
    assert df.loc[ids[0], "created_by"] == "tester"


def test_update_missing_row_is_ignored(store):
    assert db.update_logs({999: {"hours": 1}}) == 0


class _FakeWs:
    id = 7

    def __init__(self, ids):
        self.ids = ids
        self.updates = None

    def col_values(self, n):
        return self.ids

    def batch_update(self, data, value_input_option=None):
        self.updates = data


class _FakeSs:
    def __init__(self):
        self.body = None

    def batch_update(self, body):
        self.body = body


def test_sheet_store_row_level_ops():
    s = object.__new__(db.SheetStore)
    s.ws = {"usage": _FakeWs(["ID", "100", "200", "300"])}
    s.ss = _FakeSs()
    n = len(db.cols("usage"))
    assert s.update_rows("usage", {"200": ["200"] + [""] * (n - 1), "999": ["x"] * n}) == 1
    assert s.ws["usage"].updates[0]["range"].startswith("A3:")
    assert s.delete_ids("usage", ["100", "300"]) == 2
    starts = [r["deleteDimension"]["range"]["startIndex"] for r in s.ss.body["requests"]]
    assert starts == [3, 1]  # 아래 행부터


def test_same_progress_end_clips_previous_period():
    import datetime as dt
    from core.calc import same_progress_end
    # 4분기를 11/02까지 보면 3분기는 08/02까지
    assert same_progress_end(dt.date(2026, 10, 1), dt.date(2026, 11, 2), dt.date(2026, 12, 31),
                             dt.date(2026, 7, 1), dt.date(2026, 9, 30)) == dt.date(2026, 8, 2)
    # 끝난 기간은 그대로
    assert same_progress_end(dt.date(2026, 7, 1), dt.date(2026, 9, 30), dt.date(2026, 9, 30),
                             dt.date(2026, 4, 1), dt.date(2026, 6, 30)) == dt.date(2026, 6, 30)
    # 3/31까지 본 1분기 → 직전 4분기(92일)를 넘지 않음
    assert same_progress_end(dt.date(2027, 1, 1), dt.date(2027, 1, 31), dt.date(2027, 3, 31),
                             dt.date(2026, 10, 1), dt.date(2026, 12, 31)) == dt.date(2026, 10, 31)
