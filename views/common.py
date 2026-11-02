"""여러 화면이 함께 쓰는 기간 선택 위젯."""
import datetime as dt

import pandas as pd
import streamlit as st

from core.calc import period_bounds

HALF = ["상반기", "하반기"]


def period_picker(key: str, kinds: list[str], default_kind: str, completed: bool = False,
                  years: list[int] | None = None, extra=None) -> tuple[dt.date, dt.date, str, str]:
    """기간 단위와 기간을 한 줄에서 고르게 하고 (시작일, 종료일, 이름, 단위)를 돌려줍니다.

    completed=True 면 기본값이 '직전에 끝난 기간'(예: 11월이면 3분기)입니다.
    extra 가 있으면 줄 오른쪽 끝 칸에서 extra(칸)을 불러 다른 위젯을 그립니다.
    """
    today = dt.date.today()
    row = st.columns([2.6, 1, 1, 0.2, 2.2] if extra else [2.6, 1, 1, 2.4], vertical_alignment="bottom")
    with row[0]:
        kind = st.segmented_control("기간 단위", kinds, default=default_kind, key=f"{key}_kind") or default_kind
    if extra:
        with row[4]:
            extra()
    ref = today
    if completed and kind in ("월", "분기", "반기"):
        ref = period_bounds(kind, today)[0] - dt.timedelta(days=1)

    if kind == "직접 지정":
        s0 = ref.replace(day=1)
        rng = row[1].date_input("기간", value=(s0, today), format="YYYY-MM-DD", key=f"{key}_range")
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            s, e = rng
        else:
            s = e = rng[0] if isinstance(rng, (tuple, list)) and rng else today
        return s, e, f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", kind
    if kind == "주":
        d = row[1].date_input("기준일", value=today, format="YYYY-MM-DD", key=f"{key}_week",
                              help="고른 날이 속한 주(월~일)를 봅니다.")
        s, e, label = period_bounds("주", d)
        return s, e, label, kind

    years = sorted(set((years or []) + [today.year, ref.year]), reverse=True)
    year = row[1].selectbox("연도", years, index=years.index(ref.year), key=f"{key}_year",
                            format_func=lambda v: f"{v}년")
    if kind == "월":
        m = row[2].selectbox("월", list(range(1, 13)), index=ref.month - 1, format_func=lambda v: f"{v}월",
                             key=f"{key}_month")
        d = dt.date(year, m, 1)
    elif kind == "분기":
        q = row[2].selectbox("분기", [1, 2, 3, 4], index=(ref.month - 1) // 3, format_func=lambda v: f"{v}분기",
                             key=f"{key}_q")
        d = dt.date(year, (q - 1) * 3 + 1, 1)
    elif kind == "반기":
        h = row[2].selectbox("반기", HALF, index=0 if ref.month <= 6 else 1, key=f"{key}_h")
        d = dt.date(year, 1 if h == "상반기" else 7, 1)
    else:
        d = dt.date(year, 1, 1)
    s, e, label = period_bounds(kind, d)
    return s, e, label, kind


# ── 목록 표의 '삭제' 칸 ─────────────────────────────────────────

DEL = "삭제"


def with_delete_column(view):
    """표 맨 앞에 '삭제' 체크 칸을 붙입니다."""
    view = view.copy()
    view.insert(0, DEL, False)
    return view


def delete_config() -> dict:
    return {DEL: st.column_config.CheckboxColumn(DEL, width="small", default=False,
                                                 help="지울 행에 체크한 뒤 저장을 누르세요.")}


def split_deleted(edited, name_col: str):
    """(남길 행, 지울 행 이름 목록)."""
    mask = edited[DEL].fillna(False).astype(bool)
    names = [str(n) for n in edited.loc[mask, name_col] if str(n) not in ("", "None", "<NA>", "nan")]
    return edited[~mask].drop(columns=[DEL]), names


def confirm_delete(names: list[str], key: str, unit: str = "개") -> bool:
    """지울 행이 있으면 무엇이 지워지는지 한 줄로 알려 줍니다 (지운 것은 되돌리기·휴지통으로 살릴 수 있음)."""
    if names:
        shown = ", ".join(names[:5]) + (f" 외 {len(names) - 5}{unit}" if len(names) > 5 else "")
        st.caption(f"저장하면 {len(names)}{unit} 삭제: {shown} · 실수해도 '되돌리기'나 휴지통에서 살릴 수 있습니다.")
    return True


# ── 검색해도 바로 고칠 수 있는 목록 표 ───────────────────────────

POS = "_pos"


def search_box(key: str, placeholder: str) -> str:
    return st.text_input("검색", placeholder=placeholder, key=key, label_visibility="collapsed",
                         icon=":material/search:")


def filtered_editor(view, mask, **kwargs):
    """검색에 맞는 행만 보여 주되 그대로 고칠 수 있는 표.

    돌려주는 값은 전체 목록(숨긴 행 + 고친 행 + 새 행)이며, 원래 순서를 지키고 새 행은 맨 뒤에 둡니다.
    view 에는 이미 '삭제' 칸이 있어야 합니다.
    """
    view = view.copy()
    view[POS] = range(len(view))
    order = kwargs.pop("column_order", None)
    shown = view if mask is None else view[mask]
    edited = st.data_editor(shown, column_order=order, **kwargs)
    full = edited if mask is None else pd.concat([view[~mask], edited])
    full = full.sort_values(POS, na_position="last", kind="stable").drop(columns=[POS])
    return full.reset_index(drop=True), len(edited)
