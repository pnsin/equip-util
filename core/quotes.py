"""견적서 화면에서 쓰는 계산 (화면 코드와 분리해 시험하기 쉽게).

- 장비 단가표: 장비 목록 + 저장된 단가를 합쳐 '장비 단가' 화면 표를 만듦
- 견적 줄: 장비를 고르면 단가를 채우고, 금액은 시간당 단가로 계산 (직접 넣은 금액은 그대로)
"""
from __future__ import annotations

import math
import re
import uuid

import pandas as pd

from core.quote_doc import has_amount, line_auto, num

MODES = ("의뢰", "직접")


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _n(v):
    """숫자 또는 None."""
    s = _s(v).replace(",", "")
    if not s:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


# ── 장비 단가표 ─────────────────────────────────────────────────

def rate_devices(eq: pd.DataFrame) -> pd.DataFrame:
    """단가를 매길 장비 = 실제로 빌려 쓰는 단위.

    - '슬리터(양극)'처럼 바로 위 장비 이름 뒤에 (양극)·(음극)만 붙은 장비는 뺌 (위 장비 단가를 씀)
    - 세부장비가 있는 묶음 장비(예: 전극제조 시스템)는 뺌. 세부장비가 (양극)·(음극)뿐이면 넣음
    - 불용 장비는 뺌
    """
    if eq.empty:
        return eq
    name_of = dict(zip(eq["id"].astype(int), eq["name"]))

    def parent(r):
        p = r.get("parent_id")
        return int(p) if p is not None and not pd.isna(p) else None

    recs = eq.to_dict("records")
    variant = {int(r["id"]) for r in recs
               if parent(r) is not None and str(r["name"]).startswith(str(name_of.get(parent(r), "")) + "(")}
    has_real_kids = {parent(r) for r in recs if parent(r) is not None and int(r["id"]) not in variant}
    keep = []
    for r in recs:
        retired = r.get("retired_on")
        keep.append(int(r["id"]) not in variant and int(r["id"]) not in has_real_kids
                    and (retired is None or pd.isna(retired)))
    return eq[keep]


