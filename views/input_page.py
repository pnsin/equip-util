"""실적 입력: 달력에서 날짜를 눌러 입력합니다 (입력 방식은 달력 하나)."""
import streamlit as st

from ui_style import page_header
from views import calendar_entry, export


def render() -> None:
    head, btn = st.columns([1, 0.2], vertical_alignment="center")
    with head:
        page_header("실적 입력", "실적")
    with btn:
        if st.button("실적 내려받기", icon=":material/download:", key="open_dl",
                     help="기간을 고르면 그 기간 실적을 예전 입력시트 양식 엑셀로 내려받습니다.", width="stretch"):
            export.download_dialog()
    calendar_entry.render(header=False)
