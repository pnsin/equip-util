"""i-Tube 업로드 규칙 검사 (양식의 유의사항 기준)."""
from __future__ import annotations

import calendar
import datetime as dt

from core import seed
from core.db import digits, to_date, to_num, to_str


def add_months(d: dt.date, n: int) -> dt.date:
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def validate(rec: dict) -> list[str]:
    errs: list[str] = []
    s, e = to_date(rec.get("start_date")), to_date(rec.get("end_date"))
    if not s or not e:
        errs.append("사용시작일과 사용종료일을 입력하세요.")
    else:
        if e < s:
            errs.append("사용종료일이 사용시작일보다 빠릅니다.")
        elif s.year != e.year:
            errs.append("사용시작일과 사용종료일은 같은 해여야 합니다 (i-Tube 규칙 7). 해를 넘기면 두 건으로 나눠 입력하세요.")
        elif e > add_months(s, 2) - dt.timedelta(days=1):
            errs.append("사용 기간은 2개월 이내여야 합니다 (i-Tube 규칙 8).")

    hours = to_num(rec.get("hours"), 0)
    if hours <= 0:
        errs.append("사용시간은 1시간 이상이어야 합니다.")
    elif hours != int(hours):
        errs.append("사용시간은 정수로 입력하세요 (i-Tube 양식은 정수만 허용).")
    elif s and e and e >= s and hours > ((e - s).days + 1) * 24:
        errs.append(f"사용시간 {int(hours)}h가 사용기간({(e - s).days + 1}일 × 24h)을 넘습니다.")
    if to_num(rec.get("fee"), 0) < 0:
        errs.append("사용료는 0 이상이어야 합니다.")

    if to_str(rec.get("purpose")) not in seed.PURPOSES:
        errs.append("사용목적을 선택하세요.")
    ut = to_str(rec.get("usage_type"))
    if ut not in seed.USAGE_TYPES:
        errs.append("활용유형을 선택하세요.")

    brn_raw = to_str(rec.get("brn"))
    if brn_raw and digits(brn_raw) != brn_raw.replace("-", ""):
        errs.append("사업자등록번호는 숫자만 입력하세요.")
    elif brn_raw and len(digits(brn_raw)) != 10:
        errs.append("사업자등록번호는 10자리 숫자입니다.")
    if ut in ("외부", "간접지원") and not (to_str(rec.get("company")) and digits(brn_raw)):
        errs.append("외부·간접지원은 사용기관 기업명과 사업자등록번호가 필요합니다 (i-Tube 규칙 3).")
    if ut == "내부 타부서" and not to_str(rec.get("dept")):
        errs.append("내부 타부서는 내부부서명이 필요합니다 (i-Tube 규칙 3).")

    ind, item, sub = to_str(rec.get("industry")), to_str(rec.get("item")), to_str(rec.get("sub_item"))
    if not (ind and item and sub):
        errs.append("업종·품목·세부품목을 모두 선택하세요.")
    elif item not in seed.ITEMS.get(ind, []) or sub not in seed.SUBITEMS.get(item, []):
        errs.append(f"업종·품목·세부품목 조합이 맞지 않습니다 ({ind} → {item} → {sub}).")
    return errs
