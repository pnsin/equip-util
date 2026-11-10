"""담당자(팀원) 목록 관리. 실적을 입력할 때 담당자는 여기 등록된 사람 중에서 고릅니다."""
import streamlit as st

from core import db
from ui_style import page_header
from views.common import excel_box, pick_done, pick_table

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
    action, out, gone = pick_table(
        view, "staff_tbl", name_col="이름",
        column_order=[c for c in COLS.values() if c != "id"],
        column_config={
            "이름": st.column_config.TextColumn(required=True),
            "직급": st.column_config.TextColumn(help="예: 선임연구원"),
            "내선번호": st.column_config.TextColumn(help="예: 043-270-2410"),
            "생일": st.column_config.TextColumn(help="예: 03-15"),
            "담당업무": st.column_config.TextColumn(help="예: 팀장, 운영, 시험, 제조"),
            "비고": st.column_config.TextColumn(width="medium"),
        })
    st.caption(f"전체 {len(view)}명")
    if action:
        raw = out.rename(columns={v: k for k, v in COLS.items()})
        errors = db.check_staff(raw)
        for e in errors:
            st.error(e)
        if not errors:
            db.save_staff(raw)
            pick_done("staff_tbl")
            st.session_state.staff_saved = f"{len(gone)}명 삭제했어요." if gone else "저장했어요."
            st.rerun()
