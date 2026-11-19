"""장비 종·대수 세기 (2026-11-19, 사용자 기준표 '내부기준_260310(6종15대)'에 맞춤).

- 종 = 맨 위 장비 줄 (화면 위 '장비' 숫자와 같음). 방폭챔버 4대 묶음 = 1종 4대.
- 대수 = 종마다 실제 장비 수. 세부장비가 있으면 세부장비의 '대수' 합,
  '(양극)/(음극)' 처럼 짝인 장비는 한 대 (예: 5L 믹서(양극)+(음극) = 1대).
  세부장비 대수가 모두 0 이면 (예: 클린룸·드라이룸처럼 단가용으로만 나눈 줄) 장비 자신의 '대수'.
"""
from __future__ import annotations

import re

import pandas as pd

PAIR = re.compile(r"\s*[(（]\s*(양극|음극)\s*[)）]\s*$")


def _qty(v) -> float:
    q = pd.to_numeric(v, errors="coerce")
    return 1.0 if pd.isna(q) else float(q)


def units(eq: pd.DataFrame) -> pd.DataFrame:
    """종 하나당 한 줄: id, 대수. eq = db.load_equipment(full=True) 모양 (id, name, code, parent_id, qty)."""
    rec = {int(r["id"]): r for r in eq.to_dict("records")}
    kids: dict[int, list[int]] = {}
    for i, r in rec.items():
        p = r.get("parent_id")
        if p is not None and not pd.isna(p) and int(p) in rec:
            kids.setdefault(int(p), []).append(i)

    def count(i: int) -> float:
        ks = kids.get(i, [])
        if not ks:
            return _qty(rec[i].get("qty"))
        groups: dict[str, float] = {}
        for k in ks:  # 양극·음극 짝은 한 대
            name = str(rec[k].get("name") or "")
            key = PAIR.sub("", name).strip() if PAIR.search(name) else f"#{k}"
            groups[key] = max(groups.get(key, 0.0), count(k))
        n = sum(groups.values())
        return n if n > 0 else _qty(rec[i].get("qty"))

    child = {k for v in kids.values() for k in v}
    return pd.DataFrame([{"id": i, "대수": count(i)} for i in rec if i not in child], columns=["id", "대수"])
