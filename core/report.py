"""주간업무보고 분류 (2026-11-19 사용자 요청): 장비 종합 현황의 가동률 · 수수료를 보고자료와 같은 분류로 봄.

- 장비: 장비 목록의 '보고분류' 칸. 비어 있으면 소속(상위) 장비의 값 → 대분류(이름만 맞춰) → 기타.
- 수수료: 재무팀 매출장 줄마다 '보고분류' 칸. 비어 있으면 '발행내역' 글자로 자동 분류 (FEE_RULES).
- 목표(KPI): 해마다 바뀌어서 설정 › KPI 목표에 연도별로 저장 (설정 키 'kpi').
"""
from __future__ import annotations

import re

import pandas as pd

CATS = ["5Ah 제조", "50Ah 제조", "배터리 모듈 제조", "사용환경모사", "방폭챔버", "충방전시험기", "환경시험", "진동시험",
        "분석평가", "워크인챔버", "SMT", "기타"]
OTHER = "기타"
# 대분류 이름이 보고 분류와 다른 것만
GROUP_MAP = {"5Ah 생산": "5Ah 제조", "50Ah 생산": "50Ah 제조", "배터리 시제품 생산": "배터리 모듈 제조",
             "분석평가장비": "분석평가", "Lab-scale 장비": OTHER}

# 발행내역 → 보고 분류 (위에서부터 처음 맞는 것). 장비를 알 수 없는 교육·입회시험 등은 기타
FEE_RULES: list[tuple[str, tuple[str, ...]]] = [
    (OTHER, ("현장실습", "아카데미", "교육")),
    ("SMT", ("SMT",)),
    ("50Ah 제조", ("50Ah",)),
    ("5Ah 제조", ("5Ah", "믹서", "코터", "전극", "셀조립", "배터리연구지원센터")),
    ("배터리 모듈 제조", ("모듈",)),
    ("방폭챔버", ("방폭",)),
    ("충방전시험기", ("충방전",)),
    ("진동시험", ("진동",)),
    ("환경시험", ("열충격",)),
    ("사용환경모사", ("충격", "낙하", "충돌", "침수", "살수", "분진", "압착")),
    ("환경시험", ("염수", "고온", "저온", "온도", "고도", "감압", "항온", "향온", "습", "부식", "결로", "신뢰성")),
    ("워크인챔버", ("워크인",)),
    ("분석평가", ("CT", "SEM", "분석", "전기화학")),
]

# 2026 주간업무보고 기준 (설정에 아무것도 없을 때 처음 채우는 값). 2026-11-19 사용자: 목표는 연도별 수수료·가동률 두 가지만
DEFAULT_KPI = {"fee": 500_000_000, "util_total": 64.0}


def norm(v) -> str:
    """입력값을 보고 분류 이름으로 (공백·대소문자 차이는 맞춰 줌). 모르는 이름이면 ''."""
    s = re.sub(r"\s", "", str(v or "")).lower()
    if not s:
        return ""
    for c in CATS:
        if re.sub(r"\s", "", c).lower() == s:
            return c
    for k, c in GROUP_MAP.items():
        if re.sub(r"\s", "", k).lower() == s:
            return c
    return ""


def equip_cats(eq: pd.DataFrame) -> dict[int, str]:
    """장비 ID → 보고 분류. 자기 칸 → 상위 장비 칸 → 대분류 → 기타."""
    if eq.empty:
        return {}
    own = {int(i): norm(v) for i, v in zip(eq["id"], eq.get("report_cat", pd.Series([""] * len(eq))))}
    grp = {int(i): norm(v) for i, v in zip(eq["id"], eq["group"])}
    parent = {int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)}
    out = {}
    for i in own:
        cur, seen = i, set()
        while cur is not None and cur not in seen:  # 자기나 위쪽 장비에 적힌 값
            if own.get(cur):
                out[i] = own[cur]
                break
            seen.add(cur)
            cur = parent.get(cur)
        else:
            cur, seen = i, set()
            while cur is not None and cur not in seen:  # 없으면 대분류 (자기 → 위쪽)
                if grp.get(cur):
                    out[i] = grp[cur]
                    break
                seen.add(cur)
                cur = parent.get(cur)
            else:
                out[i] = OTHER
    return out


def fee_cat(item) -> str:
    s = re.sub(r"\s", "", str(item or ""))
    up = s.upper()
    for cat, words in FEE_RULES:
        for w in words:
            if (w.upper() in up) if w.isascii() else (w in s):
                return cat
    return OTHER


def ledger_cats(df: pd.DataFrame) -> list[str]:
    """매출장 줄마다 보고 분류 (직접 고친 값이 있으면 그것)."""
    over = df["report_cat"] if "report_cat" in df else pd.Series([""] * len(df), index=df.index)
    return [norm(o) or fee_cat(i) for o, i in zip(over, df["item"])]


def kpi(cfg: dict, year: int) -> dict:
    """그 해 목표 {fee(원), util_total(%)}. 그 해가 없으면 가장 가까운 이전 해 → 2026 주간업무보고 값."""
    table = {int(y): v for y, v in (cfg.get("kpi") or {}).items() if str(y).isdigit()}
    prev = [y for y in sorted(table) if y <= year] or sorted(table)
    got = table[prev[-1]] if prev else {}
    return {"fee": got.get("fee", DEFAULT_KPI["fee"]), "util_total": got.get("util_total", DEFAULT_KPI["util_total"]),
            "year_set": year in table}
