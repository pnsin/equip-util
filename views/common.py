"""여러 화면이 함께 쓰는 기간 선택 위젯."""
import datetime as dt

import streamlit as st

from core.calc import period_bounds

HALF = ["상반기", "하반기"]


def period_picker(key: str, kinds: list[str], default_kind: str, completed: bool = False,
                  years: list[int] | None = None) -> tuple[dt.date, dt.date, str, str]:
    """기간 단위와 기간을 고르게 하고 (시작일, 종료일, 이름, 단위)를 돌려줍니다.

    completed=True 면 기본값이 '직전에 끝난 기간'(예: 11월이면 3분기)입니다.
    """
    today = dt.date.today()
    kind = st.segmented_control("기간 단위", kinds, default=default_kind, key=f"{key}_kind") or default_kind
    ref = today
    if completed and kind in ("월", "분기", "반기"):
        ref = period_bounds(kind, today)[0] - dt.timedelta(days=1)

    if kind == "직접 지정":
        s0 = ref.replace(day=1)
        rng = st.date_input("기간", value=(s0, today), format="YYYY-MM-DD", key=f"{key}_range")
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            s, e = rng
        else:
            s = e = rng[0] if isinstance(rng, (tuple, list)) and rng else today
        return s, e, f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", kind
    if kind == "주":
        d = st.date_input("기준일 (그 날이 속한 주)", value=today, format="YYYY-MM-DD", key=f"{key}_week")
        s, e, label = period_bounds("주", d)
        return s, e, label, kind

    years = sorted(set((years or []) + [today.year, ref.year]), reverse=True)
    cols = st.columns([1, 1, 3])
    year = cols[0].selectbox("연도", years, index=years.index(ref.year), key=f"{key}_year")
    if kind == "월":
        m = cols[1].selectbox("월", list(range(1, 13)), index=ref.month - 1, format_func=lambda v: f"{v}월",
                              key=f"{key}_month")
        d = dt.date(year, m, 1)
    elif kind == "분기":
        q = cols[1].selectbox("분기", [1, 2, 3, 4], index=(ref.month - 1) // 3, format_func=lambda v: f"{v}분기",
                              key=f"{key}_q")
        d = dt.date(year, (q - 1) * 3 + 1, 1)
    elif kind == "반기":
        h = cols[1].selectbox("반기", HALF, index=0 if ref.month <= 6 else 1, key=f"{key}_h")
        d = dt.date(year, 1 if h == "상반기" else 7, 1)
    else:
        d = dt.date(year, 1, 1)
    s, e, label = period_bounds(kind, d)
    return s, e, label, kind
