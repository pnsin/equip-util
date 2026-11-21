"""실적 입력: 달력에서 날짜를 눌러 입력합니다 (충방전기도 달력 카드에서 '시험(충방전)' → 센터 → 충방전기 → 채널).
충방전기 현황판은 왼쪽 메뉴 '현황 › 장비 가동 현황 › 시험(충방전)' (2026-11-21 이름 바꿈)."""
from views import calendar_entry


def render() -> None:
    calendar_entry.render()
