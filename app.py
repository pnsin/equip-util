import hmac
import html

import streamlit as st

import ui_style  # noqa: E402

st.set_page_config(page_title=ui_style.SYSTEM_TITLE, page_icon=ui_style.favicon(), layout="wide",
                   initial_sidebar_state="auto")

import importlib  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

from core import calc, db, itube, rules, seed  # noqa: E402
from views import (calendar_entry, companies, common, dashboard, entry, equip_detail, equipment, export,  # noqa: E402
                   input_page,
                   records, settings, staff, trash)
from core.terms import w  # noqa: E402

# 새 코드가 배포된 직후 Streamlit Cloud가 일부 파일만 새로 읽고 나머지는 옛 버전을 쓰는 일이 있어
# (예: "module 'core.db' has no attribute 'load_companies'"), 파일이 바뀐 모듈은 다시 읽어 옴.
# core 를 먼저, 그것을 쓰는 views 를 나중에 읽어야 views 가 새 core 함수를 가리킴.
for _m in (ui_style, seed, db, calc, rules, itube, common, calendar_entry, entry, input_page, companies, dashboard,
           equip_detail,
           equipment, export, records, settings, staff, trash):
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
    failed = bool(st.session_state.get("login_failed"))
    _, mid, _ = st.columns([1, 1.25, 1])
    with mid:
        ui_style.login_bg()
        st.markdown('<div class="login-gap"></div>', unsafe_allow_html=True)
        with st.container(key="login_card"):
            ui_style.login_head(failed)
            with st.form("login", border=False, enter_to_submit=True):
                value = st.text_input("비밀번호", type="password", placeholder="비밀번호", icon=":material/lock:",
                                      label_visibility="collapsed")
                if failed:
                    st.markdown('<div class="login-err">비밀번호가 맞지 않아요. 다시 입력해 주세요.</div>',
                                unsafe_allow_html=True)
                sent = st.form_submit_button("접속하기", type="primary", width="stretch",
                                             icon=":material/arrow_forward:", icon_position="right")
            ui_style.login_foot()
    if sent:
        if value and hmac.compare_digest(value.encode(), pw.encode()):
            st.session_state.authed = True
            st.session_state.pop("login_failed", None)
        else:
            st.session_state.login_failed = True
        st.rerun()
    return False


def undo_bar() -> None:
    """방금 한 저장·삭제를 되돌리는 띠 (1분 30초 동안 화면 위에 보임)."""
    last = db.last_undo()
    if not last or (db._now() - last["at"]).total_seconds() > 90:
        return
    with st.container(key="undo_bar", horizontal=True, vertical_alignment="center"):
        st.markdown(f"<span class='undo-txt'>방금 한 작업: <b>{html.escape(last['label'])}</b></span>",
                    unsafe_allow_html=True)
        if st.button("되돌리기", icon=":material/undo:", key="undo_top"):
            _undo()


def _undo() -> None:
    label = db.undo_last()
    if label:
        for k in [k for k in st.session_state if str(k).endswith("_editor") or str(k).startswith("cal_ed_")]:
            st.session_state.pop(k, None)
        st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
        st.session_state.entry_ver = st.session_state.get("entry_ver", 0) + 1
        st.toast(f"되돌렸습니다: {label}", icon=":material/undo:")
    st.rerun()


# 다른 메뉴에 다녀와도 기간·필터 선택이 그대로 남도록 (Streamlit은 안 보이는 화면의 선택값을 지움)
KEEP_SUFFIX = ("_kind", "_year", "_month", "_q", "_h", "_week", "_range")
KEEP_KEYS = {"dash_to_today", "dash_loc", "dash_use", "dash_kind_eq", "dash_cmp", "dash_only_kpi", "dash_base",
             "rec_eq", "rec_comp", "rec_writer", "rec_cols", "detail_sel", "input_mode"}


