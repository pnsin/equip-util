"""장비 리스트 엑셀(260310_장비 종 대수 분류정리, '내부기준' 탭)을 장비 표 행으로 바꿉니다.

엑셀 구조: 대분류 › 주장비(종) › 장비(i-Tube 등록 단위) › 세부장비(대수) › 세세부장비.
- 병합된 칸은 위 칸 값을 아래로 채워 읽습니다.
- 새 장비는 '장비명(한글)' 칸에 글자가 있거나 ITUBE번호가 바뀌는 행에서 시작합니다.
- 세부장비 이름이 장비 이름과 다르면 세부장비 행을, 세세부 이름이 세부장비와 다르면 그 아래 행을 만듭니다.
- 이미 앱에 있는 장비는 ITUBE번호(없으면 이름)로 찾아 ID를 그대로 씁니다 → 기존 실적이 그대로 이어짐.
"""
from __future__ import annotations

import io

import openpyxl
import pandas as pd

SHEET_PREFIX = "내부기준"
NONE_WORDS = {"미등록장비", "미등록", "-", "None"}

HEAD = {  # 엑셀 열 제목 → 키
    "대분류": "group", "주장비(종)": "species", "관리자": "manager", "장비명(한글)": "name", "장비구분": "kind_raw",
    "ITUBE번호": "code", "국가연구시설장비번호": "nfec", "구분": "category", "자산번호": "asset_no",
    "자산기준/수량": "asset_qty", "자산기준, 수량": "asset_qty", "자산기준 수량": "asset_qty", "세부장비": "sub", "대수": "sub_qty", "세세부장비/추후정리": "subsub",
    "구매처": "vendor", "제조사": "maker", "모델명": "model", "장비위치": "location", "시스템 구성": "system",
    "장비용도": "use", "비고": "note",
}
CHILD_KEYS = ("vendor", "maker", "model", "location", "use")


