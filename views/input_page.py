"""실적 입력: 달력에서 날짜를 눌러 입력합니다 (입력 방식은 달력 하나).
내려받기는 왼쪽 메뉴 '실적 내려받기'에서 합니다 (2026-11-04 위쪽 버튼은 중복이라 뺌)."""
from ui_style import page_header
from views import calendar_entry


def render() -> None:
    page_header("실적 입력", "실적")
    calendar_entry.render(header=False)
