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
                        "depth": 0 if p is None else 1, "acquired_on": pd.NaT,
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


def test_excel_hours_match_kpi_calc_and_show_weekend_zero(monkeypatch):
    monkeypatch.setattr(db, "charger_caps", lambda: {})
    monkeypatch.setattr(db, "charger_family", lambda eq, ch=None: set())
    logs, eq = _logs(), _eq()
    w0, w1 = D(2026, 11, 1), D(2027, 1, 31)
    hours = status.kpi_hours(logs, w0, w1)
    daily = calc.expand_daily(logs, "spread", {})
    kpi = daily[(daily["equip_id"] == 4) & (daily["day"] >= pd.Timestamp(w0))]["hours"].sum()
    assert abs(sum(v for (e, _), v in hours.items() if e == 4) - kpi) < 1e-9
    bk = status.bars(logs, w0, w1)
    rws = status.rows(eq, status.device_group(eq), bk, w0, w1)
    ws = load_workbook(io.BytesIO(status.to_excel(rws, bk, hours, w0, w1, D(2026, 11, 21), "t"))).active
    r = next(i for i in range(1, ws.max_row + 1) if ws.cell(i, 3).value == "열충격 시험기")
    assert abs(ws.cell(r, 6).value - round(kpi, 1)) < 1e-9
    sat = 7 + (D(2026, 11, 7) - w0).days  # 11/7 토요일: 시험은 이어지지만 0시간
    assert ws.cell(r, sat).value == 0
    assert ws.cell(r, 7).value is None  # 11/1 시작 전