def keep_choices() -> None:
    for k in list(st.session_state):
        k = str(k)
        if k in KEEP_KEYS or (k.split("_")[0] in ("dash", "rec", "detail", "itube", "report") and k.endswith(KEEP_SUFFIX)):
            try:
                st.session_state[k] = st.session_state[k]
            except Exception:  # noqa: BLE001 - 값을 다시 넣을 수 없는 위젯은 건너뜀
                pass


PAGES = {
    "현황": [
        st.Page(dashboard.render, title="대시보드", url_path="home", default=True),
        st.Page(equip_detail.render, title="장비 상세", url_path="equip"),
    ],
    "실적": [
        st.Page(input_page.render, title="실적 입력", url_path="input"),
        st.Page(records.render, title="실적 목록", url_path="records"),
    ],
    "보고": [
        st.Page(export.render_itube, title="i-Tube 장비일지", url_path="itube"),
        st.Page(export.render_report, title=w("가동률 분석 보고서"), url_path="report"),
    ],
    "기준 정보": [
        st.Page(equipment.render, title="장비", url_path="equipment"),
        st.Page(companies.render, title="업체", url_path="companies"),
        st.Page(staff.render, title="담당자", url_path="staff"),
    ],
    "관리": [
        st.Page(settings.render, title="설정", url_path="settings"),
        st.Page(settings.render_data, title="가져오기 · 백업", url_path="data"),
        st.Page(trash.render, title="휴지통 · 기록", url_path="trash"),
    ],
}
common.PAGES.update({"equip": PAGES["현황"][1], "records": PAGES["실적"][1], "input": PAGES["실적"][0]})

# 예전 주소(/dashboard, /calendar …)로 들어와도 "Page not found" 없이 해당 화면이 열리게 하는 숨은 주소
ALIASES = [
    st.Page(dashboard.render, title="대시보드", url_path="dashboard"),
    st.Page(input_page.render, title="실적 입력", url_path="calendar"),
    st.Page(input_page.render, title="실적 입력", url_path="entry"),
    st.Page(export.render_itube, title="i-Tube 장비일지", url_path="export"),
]


def sidebar(local: bool) -> None:
    with st.sidebar:
        ui_style.sidebar_brand()
        for group, pages in PAGES.items():
            ui_style.nav_group(group)
            for p in pages:
                st.page_link(p, label=p.title)
        st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
        st.divider()
        last = db.last_undo()
        if last and st.button("마지막 작업 되돌리기", icon=":material/undo:", width="stretch", key="undo_side",
                              help=f"{last['at']:%H:%M} {last['label']}을(를) 취소합니다. "
                                   "여러 번 누르면 그 전 작업도 차례로 취소됩니다."):
            _undo()
        if st.button("데이터 새로고침", icon=":material/refresh:", width="stretch",
                     help="다른 팀원이 방금 저장한 내용이나 구글 시트에서 직접 고친 내용을 다시 불러옵니다."):
            db.clear_caches()
            st.rerun()
        where = "임시 저장소 (재시작 시 지워질 수 있음)" if local else "구글 시트에 자동 저장"
        st.markdown(f'<div class="side-foot"><span class="dot{" off" if local else ""}"></span>{where}</div>',
                    unsafe_allow_html=True)


# 주소(예: /input)로 바로 들어와도 접속 뒤에 그 화면이 열리도록 먼저 등록
pg = st.navigation({**PAGES, "": ALIASES}, position="hidden")

if check_password():
    try:
        db.get_store()
    except db.StorageError as e:
        st.error(f"데이터 저장소(구글 시트)에 연결하지 못했습니다. 잠시 뒤 새로고침해 보세요.\n\n자세한 내용: {e}")
        st.stop()
    local = db.is_local()
    sidebar(local)
    if local:
        st.warning("구글 시트가 연결되지 않아 임시 저장 중입니다. 앱이 재시작되면 데이터가 지워질 수 있습니다.")
    undo_bar()
    keep_choices()
    pg.run()
