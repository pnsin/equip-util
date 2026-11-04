"""휴지통(지운 실적·장비·업체·담당자 되살리기)과 수정 기록(누가 언제 무엇을 바꿨는지)."""
import pandas as pd
import streamlit as st

from core import db
from ui_style import empty_state, page_header

KIND = {"usage": "실적", "equipment": "장비", "companies": "업체", "staff": "담당자", "channels": "챔버 구성",
        "rates": "장비 단가", "quotes": "견적서"}


def render() -> None:
    page_header("휴지통 · 기록", "관리")
    msg = st.session_state.pop("trash_saved", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")
    tab_trash, tab_hist = st.tabs(["휴지통", "수정 기록"])

    with tab_trash:
        tr = db.load_trash()
        if tr.empty:
            empty_state("휴지통이 비어 있습니다", "지운 실적·장비·업체·담당자는 여기에 보관되어 언제든 되살릴 수 있습니다.", "○")
        else:
            c1, c2 = st.columns([1, 2])
            kinds = c1.multiselect("종류", list(KIND.values()), placeholder="전체", key="trash_kind")
            q = c2.text_input("검색", placeholder="장비·업체·이름으로 찾기", key="trash_q", icon=":material/search:")
            view = pd.DataFrame({
                "선택": False, "종류": tr["table"].map(KIND).fillna(tr["table"]), "내용": tr["summary"],
                "지운 사람": tr["deleted_by"], "지운 시각": tr["deleted_at"], "id": tr["id"],
            })
            if kinds:
                view = view[view["종류"].isin(kinds)]
            if q:
                view = view[view["내용"].str.contains(q, case=False, regex=False)]
            edited = st.data_editor(
                view, key="trash_editor", hide_index=True, width="stretch", disabled=["종류", "내용", "지운 사람", "지운 시각"],
                column_order=["선택", "종류", "내용", "지운 사람", "지운 시각"],
                column_config={"선택": st.column_config.CheckboxColumn(width="small"),
                               "내용": st.column_config.TextColumn(width="large"),
                               "지운 시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")})
            picked = list(edited.loc[edited["선택"].fillna(False).astype(bool), "id"])
            c1, c2, _ = st.columns([1.2, 1.2, 3])
            if c1.button(f"되살리기 ({len(picked)})", type="primary", icon=":material/restore_from_trash:",
                         disabled=not picked, width="stretch"):
                res = db.restore_trash(picked)
                st.session_state.trash_saved = (f"{res['restored']}건을 되살렸습니다."
                                                + (f" 이미 있는 실적 {res['skipped']}건은 건너뛰었습니다." if res["skipped"] else ""))
                st.session_state.pop("trash_editor", None)
                st.rerun()
            with c2.popover("영구 삭제", icon=":material/delete_forever:", disabled=not picked, width="stretch"):
                st.markdown(f"고른 {len(picked)}건을 휴지통에서도 지웁니다. 다시 되살릴 수 없습니다.")
                if st.button("영구 삭제", type="primary", key="purge_go"):
                    n = db.purge_trash(picked)
                    st.session_state.trash_saved = f"{n}건을 영구 삭제했습니다."
                    st.session_state.pop("trash_editor", None)
                    st.rerun()

    with tab_hist:
        h = db.load_history()
        if h.empty:
            empty_state("아직 기록이 없습니다", icon="○")
            return
        c1, c2, c3 = st.columns([1, 1, 2])
        people = sorted(p for p in h["who"].unique() if p)
        who = c1.multiselect("누가", people, placeholder="전체", key="hist_who")
        acts = c2.multiselect("작업", sorted(a for a in h["action"].unique() if a), placeholder="전체", key="hist_act")
        q = c3.text_input("검색", placeholder="내용으로 찾기", key="hist_q", icon=":material/search:")
        if who:
            h = h[h["who"].isin(who)]
        if acts:
            h = h[h["action"].isin(acts)]
        if q:
            h = h[h["summary"].str.contains(q, case=False, regex=False)]
        st.dataframe(h.rename(columns={"at": "시각", "who": "누가", "action": "작업", "target": "대상", "summary": "내용"}),
                     hide_index=True, width="stretch", height=560,
                     column_config={"시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                                    "내용": st.column_config.TextColumn(width="large")})
