"""휴지통(지운 실적·장비·업체·담당자 되살리기)과 수정 기록(누가 언제 무엇을 바꿨는지)."""
import pandas as pd
import streamlit as st

from core import db
from ui_style import empty_state, page_header

KIND = {"usage": "실적", "equipment": "장비", "companies": "업체", "staff": "담당자", "channels": "챔버 구성",
        "rates": "장비 단가", "quotes": "견적서", "maint": "유지보수", "cs": "CS활동"}


def render() -> None:
    page_header("휴지통 · 기록", "관리")
    msg = st.session_state.pop("trash_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    tab_trash, tab_hist = st.tabs(["휴지통", "수정 기록"])

    with tab_trash:
        tr = db.load_trash()
        if tr.empty:
            empty_state("휴지통이 비어 있습니다", "지운 실적·장비·업체·담당자는 여기에 보관되어 언제든 되살릴 수 있습니다.", "○")
        else:
            c1, c2 = st.columns([1, 2])
            kinds = c1.multiselect("종류", list(KIND.values()), placeholder="전체", key="trash_kind")
            q = c2.text_input("검색", placeholder="장비·업체·이름으로 찾기", key="trash_q", icon=":material/search:")
            all_on = st.checkbox("전체 선택", key="trash_all", on_change=lambda: st.session_state.pop("trash_editor", None))
            view = pd.DataFrame({
                "선택": all_on, "종류": tr["table"].map(KIND).fillna(tr["table"]), "내용": tr["summary"],
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
                               "종류": st.column_config.TextColumn(width=90),
                               "내용": st.column_config.TextColumn(width=800),
                               "지운 사람": st.column_config.TextColumn(width=80),
                               "지운 시각": st.column_config.DatetimeColumn("지운 일시", format="YYYY-MM-DD HH:mm", width=140)})
            picked = list(edited.loc[edited["선택"].fillna(False).astype(bool), "id"])
            c1, c2, _, c4 = st.columns([1.2, 1.2, 1.4, 1.2])
            if c1.button(f"데이터 복구 ({len(picked)})", type="primary", icon=":material/restore_from_trash:",
                         disabled=not picked, width="stretch"):
                res = db.restore_trash(picked)
                st.session_state.trash_saved = (f"{res['restored']}건을 되살렸습니다."
                                                + (f" 이미 있는 실적 {res['skipped']}건은 건너뛰었습니다." if res["skipped"] else ""))
                st.session_state.pop("trash_editor", None)
                st.rerun()
            with c2.popover(f"영구 삭제 ({len(picked)})", icon=":material/delete_forever:", disabled=not picked, width="stretch"):
                st.markdown(f"고른 {len(picked)}건을 휴지통에서도 지웁니다. 다시 되살릴 수 없습니다.")
                if st.button("영구 삭제", type="primary", key="purge_go"):
                    n = db.purge_trash(picked)
                    st.session_state.trash_saved = f"{n}건을 영구 삭제했습니다."
                    st.session_state.pop("trash_editor", None)
                    st.rerun()
            with c4.popover("휴지통 비우기", icon=":material/delete_sweep:", width="stretch"):
                st.markdown(f"휴지통의 {len(tr)}건을 모두 지웁니다. 다시 되살릴 수 없습니다.")
                if st.button("모두 비우기", type="primary", key="purge_all"):
                    n = db.purge_trash(list(tr["id"]))
                    st.session_state.trash_saved = f"{n}건을 영구 삭제했습니다."
                    st.session_state.pop("trash_editor", None)
                    st.session_state.pop("trash_all", None)
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
        view = h.rename(columns={"at": "일시", "who": "누가", "action": "작업", "target": "대상", "summary": "내용"})
        view.insert(0, "선택", False)
        ed = st.data_editor(view, key=f"hist_ed_{st.session_state.get('hist_ver', 0)}", hide_index=True, width="stretch",
                            height=560, disabled=["일시", "누가", "작업", "대상", "내용"],
                            column_order=["선택", "일시", "누가", "작업", "대상", "내용"],
                            column_config={"선택": st.column_config.CheckboxColumn(width=52),
                                           "일시": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm", width=140),
                                           "누가": st.column_config.TextColumn(width=70),
                                           "작업": st.column_config.TextColumn(width=80),
                                           "대상": st.column_config.TextColumn(width=100),
                                           "내용": st.column_config.TextColumn(width=900)})
        pick = ed[ed["선택"].fillna(False).astype(bool)]
        with st.popover(f"선택한 기록 삭제 ({len(pick)})", icon=":material/delete:", disabled=pick.empty):
            st.markdown(f"고른 기록 {len(pick)}건을 지웁니다. 되살릴 수 없습니다.")
            if st.button("삭제", type="primary", key="hist_del_go"):
                keys = [(a.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(a) else "", w, ac, t, sm)
                        for a, w, ac, t, sm in zip(pick["일시"], pick["누가"], pick["작업"], pick["대상"], pick["내용"])]
                n = db.delete_history(keys)
                st.session_state.trash_saved = f"기록 {n}건을 지웠어요."
                st.session_state.hist_ver = st.session_state.get("hist_ver", 0) + 1
                st.rerun()
