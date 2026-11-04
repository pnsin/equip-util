"""실적 입력: 달력에서 날짜를 눌러 입력합니다. 충방전기는 같은 화면에서 '충방전기'로 바꿔 챔버별 현황을 봅니다."""
import streamlit as st

from ui_style import page_header
from views import calendar_entry, charger_board, export


def render() -> None:
    head, mid, btn = st.columns([0.55, 0.45, 0.2], vertical_alignment="center")
    with head:
        page_header("실적 입력", "실적")
    with mid:  # 메뉴를 늘리지 않고 같은 화면에서 보기만 바꿈 (입력은 달력 카드에서 한 번)
        st.markdown("""<style>.st-key-in_view_box [data-testid="stButtonGroup"] {background: #E6EAF0; border-radius: 999px;
  padding: 3px; width: fit-content;}
.st-key-in_view_box [data-testid="stButtonGroup"] button {border: none !important; border-radius: 999px !important;
  background: transparent !important; padding: 0 18px !important; min-height: 32px !important;}
.st-key-in_view_box [data-testid="stButtonGroup"] button[aria-checked="true"] {background: #fff !important;
  box-shadow: 0 1px 4px rgba(17, 28, 46, .15);}
.st-key-in_view_box [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: var(--accent) !important;}
.st-key-in_view_box [data-testid="stButtonGroup"] button p {font-weight: 700;}</style>""", unsafe_allow_html=True)
        with st.container(key="in_view_box"):
            st.session_state.setdefault("in_view", "달력")
            view = st.segmented_control("보기", ["달력", "충방전기"], key="in_view", label_visibility="collapsed",
                                        format_func={"달력": ":material/calendar_month: 달력",
                                                     "충방전기": ":material/battery_charging_full: 충방전기"}.get)
    with btn:
        if st.button("실적 내려받기", icon=":material/download:", key="open_dl",
                     help="기간을 고르면 그 기간 실적을 예전 입력시트 양식 엑셀로 내려받습니다.", width="stretch"):
            export.download_dialog()
    if view == "충방전기":
        charger_board.render()
    else:
        calendar_entry.render(header=False)
