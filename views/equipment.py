import streamlit as st

from core import db, equip_import, seed

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
    with st.expander("📥 장비 목록 엑셀로 한꺼번에 추가", expanded=db.load_equipment().empty):
        _import_box()

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
        view, key="equip_editor", num_rows="dynamic", hide_index=True, width="stretch", height=560,
        column_order=[c for c in COLS.values() if c != "id"],
        column_config={
            "장비명": st.column_config.TextColumn(required=True, width="large"),
            "장비구분": st.column_config.SelectboxColumn(options=seed.EQUIP_KINDS),
            "연간기준시간": st.column_config.NumberColumn(min_value=0, step=100, format="%d"),
            "도입일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "불용일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "가동률 산정": st.column_config.CheckboxColumn(default=True),
        },
    )
    st.caption(f"총 {len(edited)}대 · 맨 아래 빈 행에 입력하면 장비가 추가됩니다.")
    if st.button("변경 내용 저장", type="primary"):
        errors = db.save_equipment(edited.rename(columns={v: k for k, v in COLS.items()}))
        for e in errors:
            st.warning(e)
        if not errors:
            st.session_state.equip_saved = "장비 목록을 저장했습니다."
            st.session_state.pop("equip_editor", None)
            st.rerun()


def _import_box() -> None:
    st.caption("장비 현황 엑셀(예: '장비 종 대수 분류정리' 파일)을 올리면 '전수조사' 탭의 장비를 추가합니다. "
               "비고에 '불용'이라고 적힌 장비와 이미 등록된 장비번호는 건너뜁니다.")
    up = st.file_uploader("장비 현황 엑셀", type=["xlsx"], key="equip_import_file")
    if up is None:
        return
    try:
        items, retired, sheet = equip_import.read_equipment_file(up.getvalue())
    except Exception as e:  # 양식이 다른 파일
        st.error(f"파일을 읽지 못했습니다: {e}")
        return
    st.write(f"'{sheet}' 탭에서 장비 **{len(items)}대**를 찾았습니다 (불용 {len(retired)}대 제외).")
    st.dataframe([{"장비명": i["name"], "장비번호": i["code"], "장비구분": i["kind"], "비고": i["note"]} for i in items],
                 hide_index=True, width="stretch", height=260)
    if st.button(f"{len(items)}대 추가", type="primary", disabled=not items):
        n, skipped = db.add_equipment(items)
        st.session_state.equip_saved = f"장비 {n}대를 추가했습니다." + (
            f" 이미 있는 {len(skipped)}대는 건너뛰었습니다." if skipped else "")
        st.session_state.pop("equip_import_file", None)
        st.rerun()
