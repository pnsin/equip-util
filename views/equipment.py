import streamlit as st

from core import db, seed
from ui_style import page_header
from views.common import (confirm_delete, delete_config, filtered_editor, search_box, split_deleted,
                          with_delete_column)

# 화면 열 이름은 장비 현황 엑셀(260310 전수조사·내부기준 탭)의 항목 이름을 따름. 순서도 엑셀 순서.
COLS = {
    "id": "id", "code": "ITUBE번호", "name": "장비명(한글)", "kind": "장비구분", "manager": "관리자",
    "annual_hours": "연간기준시간", "acquired_on": "도입일", "retired_on": "불용일", "in_kpi": "가동률 산정",
    "note": "비고",
}


def render() -> None:
    cfg = db.get_settings()
    page_header("장비 정보", "정보 입력")
    msg = st.session_state.pop("equip_saved", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")
        st.toast(msg, icon="✅")
    eq = db.load_equipment()
    view = eq[list(COLS)].rename(columns=COLS)
    view["도입일"] = view["도입일"].dt.date
    view["불용일"] = view["불용일"].dt.date

    q = search_box("equip_q", "🔍  장비명·ITUBE번호·관리자로 찾기")
    kpi_n = int(view["가동률 산정"].fillna(False).astype(bool).sum()) if not view.empty else 0
    mask = None
    if q:
        mask = (view["장비명(한글)"].str.contains(q, case=False, regex=False)
                | view["ITUBE번호"].str.contains(q, case=False, regex=False)
                | view["관리자"].astype(str).str.contains(q, case=False, regex=False))

    edited, shown = filtered_editor(
        with_delete_column(view), mask, key=f"equip_editor_{q}", num_rows="dynamic", hide_index=True,
        width="stretch", height=min(620, 38 + 35 * (len(view) + 2)),
        column_order=["삭제"] + [c for c in COLS.values() if c != "id"],
        column_config=delete_config() | {
            "장비명(한글)": st.column_config.TextColumn(required=True, width="large"),
            "ITUBE번호": st.column_config.TextColumn(help="예: 2312-C-0436"),
            "장비구분": st.column_config.SelectboxColumn(options=seed.EQUIP_KINDS),
            "연간기준시간": st.column_config.NumberColumn(min_value=0, step=100, format="%d",
                                                     help=f"비워 두면 기본값 {float(cfg.get('annual_hours') or 2000):,.0f}시간(설정)을 씁니다."),
            "도입일": st.column_config.DateColumn(format="YYYY-MM-DD", help="이 날 이전은 가용시간에서 빠집니다."),
            "불용일": st.column_config.DateColumn(format="YYYY-MM-DD", help="이 날 이후는 가용시간에서 빠집니다."),
            "가동률 산정": st.column_config.CheckboxColumn(default=True, help="부대시설처럼 가동률에 넣지 않을 장비는 끄세요."),
            "비고": st.column_config.TextColumn(width="large"),
        },
    )
    st.caption((f"{shown}대 / " if q else "") + f"전체 {len(view)}대 · 가동률 산정 {kpi_n}대")
    edited, deleted = split_deleted(edited, "장비명(한글)")
    ok = confirm_delete(deleted, "equip_editor_del", "대")
    if st.button("변경 내용 저장", type="primary", disabled=not ok, icon=":material/save:"):
        errors = db.save_equipment(edited.rename(columns={v: k for k, v in COLS.items()}))
        for e in errors:
            st.warning(e)
        if not errors:
            st.session_state.equip_saved = "장비 목록을 저장했습니다." + (f" ({len(deleted)}대 삭제)" if deleted else "")
            st.session_state.pop(f"equip_editor_{q}", None)
            st.session_state.pop("equip_editor_del", None)
            st.rerun()
