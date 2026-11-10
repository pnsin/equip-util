"""재무팀 매출장: 재단 재무팀이 보내 주는 '장비사용수수료 매출장' 엑셀을 올려 우리 팀 줄만 담습니다.

- 팀 이름이 바뀌어도(차세대전지팀 → 배터리산업팀) 두 이름 모두 우리 팀으로 봅니다.
- 재무팀 파일은 누적이라 같은 줄이 계속 들어 있음 → 세금일자·사업자번호·발행내역·공급가로 같은 줄을 알아보고
  이미 있으면 새로 넣지 않고 입금 칸만 최신으로 고칩니다. (파일 안에 똑같은 줄이 둘이면 #2 로 구분)
"""
from __future__ import annotations

import datetime as dt
import io
import re

import pandas as pd
import streamlit as st

from core import db

TEAMS = ("차세대전지팀", "배터리산업팀")
HEAD = {"세금일자": "tax_date", "팀명": "team", "담당자": "staff", "업체명": "company", "사업자번호": "brn",
        "발행내역": "item", "공급가": "supply", "부가세": "vat", "합계": "total", "입금일자(1차)": "paid1_date",
        "입금금액(1차)": "paid1", "입금일자(2차)": "paid2_date", "입금금액(2차)": "paid2", "미수금": "unpaid"}
MONEY = ("supply", "vat", "total", "paid1", "paid2", "unpaid")
DATES = ("tax_date", "paid1_date", "paid2_date")


def _date(v) -> str:
    d = db.to_date(v)
    return d.isoformat() if d else ""


def _money(v) -> str:
    n = db.to_num(str(v).replace(",", "") if isinstance(v, str) else v)
    return str(int(round(n))) if n is not None else ""


def _key(r: dict) -> str:
    brn = re.sub(r"\D", "", str(r["brn"])) or re.sub(r"\s", "", str(r["company"]))
    return "|".join([r["tax_date"], brn, re.sub(r"\s", "", str(r["item"])), r["supply"]])


def read_file(data: bytes) -> pd.DataFrame:
    """엑셀에서 우리 팀 줄만 → 내부 열 이름. 제목 줄 위치가 달라도 '세금일자' 가 있는 줄을 찾음."""
    raw = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    hit = [i for i, row in raw.iterrows() if any(str(x).strip() == "세금일자" for x in row)]
    if not hit:
        raise ValueError("'세금일자' 제목이 있는 줄을 못 찾았어요. 재무팀 매출장 파일이 맞는지 봐 주세요.")
    df = raw.iloc[hit[0] + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[hit[0]]]
    df = df[[c for c in HEAD if c in df.columns]].rename(columns=HEAD)
    df["team"] = df["team"].map(lambda v: str(v).strip() if pd.notna(v) else "")
    df = df[df["team"].isin(TEAMS)]
    out = []
    seen: dict[str, int] = {}
    for r in df.to_dict("records"):
        rec = {k: ("" if pd.isna(r.get(k)) else str(r.get(k)).strip()) for k in HEAD.values() if k not in MONEY + DATES}
        rec |= {k: _date(r.get(k)) for k in DATES} | {k: _money(r.get(k)) for k in MONEY}
        k = _key(rec)
        seen[k] = seen.get(k, 0) + 1
        rec["key"] = k if seen[k] == 1 else f"{k}#{seen[k]}"
        out.append(rec)
    return pd.DataFrame(out, columns=["key"] + list(HEAD.values()))


@st.cache_data(ttl=120, show_spinner=False)
def load() -> pd.DataFrame:
    df = db._tab("fee_ledger")
    for c in MONEY:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in DATES:
        df[c] = df[c].map(db.to_date)
    return df.sort_values("tax_date", key=lambda s: s.map(lambda d: d.toordinal() if d else 0),
                          ascending=False).reset_index(drop=True)


def _nm(v) -> str:
    return re.sub(r"\(주\)|㈜|주식회사|\(유\)|\s", "", str(v))


def add_companies(new: pd.DataFrame) -> int:
    """매출장에 처음 보는 업체가 있으면 업체 목록에 추가 (사업자번호 → 이름 순으로 같은 업체인지 봄)."""
    comp = db.load_companies()
    brns = {re.sub(r"\D", "", str(b)) for b in comp["brn"]} - {""}
    names = {_nm(n) for n in comp["name"]}
    add = []
    for r in new.drop_duplicates("company").to_dict("records"):
        b = re.sub(r"\D", "", str(r["brn"]))
        if not r["company"] or (b and b in brns) or _nm(r["company"]) in names:
            continue
        add.append({c: "" for c in db.COMPANY_TEXT} | {"id": None, "name": r["company"], "brn": r["brn"],
                                                        "note": "재무팀 매출장에서 추가"})
        brns.add(b)
        names.add(_nm(r["company"]))
    if add:
        db.save_companies(pd.concat([comp, pd.DataFrame(add)], ignore_index=True))
    return len(add)


def merge(new: pd.DataFrame) -> tuple[int, int, int]:
    """올린 줄을 저장된 매출장에 합침 → (새로 넣음, 입금 고침, 이미 있음)."""
    cur = db.get_store().read("fee_ledger")
    rows = {str(r["key"]): dict(r) for r in cur.to_dict("records")}
    ids = pd.to_numeric(cur["id"], errors="coerce").dropna()
    nid = int(ids.max()) + 1 if len(ids) else 1
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    add = upd = same = 0
    for r in new.to_dict("records"):
        old = rows.get(r["key"])
        if old is None:
            rows[r["key"]] = r | {"id": nid, "imported_at": now}
            nid += 1
            add += 1
        elif any(str(old.get(k, "")) != str(r[k]) for k in r):
            old.update(r)
            upd += 1
        else:
            same += 1
    if add or upd:
        db._save_master("fee_ledger", sorted(rows.values(), key=lambda x: int(x["id"])))
        load.clear()
    return add, upd, same
