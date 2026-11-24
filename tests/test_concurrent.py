"""두 사람이 동시에 고칠 때 (2026-11-24): 같은 칸을 먼저 고친 사람의 내용이 지워지지 않게."""
import datetime as dt

import pandas as pd
import pytest

from core import cs, db


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = db.CsvStore(str(tmp_path))
    monkeypatch.setattr(db, "get_store", lambda: s)
    db.clear_caches()
    s.rewrite("equipment", db._rows("equipment", [{"id": 1, "name": "장비A", "in_kpi": True},
                                                  {"id": 2, "name": "장비B", "in_kpi": True}]))
    yield s
    db.clear_caches()


class Sessions:
    """화면 두 개 (사람 두 명). with people.a: … 안에서 한 일은 A의 화면에서 한 것."""

    def __init__(self, monkeypatch):
        self.states = {"a": {}, "b": {}}
        self.mp = monkeypatch
        self.now = None

    def __getattr__(self, name):
        states, mp = self.states, self.mp

        class Ctx:
            def __enter__(self_):
                mp.setattr(db, "_state", lambda: states[name])

            def __exit__(self_, *a):
                return False
        return Ctx()


@pytest.fixture
def people(monkeypatch):
    return Sessions(monkeypatch)


def _rec(company, hours=5, day=dt.date(2026, 11, 3)):
    return {"equip_id": 1, "company": company, "usage_type": "외부", "purpose": "시험", "start_date": day,
            "end_date": day, "hours": hours, "include_holidays": "N"}


def _logs():
    return db.load_logs().set_index("id")


def test_same_field_stops_second_save(store, people):
    db.insert_logs([_rec("가"), _rec("나")])
    ids = list(_logs().index)
    x, y = ids[0], ids[1]
    with people.a:
        _logs()  # A가 화면을 엶
    with people.b:
        _logs()  # B도 같은 때 엶
    with people.a:
        db.update_logs({x: {"hours": 7}})
    with people.b:  # B는 예전 화면(5h) 그대로 같은 실적의 시간을 8로
        with pytest.raises(db.Conflict) as e:
            db.update_logs({x: {"hours": 8}})
        assert "다른 분이 방금 이 실적을 고쳤어요" in str(e.value)
        assert db.to_num(_logs().at[x, "hours"]) == 7  # A가 고친 값이 그대로
        db.update_logs({y: {"hours": 9}})  # 다른 실적은 알림 없이 저장
        assert db.to_num(_logs().at[y, "hours"]) == 9
        db.update_logs({x: {"company": "다"}})  # 같은 실적이라도 A가 안 건드린 칸만 바꾸면 저장
        assert (_logs().at[x, "company"], db.to_num(_logs().at[x, "hours"])) == ("다", 7)


def test_own_saves_never_conflict(store, people):
    db.insert_logs([_rec("가")])
    x = list(_logs().index)[0]
    with people.a:
        _logs()
        db.update_logs({x: {"hours": 6}})
        db.update_logs({x: {"hours": 7}})
        db.update_logs({x: {"hours": 8}})
        assert db.to_num(_logs().at[x, "hours"]) == 8


def test_reload_lets_save_through(store, people):
    db.insert_logs([_rec("가")])
    x = list(_logs().index)[0]
    with people.b:
        _logs()
    with people.a:
        _logs()
        db.update_logs({x: {"hours": 7}})
    with people.b:
        with pytest.raises(db.Conflict):
            db.update_logs({x: {"hours": 8}})
        db.reset_seen()  # '새로 불러오기'
        _logs()
        db.update_logs({x: {"hours": 8}})
        assert db.to_num(_logs().at[x, "hours"]) == 8


def test_delete_after_other_edit_and_edit_after_other_delete(store, people):
    db.insert_logs([_rec("가"), _rec("나")])
    x, y = list(_logs().index)
    with people.a:
        _logs()
    with people.b:
        _logs()
    with people.a:
        db.update_logs({x: {"hours": 7}})
        db.delete_logs([y])
    with people.b:
        with pytest.raises(db.Conflict):  # A가 방금 고친 실적을 지우려 함
            db.delete_logs([x])
        assert x in _logs().index
        with pytest.raises(db.Conflict) as e:  # A가 지운 실적을 고치려 함
            db.update_logs({y: {"hours": 3}})
        assert "지웠어요" in str(e.value)


