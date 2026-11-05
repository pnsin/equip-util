"""담당자(팀원) 목록 관리. 실적을 입력할 때 담당자는 여기 등록된 사람 중에서 고릅니다."""
import streamlit as st

from core import db
from ui_style import page_header
from views.common import excel_box, confirm_delete, delete_config, split_deleted, with_delete_column

COLS = {
    "id": "id", "dept": "부서", "team": "팀", "name": "이름", "title": "직급", "phone": "내선번호",
    "role": "담당업무", "email": "이메일", "birthday": "생일", "note": "비고",
}
TEXT = ("부서", "팀", "이름", "직급", "내선번호", "담당업무", "이메일", "생일", "비고")


def render() -> None:
    page_header("담당자", "기준 정보")
    msg = st.session_state.pop("staff_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    staff = db.load_staff()

    def _apply_xl(m):
        errors = db.check_staff(m)
        if not errors:
            db.save_staff(m)
        return errors

    excel_box("staff_xl", staff, {k: v for k, v in COLS.items() if k != "id"}, "담당자", _apply_xl)
    view = staff[list(COLS)].rename(columns=COLS)
    # 빈 목록이면 열 형식을 알 수 없어 편집기가 오류를 내므로 형식을 고정
    view = view.astype({c: "string" for c in TEXT} | {"id": "Int64"})
    edited = st.data_editor(
        with_delete_column(view), key="staff_editor", num_rows="dynamic", hide_index=True, width="stretch",
        column_order=["삭제"] + [c for c in COLS.values() if c != "id"],
        column_config=delete_config() | {
            "이름": st.column_config.TextColumn(required=True),
            "직급": st.column_config.TextColumn(help="예: 선임연구원"),
            "내선번호": st.column_config.TextColumn(help="예: 043-270-2410"),
            "생일": st.column_config.TextColumn(help="예: 03-15"),
            "담당업무": st.column_config.TextColumn(help="예: 팀장, 운영, 시험, 제조"),
            "비고": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption(f"전체 {len(edited.dropna(subset=['이름']))}명")
    edited, deleted = split_deleted(edited, "이름")
    ok = confirm_delete(deleted, "staff_editor_del", "명")
    if st.button("변경 내용 저장", type="primary", disabled=not ok, icon=":material/save:"):
        raw = edited.rename(columns={v: k for k, v in COLS.items()})
        errors = db.check_staff(raw)
        for e in errors:
            st.error(e)
        if not errors:
            db.save_staff(raw)
            st.session_state.staff_saved = "담당자 목록을 저장했습니다." + (f" ({len(deleted)}명 삭제)" if deleted else "")
            st.session_state.pop("staff_editor", None)
            st.session_state.pop("staff_editor_del", None)
            st.rerun()
