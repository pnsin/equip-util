"""아직 만들지 않은 메뉴(유지보수 · 장비 정보 · CS활동)의 '준비 중' 화면."""
import html

import streamlit as st

from ui_style import page_header

GROUP = "장비 정보"

# 화면마다: (제목, 그림, 한 줄 설명)
SOON = {
    "maint": ("유지보수", "🔧", "점검 · 수리 기록을 모아 볼 수 있게 준비하고 있어요"),
    "info": ("장비 정보", "📘", "장비별 사양 · 사진 · 설명서를 한곳에 모을 예정이에요"),
    "cs": ("CS활동", "🤝", "업체 지원 · 상담 활동을 기록할 수 있게 준비하고 있어요"),
}


def _page(key: str) -> None:
    title, icon, body = SOON[key]
    page_header(title, GROUP)
    e = html.escape
    st.markdown(
        f'<div class="soon"><div class="soon-ic">{e(icon)}</div><div class="soon-tag">준비 중</div>'
        f'<div class="soon-h">곧 만나요!</div><div class="soon-b">{e(body)}</div>'
        '<div class="soon-dots"><i></i><i></i><i></i></div></div>', unsafe_allow_html=True)


def render_maint() -> None:
    _page("maint")


def render_info() -> None:
    _page("info")


def render_cs() -> None:
    _page("cs")
