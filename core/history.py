"""장비 히스토리: 고장·문제 이력을 날짜순으로 쌓음 (장비ID로 연결, 사진 한 장 붙일 수 있음)."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core import db

T = "equip_history"


@st.cache_data(ttl=120, show_spinner=False)
def load() -> pd.DataFrame:
    df = db.get_store().read(T)
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df["equip_id"] = pd.to_numeric(df["equip_id"], errors="coerce")
    df = df.dropna(subset=["id", "equip_id"])
    df["id"] = df["id"].astype(int)
    df["equip_id"] = df["equip_id"].astype(int)
    df["date"] = df["date"].map(db.to_date)
    df["_o"] = df["date"].map(lambda d: d.toordinal() if d else 0)
    return df.sort_values(["_o", "id"], ascending=False).drop(columns="_o").reset_index(drop=True)


def _write(rows: list[dict]) -> None:
    db._save_master(T, sorted(rows, key=lambda r: int(r["id"])))
    load.clear()


def _all() -> list[dict]:
    return [r for r in db.get_store().read(T).to_dict("records") if str(r.get("id", "")).strip()]


def add(eid: int, day, content: str, thumb: str = "", photo: str = "") -> None:
    rows = _all()
    nid = max([int(float(r["id"])) for r in rows] or [0]) + 1
    rows.append({"id": nid, "equip_id": int(eid), "date": day, "content": content, "thumb": thumb, "photo": photo,
                 "created_at": db._now(), "created_by": db.who()})
    _write(rows)


def update(rid: int, **vals) -> None:
    rows = _all()
    for r in rows:
        if int(float(r["id"])) == rid:
            r.update(vals)
    _write(rows)


def delete(rid: int) -> None:
    _write([r for r in _all() if int(float(r["id"])) != rid])


def to_xlsx(df: pd.DataFrame, name_of: dict) -> bytes:
    view = pd.DataFrame({"날짜": df["date"], "장비": [name_of.get(i, "") for i in df["equip_id"]],
                         "내용": df["content"], "작성자": df["created_by"],
                         "사진": ["있음" if p else "" for p in df["photo"]]})
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        view.to_excel(xw, sheet_name="장비 히스토리", index=False)
        ws = xw.sheets["장비 히스토리"]
        for col, wdt in zip("ABCDE", (12, 30, 70, 10, 6)):
            ws.column_dimensions[col].width = wdt
    return bio.getvalue()
