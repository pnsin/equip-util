"""구글 시트 저장소를 가짜 시트로 돌려 요청 수와 결과를 확인 (2026-11-18 속도 작업)."""
import datetime as dt
import types

import pytest

from core import db


class FakeWS:
    def __init__(self, ss, title, sid, values):
        self.ss, self.title, self.id, self.values = ss, title, sid, values

    @property
    def row_count(self):
        return max(len(self.values), 1000)

    @property
    def col_count(self):
        return 40

    def _c(self, name):
        self.ss.calls.append(name)

    def get_all_values(self):
        self._c("get_all_values")
        return [list(r) for r in self.values]

    def row_values(self, n):
        self._c("row_values")
        return list(self.values[n - 1]) if len(self.values) >= n else []

    def col_values(self, n):
        self._c("col_values")
        return [r[n - 1] if len(r) >= n else "" for r in self.values]

    def append_rows(self, rows, **kw):
        self._c("append_rows")
        self.values += [[("" if v is None else str(v)) for v in r] for r in rows]

    def batch_update(self, data, **kw):
        self._c("ws.batch_update")
        for d in data:
            r = int(d["range"].split(":")[0][1:])
            self.values[r - 1] = [str(v) for v in d["values"][0]]

    def update(self, values=None, range_name="A1", **kw):
        self._c("update")
        for i, r in enumerate(values):
            if i < len(self.values):
                self.values[i] = [str(v) for v in r]
            else:
                self.values.append([str(v) for v in r])

    def add_rows(self, n):
        self._c("add_rows")

    def add_cols(self, n):
        self._c("add_cols")

    def freeze(self, rows=1):
        pass


class FakeSS:
    def __init__(self):
        self.calls, self.tabs = [], {}

    def worksheets(self):
        self.calls.append("worksheets")
        return list(self.tabs.values())

    def add_worksheet(self, title, rows, cols):
        self.calls.append("add_worksheet")
        ws = FakeWS(self, title, len(self.tabs) + 1, [])
        self.tabs[title] = ws
        return ws

    def values_batch_get(self, ranges):
        self.calls.append("values_batch_get")
        out = []
        for r in ranges:
            title, _, rng = r.partition("!")
            vals = self.tabs[title.strip("'").replace("''", "'")].values
            out.append({"values": vals[:1] if rng == "1:1" else [list(x) for x in vals]})
        return {"valueRanges": out}

    def batch_update(self, body):
        self.calls.append("ss.batch_update")
        by_id = {w.id: w for w in self.tabs.values()}
        for q in body["requests"]:
            if "appendCells" in q:
                ws = by_id[q["appendCells"]["sheetId"]]
                for row in q["appendCells"]["rows"]:
                    ws.values.append([str(list(c["userEnteredValue"].values())[0]) for c in row["values"]])
            elif "deleteDimension" in q:
                rg = q["deleteDimension"]["range"]
                del by_id[rg["sheetId"]].values[rg["startIndex"]:rg["endIndex"]]


@pytest.fixture
def sheet(monkeypatch):
    ss = FakeSS()
    for t, (title, _) in db.TABLES.items():  # 이미 만들어진 시트 (1행 = 열 제목)
        ss.tabs[title] = FakeWS(ss, title, len(ss.tabs) + 1, [db.heads(t)])
    ss.tabs[db.TABLES["equipment"][0]].values.append(
        [str(x) for x in db._rows("equipment", [{"id": 1, "name": "장비A", "in_kpi": True}])[0]])
    import gspread
    monkeypatch.setattr(gspread, "service_account_from_dict",
                        lambda *a, **k: types.SimpleNamespace(open_by_key=lambda key: ss))
    store = db.SheetStore({"x": 1}, "sid")
    monkeypatch.setattr(db, "get_store", lambda: store)
    monkeypatch.setattr(db, "log", lambda *a, **k: None)  # 수정 기록은 뒤에서 따로 씀
    db.clear_caches()
    yield ss, store
    db.clear_caches()


def test_startup_reads_all_headers_in_one_request(sheet):
    ss, _ = sheet
    assert ss.calls.count("row_values") == 0
    assert ss.calls == ["worksheets", "values_batch_get"]


def test_save_edit_delete_request_counts(sheet):
    ss, store = sheet
    db._snapshot()
    rec = dict(equip_id=1, start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 7, 1), hours=2.5,
               purpose="시험", usage_type="내부", company="업체A", fee=15000)
    ss.calls.clear()
    db.insert_logs([rec, dict(rec, hours=4)], "tester")
    db.load_logs()
    assert ss.calls == ["append_rows"]  # 저장 뒤 다시 읽지 않음
    ids = [r[0] for r in ss.tabs[db.TABLES["usage"][0]].values[1:]]

    ss.calls.clear()
    db.update_logs({int(ids[0]): {"hours": 7}})
    db.load_logs()
    assert ss.calls == ["get_all_values", "ws.batch_update"]  # 예전: 읽기 2 + 쓰기 1 + 다시 읽기 1

    ss.calls.clear()
    assert db.delete_logs([int(ids[1])]) == 1
    logs = db.load_logs()
    assert ss.calls == ["get_all_values", "ss.batch_update"]  # 예전: 읽기 2 + 휴지통 1 + 지우기 1 + 다시 읽기 1
    assert list(logs["hours"]) == [7]
    assert len(ss.tabs[db.TABLES["trash"][0]].values) == 2  # 휴지통에 한 줄
    # 시트 실제 내용과 화면용 묶음이 같음
    fresh = store.read("usage").sort_values("id").reset_index(drop=True)
    snap = db._snapshot()["usage"].sort_values("id").reset_index(drop=True)
    assert fresh.equals(snap)


def test_header_mismatch_still_detected(monkeypatch):
    ss = FakeSS()
    for t, (title, _) in db.TABLES.items():
        ss.tabs[title] = FakeWS(ss, title, len(ss.tabs) + 1, [db.heads(t)])
    ss.tabs[db.TABLES["usage"][0]].values[0] = ["엉뚱한", "제목"]
    import gspread
    monkeypatch.setattr(gspread, "service_account_from_dict",
                        lambda *a, **k: types.SimpleNamespace(open_by_key=lambda key: ss))
    with pytest.raises(db.StorageError):
        db.SheetStore({"x": 1}, "sid")

