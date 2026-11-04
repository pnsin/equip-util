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


def _clear_undo():
    import streamlit as st
    for k in ("_undo_stack", "_undo_open"):
        st.session_state.pop(k, None)


def test_undo_insert_update_delete(store):
    _clear_undo()
    rec = dict(equip_id=1, start_date=D(2026, 7, 1), end_date=D(2026, 7, 1), hours=3, purpose="시험",
               usage_type="내부", company="")
    db.insert_logs([rec, dict(rec, hours=4)], "tester")
    ids = list(store.read("usage")["id"])
    db.update_logs({int(ids[0]): {"hours": 9}})
    db.delete_logs([int(ids[1])])
    assert len(store.read("usage")) == 1 and len(store.read("trash")) == 1
    assert db.undo_last() == "실적 1건 삭제"
    assert len(store.read("usage")) == 2 and len(store.read("trash")) == 0
    assert db.undo_last() == "실적 1건 수정"
    assert store.read("usage").set_index("id").loc[ids[0], "hours"] == "3"
    assert db.undo_last() == "실적 2건 추가"
    assert store.read("usage").empty
    assert db.undo_last() is None
    assert len(store.read("history")) >= 6


def test_undo_group_and_trash_restore(store):
    _clear_undo()
    rec = dict(equip_id=1, start_date=D(2026, 7, 1), end_date=D(2026, 7, 1), hours=3, purpose="시험",
               usage_type="내부", company="")
    with db.undo_group("묶음"):
        db.insert_logs([rec])
        db.insert_logs([rec])
    assert len(db.undo_stack()) == 1
    ids = list(store.read("usage")["id"])
    db.delete_logs([int(ids[0])])
    tid = list(store.read("trash")["id"])
    res = db.restore_trash(tid)
    assert res["restored"] == 1 and len(store.read("usage")) == 2 and store.read("trash").empty


def test_master_save_undo_and_trash(store):
    _clear_undo()
    import pandas as pd
    db.save_companies(pd.DataFrame([{"name": "가"}, {"name": "나"}]))
    db.save_companies(pd.DataFrame([{"id": 1, "name": "가"}]))  # '나' 삭제
    assert list(store.read("companies")["name"]) == ["가"]
    assert list(store.read("trash")["summary"]) == ["나"]
    assert db.undo_last() == "업체 저장"
    assert sorted(store.read("companies")["name"]) == ["가", "나"] and store.read("trash").empty


def test_compare_period_modes():
    import datetime as dt
    from core.calc import compare_period
    s, e, e_eff = dt.date(2026, 10, 1), dt.date(2026, 12, 31), dt.date(2026, 11, 2)
    ps, pe, label = compare_period("분기", s, e, e_eff, "직전")
    assert (ps, pe) == (dt.date(2026, 7, 1), dt.date(2026, 8, 2)) and "같은 기간" in label
    ps, pe, label = compare_period("분기", s, e, e_eff, "전년")
    assert (ps, pe) == (dt.date(2025, 10, 1), dt.date(2025, 11, 2)) and label.startswith("전년")
    # 직접 지정: 같은 길이만큼 바로 앞
    ps, pe, _ = compare_period("직접 지정", dt.date(2026, 3, 11), dt.date(2026, 3, 20), dt.date(2026, 3, 20))
    assert (ps, pe) == (dt.date(2026, 3, 1), dt.date(2026, 3, 10))


# ── 장비 › 세부장비 계층 ─────────────────────────────────────────

def _tree_store(store):
    store.rewrite("equipment", db._rows("equipment", [
        {"id": 1, "name": "시스템", "code": "2312-C-0001", "in_kpi": True, "order": 1},
        {"id": 2, "name": "믹서", "parent_id": 1, "kind": "세부장비", "in_kpi": False, "order": 2},
        {"id": 3, "name": "믹서(양극)", "parent_id": 2, "kind": "세부장비", "in_kpi": True, "order": 3},
        {"id": 4, "name": "단독장비", "in_kpi": True, "order": 4},
    ]))
    db.clear_caches()


def test_tree_order_labels_and_itube_unit(store):
    _tree_store(store)
    eq = db.load_equipment()
    assert list(eq["id"]) == [1, 2, 3, 4]
    assert list(eq["depth"]) == [0, 1, 2, 0]
    assert eq.set_index("id").at[3, "label"] == "믹서(양극) · 시스템"
    assert eq.set_index("id").at[3, "itube_id"] == 1 and pd.isna(eq.set_index("id").at[4, "itube_id"])
    assert sorted(db.descendants(eq)[1]) == [1, 2, 3]


