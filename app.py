import hmac

import streamlit as st

st.set_page_config(page_title="장비 가동률 관리", page_icon="📊", layout="wide")

import importlib  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

from core import calc, db, itube, rules, seed  # noqa: E402
from views import calendar_entry, companies, common, dashboard, entry, equipment, export, records, settings, staff  # noqa: E402,E501

# 새 코드가 배포된 직후 Streamlit Cloud가 일부 파일만 새로 읽고 나머지는 옛 버전을 쓰는 일이 있어
# (예: "module 'core.db' has no attribute 'load_companies'"), 파일이 바뀐 모듈은 다시 읽어 옴.
# core 를 먼저, 그것을 쓰는 views 를 나중에 읽어야 views 가 새 core 함수를 가리킴.
for _m in (seed, db, calc, rules, itube, common, calendar_entry, companies, dashboard, entry, equipment, export,
           records, settings, staff):
    _mt = os.path.getmtime(_m.__file__)
    if getattr(_m, "_src_mtime", None) != _mt:
        _m = importlib.reload(sys.modules[_m.__name__])
        _m._src_mtime = _mt


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
        if hmac.compare_digest(value.encode(), pw.encode()):
            st.session_state.authed = True
            st.rerun()
        st.error("비밀번호가 맞지 않습니다.")
    return False


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
            st.Page(staff.render, title="담당자 관리", icon="👤", url_path="staff"),
            st.Page(settings.render, title="설정", icon="⚙️", url_path="settings"),
        ],
    })
    pg.run()
