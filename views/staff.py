"""담당자(팀원) 목록 관리. 실적을 입력할 때 담당자는 여기 등록된 사람 중에서 고릅니다."""
import streamlit as st

from core import db
from views.common import confirm_delete, delete_config, split_deleted, with_delete_column

COLS = {
    "id": "id", "name": "이름", "phone": "연락처", "email": "이메일", "role": "담당업무",
    "active": "재직", "note": "비고",
}


def render() -> None:
    st.title("👤 담당자 정보 입력")
    msg = st.session_state.pop("staff_saved", None)
    if msg:
        st.success(msg)
    st.caption("실적을 입력할 때 담당자는 이 목록에서 고릅니다. 그만둔 사람은 지우지 말고 '재직'을 끄세요. "
               "그러면 새 입력 목록에서는 빠지고 지난 실적의 담당자 이름은 그대로 남습니다.")
    view = db.load_staff()[list(COLS)].rename(columns=COLS)
    # 빈 목록이면 열 형식을 알 수 없어 편집기가 오류를 내므로 형식을 고정
    view = view.astype({c: "string" for c in ("이름", "연락처", "이메일", "담당업무", "비고")} | {"재직": "bool", "id": "Int64"})
    edited = st.data_editor(
        with_delete_column(view), key="staff_editor", num_rows="dynamic", hide_index=True, width="stretch",
        column_order=["삭제"] + [c for c in COLS.values() if c != "id"],
        column_config=delete_config() | {
            "이름": st.column_config.TextColumn(required=True),
            "재직": st.column_config.CheckboxColumn(default=True, width="small"),
            "담당업무": st.column_config.TextColumn(help="예: 시험 장비, 5Ah 제조 라인"),
            "비고": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption(f"총 {len(edited.dropna(subset=['이름']))}명 · 지울 행은 '삭제'에 체크하고, 맨 아래 빈 행에 입력하면 추가됩니다.")
    edited, deleted = split_deleted(edited, "이름")
    ok = confirm_delete(deleted, "staff_editor_del", "명")
    if st.button("변경 내용 저장", type="primary", disabled=not ok):
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