def test_rollup_adds_child_hours_without_double_count(store):
    _tree_store(store)
    eq = db.load_equipment()
    logs = pd.DataFrame([_log(id=1, equip_id=3, hours=10), _log(id=2, equip_id=1, hours=5),
                         _log(id=3, equip_id=4, hours=2)])
    daily = calc.expand_daily(logs, "spread")
    sm = calc.equipment_summary(daily, eq, D(2026, 7, 1), D(2026, 7, 31), 2000).set_index("equip_id")
    assert sm.at[1, "사용시간"] == 15 and sm.at[2, "사용시간"] == 10 and sm.at[3, "사용시간"] == 10
    assert not sm.at[3, "KPI"]  # 상위가 대상이면 하위는 합계에서 뺌
    assert calc.totals(sm.reset_index())["used"] == 17


def test_logs_carry_itube_parent(store):
    _tree_store(store)
    db.insert_logs([dict(equip_id=3, start_date=D(2026, 7, 1), end_date=D(2026, 7, 1), hours=3, purpose="시험",
                         usage_type="내부", company="")], "t")
    r = db.load_logs().iloc[0]
    assert (r["equip_name"], r["itube_name"], r["itube_code"]) == ("믹서(양극)", "시스템", "2312-C-0001")


def test_delete_parent_reattaches_children(store):
    _tree_store(store)
    eq = db.load_equipment()
    db.save_equipment(eq[eq["id"] != 2])
    eq = db.load_equipment().set_index("id")
    assert eq.at[3, "parent_id"] == 1


def _excel(rows):
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "내부기준_test"
    head = ["대분류", "주장비(종)", "관리자", "0", "장비명(한글)", "장비구분", "ITUBE번호", "국가연구시설장비번호", "구분",
            "자산번호", "자산기준\n수량", "세부장비", "대수", "세세부장비/추후정리", "구매처", "제조사", "모델명", "장비위치",
            "시스템 구성", "장비용도", "비고"]
    ws.append(head)
    for r in rows:
        ws.append([r.get(h) for h in head])
    ws.merge_cells("E2:E4")
    ws.merge_cells("G2:G4")
    ws.merge_cells("L2:L3")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_import_builds_tree_and_keeps_ids():
    from core import equip_import as ei
    data = _excel([
        {"대분류": "5Ah", "장비명(한글)": "시스템", "장비구분": "주장비", "ITUBE번호": "2212-C-0709", "자산번호": "A1",
         "자산기준\n수량": 1, "세부장비": "5L 믹서", "대수": 1, "세세부장비/추후정리": "5L 믹서(양극)"},
        {"세세부장비/추후정리": "5L 믹서(음극)"},
        {"세부장비": "침수", "대수": 1, "세세부장비/추후정리": "침수시험기"},
        {"장비명(한글)": None, "ITUBE번호": "미등록장비", "장비구분": "주장비", "세부장비": "건조오븐", "대수": 0,
         "세세부장비/추후정리": "건조오븐", "자산번호": "B2"},
    ])
    parsed = ei.parse(data)
    names = [(p["name"], p["parent_tmp"]) for p in parsed]
    assert names == [("시스템", None), ("5L 믹서", 0), ("5L 믹서(양극)", 1), ("5L 믹서(음극)", 1),
                     ("침수시험기", 0), ("건조오븐", None)]
    existing = pd.DataFrame([{"id": 7, "name": "시스템", "code": "2212-C-0709", "in_kpi": True},
                             {"id": 9, "name": "건조오븐", "code": "", "in_kpi": True}])
    out = ei.merge_with_existing(parsed, existing)
    assert [r["id"] for r in out][:1] == [7] and out[-1]["id"] == 9
    assert out[1]["parent_id"] == 7 and out[2]["parent_id"] == out[1]["id"]