def test_table_save_keeps_rows_added_by_other(store, people):
    db.save_companies(pd.DataFrame([{"name": "가"}, {"name": "나"}]))
    with people.a:
        db.load_companies()
    with people.b:
        stale = db.load_companies()  # B가 연 화면 (그 뒤로 다시 그리지 않음)
    with people.a:  # A: 업체 추가 + '가' 연락처
        df = db.load_companies()
        df.loc[df["name"] == "가", "phone"] = "010-1"
        db.save_companies(pd.concat([df, pd.DataFrame([{"name": "다"}])], ignore_index=True))
    with people.b:  # B: 예전 표에서 '나'만 고침 → A가 추가한 '다'도, '가' 연락처도 그대로 남음
        stale.loc[stale["name"] == "나", "note"] = "B 메모"
        db.save_companies(stale)
        got = db.load_companies().set_index("name")
        assert set(got.index) == {"가", "나", "다"}
        assert (got.at["가", "phone"], got.at["나", "note"]) == ("010-1", "B 메모")


def test_stale_form_keeps_other_fields(store, people):
    """입력 카드에 예전 값이 남아 있어도, 내가 안 고친 칸은 남이 고친 값을 살림."""
    db.insert_logs([_rec("가")])
    x = list(_logs().index)[0]
    with people.b:
        form = _logs().loc[x].to_dict()  # B가 카드를 엶 (5h · 가)
    with people.a:
        _logs()
        db.update_logs({x: {"hours": 7}})
    with people.b:  # B는 카드 전체(예전 5h 포함)를 보내지만 업체만 바꿈
        vals = {k: form[k] for k in db.LOG_FIELDS if k in form} | {"company": "나"}
        db.update_logs({x: vals})
        got = _logs().loc[x]
        assert (got["company"], db.to_num(got["hours"])) == ("나", 7)


def test_table_save_with_stale_cell_stops(store, people):
    db.save_companies(pd.DataFrame([{"name": "가"}, {"name": "나"}]))
    with people.a:
        db.load_companies()
    with people.b:
        stale = db.load_companies()
    with people.a:
        df = db.load_companies()
        df.loc[df["name"] == "가", "phone"] = "010-1"
        db.save_companies(df)
    with people.b:  # B가 예전 표에서 '가' 연락처를 다른 값으로
        stale.loc[stale["name"] == "가", "phone"] = "010-2"
        with pytest.raises(db.Conflict):
            db.save_companies(stale)
        assert db.load_companies().set_index("name").at["가", "phone"] == "010-1"


def test_equipment_save_keeps_device_added_by_other(store, people):
    with people.b:
        stale = db.load_equipment(full=True)
    with people.a:
        eq = db.load_equipment(full=True)
        db.save_equipment(pd.concat([eq, pd.DataFrame([{"name": "장비C", "in_kpi": True}])], ignore_index=True))
    with people.b:
        stale = stale.copy()
        stale.loc[stale["name"] == "장비B", "note"] = "B"
        assert not db.save_equipment(stale)
        names = set(db.load_equipment(full=True)["name"])
        assert names == {"장비A", "장비B", "장비C"}


def test_cs_and_quotes_guarded(store, people):
    rid = cs.insert([{"date": dt.date(2026, 11, 3), "title": "문의", "company": "가"}])[0]
    q = db.save_quote({"no": "Q-1", "company": "가", "data": "{}"})
    for p in (people.a, people.b):
        with p:
            cs.load()
            db.load_quotes()
    with people.a:
        cs.update({rid: {"date": dt.date(2026, 11, 3), "title": "문의(A)", "company": "가"}})
        db.save_quote({"id": q, "no": "Q-1", "company": "가", "data": '{"a": 1}'})
    with people.b:
        with pytest.raises(db.Conflict):
            cs.update({rid: {"date": dt.date(2026, 11, 3), "title": "문의(B)", "company": "가"}})
        with pytest.raises(db.Conflict):
            db.save_quote({"id": q, "no": "Q-1", "company": "가", "data": '{"b": 1}'})


def test_sheet_edit_outside_app_is_protected(store, people):
    """시트를 직접 고친 칸도 (앱이 아직 모르는 상태에서) 덮어쓰지 않음."""
    db.insert_logs([_rec("가")])
    x = list(_logs().index)[0]
    with people.b:
        _logs()
        raw = store.read("usage")
        raw.loc[raw["id"].astype(str) == str(x), "hours"] = "11"
        raw.to_csv(store._path("usage"), index=False)  # 시트에서 직접 (앱 캐시는 모름)
        with pytest.raises(db.Conflict):
            db.update_logs({x: {"hours": 4}})
