"""장비 가동 현황 (core/status.py) 테스트."""
import datetime as dt
import io

import pandas as pd
from openpyxl import load_workbook

from core import calc, db, status

D = dt.date


def _eq():
    rows = [
        (1, "전극 라인", "제조", None), (2, "코터", "제조", 1), (3, "롤프레스", "제조", 1),
        (4, "열충격 시험기", "시험", None), (5, "SEM", "분석", None), (6, "옛 장비", "시험", None),
    ]
    df = pd.DataFrame([{"id": i, "name": n, "short": n, "use": u, "parent_id": p, "location": "제조검증",
                        "depth": 0 if p is None else 1, "acquired_on": pd.NaT, "code": f"C-{i}", "nfec": "",
                        "kind": "장비", "manager": "", "in_kpi": True, "annual_hours": 2000,
                        "retired_on": pd.Timestamp("2026-01-01") if i == 6 else pd.NaT} for i, n, u, p in rows])
    df["parent_id"] = df["parent_id"].astype("float")
    return df


def _logs():
    def lg(i, e, s, en, h, p="시험", hol="Y", series=""):
        return dict(id=i, equip_id=e, start_date=pd.Timestamp(s), end_date=pd.Timestamp(en), include_holidays=hol,
                    hours=h, fee=0, purpose=p, company=f"업체{i}", created_by="", series=series)
    return pd.DataFrame([
        lg(1, 4, "2026-11-02", "2026-11-30", 80, hol="N", series="S"),  # 달마다 나눠 저장한 기간 실적
        lg(2, 4, "2026-12-01", "2026-12-10", 64, hol="N", series="S"),
        lg(3, 3, "2026-11-20", "2026-11-20", 6, p="생산"),
        lg(4, 5, "2026-10-01", "2026-10-02", 4, p="분석"),  # 보는 기간 밖
    ])


def test_bars_join_series_and_skip_outside_window():
    w0, w1 = D(2026, 11, 1), D(2027, 1, 31)
    bk = status.bars(_logs(), w0, w1)
    assert len(bk) == 2
    s = bk[bk["equip_id"] == 4].iloc[0]
    assert (s["start"], s["end"], s["skip_off"], s["log_ids"]) == (D(2026, 11, 2), D(2026, 12, 10), True, [1, 2])
    assert bk[bk["equip_id"] == 3].iloc[0]["cat"] == "제조"


def test_rows_order_filter_and_heads(monkeypatch):
    monkeypatch.setattr(db, "charger_family", lambda eq, ch=None: set())
    eq = _eq()
    w0, w1 = D(2026, 11, 1), D(2027, 1, 31)
    groups = status.device_group(eq)
    bk = status.bars(_logs(), w0, w1)
    rws = status.rows(eq, groups, bk, w0, w1)
    ids = [r["id"] for r in rws]
    assert 6 not in ids  # 보는 기간 전에 불용
    assert ids == [4, 1, 2, 3, 5]  # 구분 순서 시험 → 제조 → 분석, 주장비 머리 줄 다음 세부장비
    assert [r["head"] for r in rws if r["id"] == 1] == [True]
    assert [r["id"] for r in status.rows(eq, groups, bk, w0, w1, want="분석")] == [5]


def test_now_next_prefers_running_then_upcoming():
    bs = [{"start": D(2026, 11, 25), "end": D(2026, 11, 26)}, {"start": D(2026, 11, 1), "end": D(2026, 11, 21)}]
    assert status.now_next(bs, D(2026, 11, 21)) == (bs[1], True)
    assert status.now_next(bs, D(2026, 11, 22)) == (bs[0], False)


def test_excel_same_format_as_test_part_file_and_hours_match_kpi(monkeypatch):
    monkeypatch.setattr(db, "charger_caps", lambda: {})
    monkeypatch.setattr(db, "charger_family", lambda eq, ch=None: set())
    logs, eq = _logs(), _eq()
    ys, ye, today = D(2026, 1, 1), D(2026, 12, 31), D(2026, 11, 21)
    rws = status.rows(eq, status.device_group(eq), status.bars(logs, ys, ye), ys, ye, busy_first=False)
    wb = load_workbook(io.BytesIO(status.to_excel(rws, logs, eq, 2026, today, {"annual_hours": 2000})))
    assert wb.sheetnames[:2] == ["총괄", "1. 열충격 시험기"]
    ws = wb["1. 열충격 시험기"]
    assert [ws.cell(1, j).value for j in (1, 5, 6, 9, 14, 16, 17, 21)] == [
        "장비명", "가동No.", "사용시작일", "사용기관(기업)명", "사용시간\n(hr기준)", "월", "사용시간(hr)", "가동률"]
    rows = list(ws.iter_rows(min_row=2, max_col=14, values_only=True))
    assert len(rows) == 365  # 하루 한 줄 (그날 실적이 둘이면 줄이 늘어남)
    got = sum(r[13] or 0 for r in rows)
    daily = calc.expand_daily(logs, "spread", {})
    summ = calc.equipment_summary(daily, eq[eq["id"] == 4], ys, today, 2000, eq).iloc[0]
    assert abs(got - summ["사용시간"]) < 1e-6  # 가동률 계산과 같은 시간 (오늘까지)
    sat = next(r for r in rows if r[5].date() == D(2026, 11, 7))
    assert sat[8] == "업체1" and sat[13] == 0  # 주말에도 이어지는 시험은 업체 + 0시간
    later = next(r for r in rows if r[5].date() == D(2026, 12, 2))
    assert later[8] == "업체2" and later[13] is None  # 오늘 뒤 예약은 업체만
    assert ws["Q2"].value.startswith("=SUMIFS($N:$N") and ws["Q14"].value == "=SUM(Q2:Q13)"
    tot = wb["총괄"]
    assert tot["E6"].value == "열충격 시험기" and tot["N6"].value == "='1. 열충격 시험기'!R14"
    assert abs(tot["J6"].value - summ["가용시간"]) < 1e-9  # 반올림 없이 (평균 가동률이 KPI 현황과 똑같게)
    line = wb[next(n for n in wb.sheetnames if n.endswith("전극 라인"))]
    assert any(c.value == "전극 라인 › 롤프레스" for c in line["A"])  # 세부장비 실적은 주장비 탭에