def test_performance_file_fills_old_sheet_layout(store):
    import io as _io
    from openpyxl import load_workbook
    from core import perf_export
    _tree_store(store)
    db.insert_logs([
        dict(equip_id=3, start_date=D(2026, 7, 30), end_date=D(2026, 8, 2), hours=40, purpose="생산",
             usage_type="내부", company="", dept="연구팀", include_holidays="Y", created_by="홍길동"),
        dict(equip_id=1, start_date=D(2026, 8, 1), end_date=D(2026, 8, 1), hours=5, purpose="시험",
             usage_type="외부", company="가나전지", include_holidays="Y"),
        dict(equip_id=4, start_date=D(2026, 9, 1), end_date=D(2026, 9, 1), hours=3, purpose="분석",
             usage_type="외부", company="가나전지", include_holidays="Y"),
    ], "t")
    logs, eq = db.load_logs(), db.load_equipment()
    data, info = perf_export.make_performance_file(logs, eq, None, D(2026, 8, 1), D(2026, 8, 31),
                                                   today=D(2026, 11, 4))
    assert info["count"] == 2 and info["hours"] == 25  # 7/30~8/2 40h 중 8월 몫 20h + 5h
    wb = load_workbook(_io.BytesIO(data))
    assert wb.sheetnames == ["가동데이터(2026)", "ooo_전체", "ooo_시험", "ooo_제조", "장비목록"]
    ws = wb["가동데이터(2026)"]
    assert ws["A4"].value == "접수번호" and ws["P5"].value == "장비명" and ws["S5"].value.date() == D(2026, 8, 1)
    row = {ws.cell(8 + 1, c).value for c in range(1, 19)} | {ws.cell(10, c).value for c in range(1, 19)}
    assert "연구팀" in row and "제조" in row and "믹서(양극)" in row
    allsh = wb["ooo_전체"]
    names = [allsh.cell(r, 2).value for r in range(8, 12)]
    assert names[0] == "시스템" and allsh.cell(8, 5).value == 25  # 세부장비 시간이 주장비에 더해짐
    assert allsh.cell(8, 6).value == 15  # 8/1: 세부 10 + 주장비 5
    assert "합계" in names and allsh.cell(names.index("합계") + 8, 5).value == 25
    assert perf_export.file_name(D(2026, 8, 1), D(2026, 8, 31)) == "장비실적_2026년8월.xlsx"
    assert perf_export._weeknum(D(2026, 1, 3)) == 1 and perf_export._weeknum(D(2026, 1, 4)) == 2


def test_sheet_read_many_one_request():
    """화면용 탭을 구글 API 요청 한 번으로 읽고, 빈 탭·짧은 행도 표 모양으로 맞춥니다."""
    class WS:
        def __init__(self, title):
            self.title = title

    class SS:
        calls = 0

        def values_batch_get(self, ranges):
            SS.calls += 1
            assert ranges == ["'업체'", "'담당자'"]
            return {"valueRanges": [{"values": [db.heads("companies"), ["1", "가나"], ["", ""]]}, {}]}

    store = db.SheetStore.__new__(db.SheetStore)
    store.ss, store.ws = SS(), {"companies": WS("업체"), "staff": WS("담당자")}
    out = store.read_many(["companies", "staff"])
    assert SS.calls == 1
    assert list(out["companies"].columns) == db.cols("companies") and len(out["companies"]) == 1
    assert out["companies"].iloc[0]["name"] == "가나" and out["companies"].iloc[0]["note"] == ""
    assert out["staff"].empty and list(out["staff"].columns) == db.cols("staff")


def test_summary_rolls_up_children_once():
    """세부장비 실적은 상위 장비에 더해지고, 건수는 같은 실적을 두 번 세지 않습니다."""
    eq = pd.DataFrame([
        dict(id=1, name="주", code="A", kind="", manager="", annual_hours=2000, acquired_on=None, retired_on=None,
             in_kpi=True, parent_id=None),
        dict(id=2, name="세부", code="", kind="", manager="", annual_hours=2000, acquired_on=None, retired_on=None,
             in_kpi=True, parent_id=1),
    ])
    logs = pd.DataFrame([_log(id=1, equip_id=1, hours=3), _log(id=2, equip_id=2, hours=5)])
    sm = calc.equipment_summary(calc.expand_daily(logs), eq, D(2026, 7, 1), D(2026, 7, 31), 2000).set_index("equip_id")
    assert sm.at[1, "사용시간"] == 8 and sm.at[1, "건수"] == 2
    assert sm.at[2, "사용시간"] == 5 and sm.at[2, "건수"] == 1
    assert bool(sm.at[2, "KPI"]) is False  # 상위가 이미 산정 대상
