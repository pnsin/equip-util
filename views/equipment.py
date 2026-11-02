import streamlit as st

from core import db, seed
from views.common import confirm_delete, delete_config, split_deleted, with_delete_column

COLS = {
    "id": "id", "name": "장비명", "code": "장비번호", "kind": "장비구분", "annual_hours": "연간기준시간",
    "acquired_on": "도입일", "retired_on": "불용일", "in_kpi": "가동률 산정", "manager": "담당자", "note": "비고",
}


def render() -> None:
    st.title("🔧 장비 관리")
    msg = st.session_state.pop("equip_saved", None)
    if msg:
        st.success(msg)
    cfg = db.get_settings()
    st.caption(
        f"연간기준시간을 비워 두면 기본값 {cfg.get('annual_hours', 2000):,.0f}시간(설정 메뉴)을 씁니다. "
        "도입일 이전·불용일 이후는 가용시간에서 빠집니다. 부대시설처럼 가동률에 넣지 않을 장비는 '가동률 산정'을 끄세요."
    )
    eq = db.load_equipment()
    view = eq[list(COLS)].rename(columns=COLS)
    view["도입일"] = view["도입일"].dt.date
    view["불용일"] = view["불용일"].dt.date

    q = st.text_input("검색", placeholder="장비명 또는 장비번호")
    if q:
        mask = view["장비명"].str.contains(q, case=False, regex=False) | view["장비번호"].str.contains(q, case=False, regex=False)
        st.dataframe(view[mask].drop(columns=["id"]), hide_index=True, width="stretch")
        st.caption("검색 중에는 보기만 됩니다. 수정하려면 검색어를 지우세요.")
        return

    edited = st.data_editor(
        with_delete_column(view), key="equip_editor", num_rows="dynamic", hide_index=True, width="stretch", height=560,
        column_order=["삭제"] + [c for c in COLS.values() if c != "id"],
        column_config=delete_config() | {
            "장비명": st.column_config.TextColumn(required=True, width="large"),
            "장비구분": st.column_config.SelectboxColumn(options=seed.EQUIP_KINDS),
            "연간기준시간": st.column_config.NumberColumn(min_value=0, step=100, format="%d"),
            "도입일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "불용일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "가동률 산정": st.column_config.CheckboxColumn(default=True),
        },
    )
    st.caption(f"총 {len(edited)}대 · 지울 행은 '삭제'에 체크하고, 맨 아래 빈 행에 입력하면 장비가 추가됩니다.")
    edited, deleted = split_deleted(edited, "장비명")
    ok = confirm_delete(deleted, "equip_editor_del", "대")
    if st.button("변경 내용 저장", type="primary", disabled=not ok):
        errors = db.save_equipment(edited.rename(columns={v: k for k, v in COLS.items()}))
        for e in errors:
            st.warning(e)
        if not errors:
            st.session_state.equip_saved = "장비 목록을 저장했습니다." + (f" ({len(deleted)}대 삭제)" if deleted else "")
            st.session_state.pop("equip_editor", None)
            st.session_state.pop("equip_editor_del", None)
            st.rerun()