def rate_table(eq: pd.DataFrame, rates: pd.DataFrame, chargers: set | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(장비 줄, 시험·기타 항목 줄). 장비 줄은 장비 목록 순서, 단가가 없는 장비도 빈 칸으로 보여 줌."""
    by_eq = {}
    for r in rates.to_dict("records"):
        e = _n(r.get("equip_id"))
        if e is not None and int(e) not in by_eq:
            by_eq[int(e)] = r
    dev = rate_devices(eq)
    if not eq.empty:  # 장비 목록에서 단가를 넣은 장비는 묶음 장비라도 포함 (장비 목록 순서 그대로)
        keep = set(dev["id"].astype(int)) | {i for i, r in by_eq.items() if not is_missing(r)}
        dev = eq[eq["id"].astype(int).isin(keep)]
    rows = []
    for d in dev.to_dict("records"):
        r = by_eq.get(int(d["id"]), {})
        rows.append({
            "id": _n(r.get("id")), "equip_id": int(d["id"]), "group": _s(d.get("group")),
            "equip": _s(d.get("short")) or _s(d.get("name")),
            "name": _s(r.get("name")) or _s(d.get("name")), "spec": _s(r.get("spec")),
            "unit": _s(r.get("unit")) or ("ch" if int(d["id"]) in (chargers or ()) else "hr"),
            "price_req": _n(r.get("price_req")), "price_self": _n(r.get("price_self")), "note": _s(r.get("note")),
            "_named": bool(_s(r.get("name"))) and _s(r.get("name")) != _s(d.get("name")),
        })
    devices = pd.DataFrame(rows, columns=["id", "equip_id", "group", "equip", "name", "spec", "unit", "price_req",
                                          "price_self", "note", "_named"])
    known = set(dev["id"].astype(int)) if not dev.empty else set()
    ex = [r for r in rates.to_dict("records")
          if _n(r.get("equip_id")) is None or int(_n(r.get("equip_id"))) not in known]
    extras = pd.DataFrame([{"id": _n(r.get("id")), "equip_id": _n(r.get("equip_id")),
                            "name": _s(r.get("name")) or f"장비 #{_s(r.get('equip_id'))}",
                            "spec": _s(r.get("spec")), "unit": _s(r.get("unit")) or "hr",
                            "price_req": _n(r.get("price_req")), "price_self": _n(r.get("price_self")),
                            "note": _s(r.get("note"))} for r in ex],
                          columns=["id", "equip_id", "name", "spec", "unit", "price_req", "price_self", "note"])
    return devices, extras


def is_missing(row: dict) -> bool:
    return _n(row.get("price_req")) is None and _n(row.get("price_self")) is None


# ── 견적 줄에서 고르는 장비·항목 ───────────────────────────────

def pick_options(devices: pd.DataFrame, extras: pd.DataFrame) -> dict[str, dict]:
    """고르기 칸에 보일 이름 → 단가 정보. 장비는 장비 목록의 짧은 이름, 기타 항목은 항목 이름."""
    out: dict[str, dict] = {}
    for r in devices.to_dict("records"):
        out[r["equip"]] = {"equip_id": r["equip_id"], "name": r["name"], "spec": r["spec"], "unit": r["unit"],
                           "price_req": r["price_req"], "price_self": r["price_self"]}
    for r in extras.to_dict("records"):
        label = r["name"]
        if not label:
            continue
        if label in out:
            label = f"{label} (항목)"
        out[label] = {"equip_id": None, "name": r["name"], "spec": r["spec"], "unit": r["unit"],
                      "price_req": r["price_req"], "price_self": r["price_self"]}
    return out


def option_price(opt: dict, mode: str):
    """이용 방식에 맞는 단가. 직접 단가가 없으면 의뢰 단가 (기타 항목은 단가가 하나)."""
    a, b = _n(opt.get("price_req")), _n(opt.get("price_self"))
    if mode == "직접":
        return b if b is not None else a
    return a if a is not None else b


# ── 견적 줄 편집 ────────────────────────────────────────────────

LINE_KEYS = ("key", "pick", "mode", "name", "spec", "note", "count", "qty", "unit", "price", "difficulty",
             "amount", "manual", "ch")


def new_line(form: str) -> dict:
    ln = {k: None for k in LINE_KEYS}
    ln.update(key=uuid.uuid4().hex[:10], mode="의뢰", unit="hr", manual=False)
    if form == "시험":
        ln.update(count=1, difficulty=1)
    return ln


def _same(a, b) -> bool:
    na, nb = _n(a), _n(b)
    if na is not None or nb is not None:
        return na == nb
    return _s(a) == _s(b)


def apply_line_edits(form: str, prev: list[dict], edited: list[dict], options: dict[str, dict]) -> list[dict]:
    """표에서 고친 줄을 정리합니다.

    - 장비 고르기 / 이용 방식을 바꾸면: 장비명·용량·단위·단가를 단가표에서 채움
    - 사용량·단가 등이 바뀌면: 금액을 다시 계산 (직접 넣은 금액은 그대로)
    - 금액 칸을 고치면: 그 금액을 그대로 씀 ('직접' 표시). 금액을 지우거나 '직접'을 끄면 다시 자동 계산
    """
    before = {p.get("key"): p for p in prev if p.get("key")}
    out = []
    for e in edited:
        ln = {k: e.get(k) for k in LINE_KEYS}
        key = _s(ln.get("key"))
        p = before.get(key) if key else None
        if not key:
            ln["key"] = uuid.uuid4().hex[:10]
            base = new_line(form)
            for k in ("mode", "unit", "count", "difficulty"):
                if _s(ln.get(k)) == "":
                    ln[k] = base[k]
        if _s(ln.get("mode")) not in MODES:
            ln["mode"] = "의뢰"
        manual = bool(ln.get("manual")) and has_amount(ln.get("amount"))
        picked = _s(ln.get("pick"))
        pick_changed = p is None and picked or (p is not None and (_s(p.get("pick")) != picked
                                                                   or _s(p.get("mode")) != _s(ln.get("mode"))))
        if picked and pick_changed and picked in options:
            opt = options[picked]
            if p is None or _s(p.get("pick")) != picked:
                ln["name"] = opt["name"]
                if opt.get("spec"):
                    ln["spec"] = opt["spec"] if form == "제조" else (ln.get("spec") or "")
                if opt.get("unit") and form == "제조":
                    ln["unit"] = opt["unit"]
            if _s(opt.get("unit")) == "ch" and _n(ln.get("ch")) is None:
                ln["ch"] = 1  # ch당 단가 → 채널 수를 넣게
            price = option_price(opt, _s(ln.get("mode")))
            if price is not None:
                ln["price"] = price
        auto = line_auto(form, ln)
        if p is not None:
            amount_touched = not _same(p.get("amount"), e.get("amount"))
            if amount_touched:
                manual = has_amount(e.get("amount"))
            if bool(p.get("manual")) and not bool(e.get("manual")):
                manual = False  # '직접' 체크를 끔 → 자동 계산으로
        elif has_amount(e.get("amount")) and not _same(e.get("amount"), auto):
            manual = True  # 새 줄에 금액부터 넣은 경우 (붙여넣기 포함)
        ln["manual"] = manual
        if not manual:
            ln["amount"] = round(auto) if auto else None
        else:
            ln["amount"] = _n(ln.get("amount"))
        out.append(ln)
    return out


def clean_extra(ex: dict) -> dict:
    """재료비·기술료 줄: 금액을 직접 넣지 않았으면 사용량 × 단가."""
    ex = dict(ex)
    q, pr = num(ex.get("qty")), num(ex.get("price"))
    if not bool(ex.get("manual")):
        ex["amount"] = round(q * pr) if (q and pr) else None
    return ex


def apply_extra_edits(prev: list[dict], edited: list[dict]) -> list[dict]:
    before = {p.get("key"): p for p in prev if p.get("key")}
    out = []
    for e in edited:
        ex = {k: e.get(k) for k in ("key", "name", "qty", "unit", "price", "amount", "manual")}
        key = _s(ex.get("key"))
        p = before.get(key) if key else None
        if not key:
            ex["key"] = uuid.uuid4().hex[:10]
        manual = bool(ex.get("manual")) and has_amount(ex.get("amount"))
        auto = num(ex.get("qty")) * num(ex.get("price"))
        if p is not None:
            if not _same(p.get("amount"), e.get("amount")):
                manual = has_amount(e.get("amount"))
            if bool(p.get("manual")) and not bool(e.get("manual")):
                manual = False
        elif has_amount(e.get("amount")) and not _same(e.get("amount"), auto):
            manual = True
        ex["manual"] = manual
        ex["amount"] = _n(ex.get("amount")) if manual else (round(auto) if auto else None)
        out.append(ex)
    return out


# ── 번호 · 발급대장 칸 ──────────────────────────────────────────

def seq_of(no: str) -> str:
    """'RAT-2611-145' → '145', 'RAT-2610-126-1' → '126-1'."""
    parts = _s(no).split("-", 2)
    s = parts[2] if len(parts) == 3 else _s(no)
    m = re.match(r"0*(\d.*)", s)
    return m.group(1) if m else s


def equip_text(lines: list[dict]) -> str:
    """발급대장 '기기명' 기본값: 견적 줄 장비명 (겹치면 한 번)."""
    names = []
    for ln in lines:
        n = _s(ln.get("name")).split("\n")[0]
        if n and n not in names:
            names.append(n)
    return ", ".join(names)


def requester_of(contact: str) -> str:
    """'유 정우 대리님' → '유정우' (발급대장 '의뢰자' 기본값)."""
    s = re.sub(r"\s*(님|대리|과장|차장|부장|팀장|책임|선임|주임|연구원|이사|대표|사원|매니저|프로)+\s*$", "", _s(contact))
    s = re.sub(r"(대리|과장|차장|부장|팀장|책임|선임|주임|연구원|이사|대표|사원|매니저|프로)님?$", "", s).strip()
    return s.replace(" ", "") if len(s.replace(" ", "")) <= 4 else s
