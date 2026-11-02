import hmac

import streamlit as st

import ui_style  # noqa: E402

st.set_page_config(page_title=ui_style.SYSTEM_TITLE, page_icon=ui_style.favicon(), layout="wide",
                   initial_sidebar_state="expanded")

import importlib  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

from core import calc, db, itube, rules, seed  # noqa: E402
from views import calendar_entry, companies, common, dashboard, entry, equipment, export, records, settings, staff  # noqa: E402,E501

# 새 코드가 배포된 직후 Streamlit Cloud가 일부 파일만 새로 읽고 나머지는 옛 버전을 쓰는 일이 있어
# (예: "module 'core.db' has no attribute 'load_companies'"), 파일이 바뀐 모듈은 다시 읽어 옴.
# core 를 먼저, 그것을 쓰는 views 를 나중에 읽어야 views 가 새 core 함수를 가리킴.
for _m in (ui_style, seed, db, calc, rules, itube, common, calendar_entry, companies, dashboard, entry, equipment,
           export, records, settings, staff):
    _mt = os.path.getmtime(_m.__file__)
    if getattr(_m, "_src_mtime", None) != _mt:
        _m = importlib.reload(sys.modules[_m.__name__])
        _m._src_mtime = _mt

ui_style.apply_style()


def check_password() -> bool:
    try:
        pw = str(st.secrets.get("app_password", "") or "")
    except Exception:
        pw = ""
    if not pw or st.session_state.get("authed"):
        return True
    _, mid, _ = st.columns([1, 1.25, 1])
    with mid:
        st.markdown('<div style="height:7vh"></div>', unsafe_allow_html=True)
        with st.container(key="login_card"):
            ui_style.login_head()
            with st.form("login", border=False, enter_to_submit=True):
                value = st.text_input("비밀번호", type="password", placeholder="팀 공용 비밀번호",
                                      label_visibility="collapsed")
                if st.session_state.get("login_failed"):
                    st.markdown('<div class="login-err">비밀번호가 맞지 않습니다. 다시 입력해 주세요.</div>',
                                unsafe_allow_html=True)
                sent = st.form_submit_button("접속하기", type="primary", width="stretch")
            st.markdown('<div class="login-foot">비밀번호를 모르면 팀 장비 담당자에게 문의하세요.</div>',
                        unsafe_allow_html=True)
    if sent:
        if value and hmac.compare_digest(value.encode(), pw.encode()):
            st.session_state.authed = True
            st.session_state.pop("login_failed", None)
        else:
            st.session_state.login_failed = True
        st.rerun()
    return False


PAGES = {
    "현황": [
        st.Page(dashboard.render, title="대시보드", url_path="dashboard", default=True),
    ],
    "실적": [
        st.Page(calendar_entry.render, title="달력 입력", url_path="calendar"),
        st.Page(entry.render, title="기간 실적 입력", url_path="entry"),
        st.Page(records.render, title="실적 조회·수정", url_path="records"),
        st.Page(export.render, title="엑셀 내려받기", url_path="export"),
    ],
    "정보 입력": [
        st.Page(equipment.render, title="장비 정보", url_path="equipment"),
        st.Page(companies.render, title="업체 정보", url_path="companies"),
        st.Page(staff.render, title="담당자 정보", url_path="staff"),
    ],
    "설정": [
        st.Page(settings.render, title="설정 · 백업", url_path="settings"),
    ],
}


def sidebar(local: bool) -> None:
    with st.sidebar:
        ui_style.sidebar_brand()
        for group, pages in PAGES.items():
            ui_style.nav_group(group)
            for p in pages:
                st.page_link(p, label=p.title)
        st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
        st.divider()
        if st.button("↻ 데이터 새로고침", width="stretch",
                     help="다른 팀원이 방금 저장한 내용이나 구글 시트에서 직접 고친 내용을 다시 불러옵니다."):
            db.clear_caches()
            st.rerun()
        where = "임시 저장소 (재시작 시 지워질 수 있음)" if local else "구글 시트에 자동 저장"
        st.markdown(f'<div class="side-foot"><span class="dot{" off" if local else ""}"></span>{where}</div>',
                    unsafe_allow_html=True)


if check_password():
    try:
        db.get_store()
    except db.StorageError as e:
        st.error(f"데이터 저장소(구글 시트)에 연결하지 못했습니다. 잠시 뒤 새로고침해 보세요.\n\n자세한 내용: {e}")
        st.stop()
    local = db.is_local()
    pg = st.navigation(PAGES, position="hidden")
    sidebar(local)
    if local:
        st.warning("구글 시트가 연결되지 않아 임시 저장 중입니다. 앱이 재시작되면 데이터가 지워질 수 있습니다.")
    pg.run()