def clean(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    lines = [" ".join(x.replace("\t", " ").split()) for x in str(v).splitlines()]
    s = ", ".join(x for x in lines if x)
    return "" if s in NONE_WORDS else s


def itube_kind(raw: str) -> str:
    return "주장비" if raw.startswith("주장비") or not raw else "부장비"


def _read_rows(data: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    names = [n for n in wb.sheetnames if n.startswith(SHEET_PREFIX)]
    if not names:
        raise ValueError(f"'{SHEET_PREFIX}'으로 시작하는 탭이 없습니다.")
    ws = wb[names[-1]]
    head = [clean(c.value) for c in ws[1]]
    raw = [[c.value for c in row] for row in ws.iter_rows(min_row=1)]
    filled = [list(r) for r in raw]
    for m in ws.merged_cells.ranges:
        v = raw[m.min_row - 1][m.min_col - 1]
        for r in range(m.min_row, m.max_row + 1):
            for c in range(m.min_col, m.max_col + 1):
                filled[r - 1][c - 1] = v
    out = []
    for r_raw, r_fill in zip(raw[1:], filled[1:]):
        if not any(clean(v) for v in r_fill):
            continue
        rec = {"_raw": {}, "_fill": {}, "_rawcode": ""}
        for i, h in enumerate(head):
            k = HEAD.get(h)
            if k:
                rec["_raw"][k] = clean(r_raw[i]) if i < len(r_raw) else ""
                rec["_fill"][k] = clean(r_fill[i]) if i < len(r_fill) else ""
                if k == "code" and i < len(r_raw) and r_raw[i] is not None:
                    rec["_rawcode"] = str(r_raw[i]).strip()
        out.append(rec)
    return out


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse(data: bytes) -> list[dict]:
    """엑셀 → [{tmp, parent_tmp, name, code, ...}] (엑셀 순서)."""
    rows = _read_rows(data)
    units: list[list[dict]] = []
    cur_code = None
    for r in rows:
        rc = r["_rawcode"]
        # 장비명 칸에 글자가 있거나, ITUBE번호 칸이 새 번호·'미등록장비'이면 새 장비
        starts = bool(r["_raw"].get("name")) or (rc and (rc != cur_code or clean(rc) == ""))
        if starts or not units:
            units.append([])
        if rc:
            cur_code = rc
        units[-1].append(r)

    out: list[dict] = []
    for unit in units:
        f0, r0 = unit[0]["_fill"], unit[0]["_raw"]
        name = r0.get("name") or f0.get("sub") or f0.get("name")
        manager = next((u["_fill"]["manager"] for u in unit if u["_raw"].get("manager")), f0.get("manager", ""))
        top = {
            "tmp": len(out), "parent_tmp": None, "name": name, "code": f0.get("code", ""),
            "kind": itube_kind(f0.get("kind_raw", "")), "group": f0.get("group", ""), "species": f0.get("species", ""),
            "manager": manager, "nfec": f0.get("nfec", ""), "category": f0.get("category", ""),
            "asset_no": r0.get("asset_no", ""), "qty": _num(f0.get("asset_qty")), "system": f0.get("system", ""),
            "note": f0.get("note", ""), "in_kpi": True, "top_asset": r0.get("asset_no", ""),
        } | {k: f0.get(k, "") for k in CHILD_KEYS}
        out.append(top)
        # 세부장비별 세세부 이름 (하나뿐이면 세부장비 이름을 그 이름으로 바꿔 한 단계로)
        groups: dict[str, list] = {}
        for u in unit:
            f, rr = u["_fill"], u["_raw"]
            sub = f.get("sub", "")
            subsub = rr.get("subsub", "") or f.get("subsub", "")
            groups.setdefault(sub, []).append((f, rr, subsub))
        for sub, items in groups.items():
            kids = [x for x in dict.fromkeys(ss for _, _, ss in items) if x and not same(x, sub)]
            parent = top
            if sub and not same(sub, name):
                if len(kids) == 1 and len(items) == 1:
                    sub, kids = kids[0], []
                f, rr, _ = items[0]
                parent = _child(len(out), top, sub, f, rr if not kids else {}, _num(f.get("sub_qty")))
                out.append(parent)
            for f, rr, ss in items:
                if ss in kids and not same(ss, name):
                    out.append(_child(len(out), parent, ss, f, rr, 1))
                    kids.remove(ss)
    return out


def same(a: str, b: str) -> bool:
    """띄어쓰기만 다른 이름은 같은 것으로 봄."""
    return a.replace(" ", "") == b.replace(" ", "")


def _child(tmp: int, parent: dict, name: str, f: dict, rr: dict, qty) -> dict:
    return {
        "tmp": tmp, "parent_tmp": parent["tmp"], "name": name, "code": "", "kind": "세부장비",
        "group": parent["group"], "species": parent["species"], "manager": parent["manager"], "nfec": "",
        "category": "", "asset_no": rr.get("asset_no", "") if rr.get("asset_no") != parent.get("top_asset") else "",
        "qty": qty, "system": "", "note": "", "in_kpi": False, "top_asset": parent.get("top_asset", ""),
    } | {k: f.get(k, "") for k in CHILD_KEYS}


def merge_with_existing(parsed: list[dict], existing: pd.DataFrame) -> list[dict]:
    """기존 장비와 맞춰 ID를 정하고 장비 표에 쓸 행을 돌려줍니다. 엑셀에 없는 기존 장비는 맨 뒤에 그대로 둡니다."""
    ex = existing.to_dict("records") if not existing.empty else []
    by_code = {str(r["code"]).strip(): r for r in ex if str(r["code"]).strip()}
    by_name = {}
    for r in ex:
        if not str(r["code"]).strip():
            by_name.setdefault(str(r["name"]).strip(), r)
    next_id = max([int(r["id"]) for r in ex] + [0]) + 1
    used, tmp_to_id, out = set(), {}, []
    for p in parsed:
        hit = None
        if p["parent_tmp"] is None:
            hit = by_code.get(p["code"]) if p["code"] else by_name.get(p["name"])
        if hit is not None and int(hit["id"]) not in used:
            rid = int(hit["id"])
        else:
            hit, rid = None, next_id
            next_id += 1
        used.add(rid)
        tmp_to_id[p["tmp"]] = rid
        rec = {k: v for k, v in p.items() if k not in ("tmp", "parent_tmp", "top_asset")}
        rec["id"] = rid
        rec["parent_id"] = tmp_to_id[p["parent_tmp"]] if p["parent_tmp"] is not None else None
        rec["order"] = len(out) + 1
        if hit is not None:  # 앱에서 넣어 둔 값은 엑셀이 비어 있을 때 살림
            for k in ("annual_hours", "acquired_on", "retired_on", "in_kpi"):
                rec[k] = hit.get(k)
            for k in ("manager", "model", "location", "use", "nfec"):
                if not rec.get(k) and str(hit.get(k) or "").strip():
                    rec[k] = hit[k]
        elif p["parent_tmp"] is None and not p["code"]:
            rec["in_kpi"] = False  # 처음 들어오는 미등록 장비는 합계에서 빼 둠 (화면에서 켤 수 있음)
        out.append(rec)
    for r in ex:
        if int(r["id"]) not in used:
            out.append(dict(r) | {"order": len(out) + 1})
    return out
