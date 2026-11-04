"""실적 입력: 하루씩(달력)과 여러 날 한 번에(기간)를 한 메뉴에서 고릅니다."""
import streamlit as st

from ui_style import page_header
from views import calendar_entry, entry, export

MODES = {"day": "하루씩 · 달력", "period": "여러 날 한 번에"}


def render() -> None:
    head, btn = st.columns([1, 0.2], vertical_alignment="center")
    with head:
        page_header("실적 입력", "실적")
    with btn:
        if st.button("실적 내려받기", icon=":material/download:", key="open_dl",
                     help="기간을 고르면 그 기간 실적을 예전 입력시트 양식 엑셀로 내려받습니다.", width="stretch"):
            export.download_dialog()
    mode = st.segmented_control(
        "입력 방식", list(MODES), format_func=MODES.get, key="input_mode", label_visibility="collapsed",
        default=st.session_state.get("input_mode_last", "day"),
        help="하루씩: 달력에서 날짜를 눌러 그날 쓴 장비를 입력합니다. "
             "여러 날 한 번에: 한 업체가 며칠~몇 주 동안 쓴 실적을 한 줄로 입력합니다.")
    mode = mode or st.session_state.get("input_mode_last", "day")
    st.session_state.input_mode_last = mode
    if mode == "period":
        entry.render(header=False)
    else:
        calendar_entry.render(header=False)
