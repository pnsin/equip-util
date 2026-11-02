import streamlit as st

st.set_page_config(page_title="장비 가동률 관리", page_icon="📊", layout="wide")

from core import db  # noqa: E402
from views import calendar_entry, companies, dashboard, entry, equipment, export, records, settings  # noqa: E402


def check_password() -> bool:
    try:
        pw = str(st.secrets.get("app_password", "") or "")
    except Exception:
        pw = ""
    if not pw or st.session_state.get("authed"):
        return True
    st.title("📊 장비 가동률 관리")
    value = st.text_input("접속 비밀번호", type="password")
    if value:
        if value == pw:
            st.session_state.authed = True
            st.rerun()
        st.error("비밀번호가 맞지 않습니다.")
    return False


def sidebar_user() -> None:
    members = db.get_settings().get("members") or []
    with st.sidebar:
        if members:
            cur = st.session_state.get("user")
            st.selectbox("👤 작성자", members, index=members.index(cur) if cur in members else None,
                         placeholder="이름을 선택하세요", key="_user_pick")
            st.session_state.user = st.session_state.get("_user_pick") or ""
        else:
            st.text_input("👤 작성자", value=st.session_state.get("user", ""), key="_user_text",
                          help="설정 메뉴에서 팀원 명단을 등록하면 목록에서 고를 수 있습니다.")
            st.session_state.user = st.session_state.get("_user_text", "")


if check_password():
    try:
        db.get_store()
    except db.StorageError as e:
        st.error(f"데이터 저장소에 연결하지 못했습니다: {e}")
        st.stop()
    if db.is_local():
        st.sidebar.warning("구글 시트가 연결되지 않아 임시 저장 중입니다. 앱이 재시작되면 데이터가 지워질 수 있습니다.")
    pg = st.navigation({
        "현황": [
            st.Page(dashboard.render, title="대시보드", icon="📊", url_path="dashboard", default=True),
        ],
        "실적": [
            st.Page(calendar_entry.render, title="달력 입력", icon="🗓️", url_path="calendar"),
            st.Page(entry.render, title="기간 실적 입력", icon="✍️", url_path="entry"),
            st.Page(records.render, title="실적 조회·수정", icon="📋", url_path="records"),
            st.Page(export.render, title="엑셀 내려받기", icon="📥", url_path="export"),
        ],
        "관리": [
            st.Page(equipment.render, title="장비 관리", icon="🔧", url_path="equipment"),
            st.Page(companies.render, title="업체 관리", icon="🏢", url_path="companies"),
            st.Page(settings.render, title="설정", icon="⚙️", url_path="settings"),
        ],
    })
    sidebar_user()
    pg.run()
