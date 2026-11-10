"""CS활동: 업체를 대상으로 한 문의·상담, 방문, 기술지원, 요청·불만, 교육·견학 기록 ('CS활동' 시트 탭).

실적과 같이 행 단위로 저장해(동시에 여러 사람이 써도 서로 덮어쓰지 않음) 되돌리기·휴지통·수정 기록을 남깁니다.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from core import db

T = "cs"
KINDS = ["문의·상담", "방문", "기술지원", "요청·불만", "교육·견학"]
STATUSES = ["접수", "진행 중", "완료"]
# 유형 색 (글자색, 바탕색) — 달력 사용목적 색과 어울리는 파스텔
KIND_COLOR = {
    "문의·상담": ("#2E9BD6", "#E6F3FB"), "방문": ("#1E8E5A", "#E5F4EC"), "기술지원": ("#8E6CC0", "#F1ECF8"),
    "요청·불만": ("#D45087", "#FBEAF1"), "교육·견학": ("#E39A2D", "#FDF2E2"),
}
STATUS_COLOR = {"접수": ("#B5650B", "#FDF1E2"), "진행 중": ("#5B6CFF", "#EEF0FF"), "완료": ("#1E8E5A", "#E5F4EC")}
FIELDS = ("date", "kind", "title", "company", "contact", "staff", "equip_ids", "content", "action", "status",
          "follow_up")


def _ids(v) -> list[int]:
    out = []
    for x in str(v or "").replace(";", ",").split(","):
        n = db.to_num(x.strip())
        if n is not None:
            out.append(int(n))
    return out


@st.cache_data(ttl=120, show_spinner=False)
def load() -> pd.DataFrame:
    df = db._tab(T)
    df = df[df["id"].astype(str).str.strip() != ""].copy()
    for c in db.cols(T):
        if c not in ("date", "follow_up"):
            df[c] = df[c].map(db.to_str)
    df["date"] = pd.to_datetime(df["date"].map(db.to_date), errors="coerce")
    df["follow_up"] = pd.to_datetime(df["follow_up"].map(db.to_date), errors="coerce")
    df["equip_list"] = df["equip_ids"].map(_ids)
    names = dict(zip(db.load_equipment(full=True)["id"].astype(int), db.load_equipment(full=True)["name"]))
    df["equip_ref"] = [", ".join(names[i] for i in ids if i in names) or ref
                       for ids, ref in zip(df["equip_list"], df["equip_ref"])]  # 장비 이름을 바꿔도 바로 반영
    df["status"] = df["status"].where(df["status"].isin(STATUSES), "접수")
    return df.sort_values(["date", "created_at"], ascending=False, na_position="last").reset_index(drop=True)


def summary(r: dict) -> str:
    return db._master_summary(T, r)


def _clean(rec: dict) -> dict:
    out = {}
    for k in FIELDS:
        if k not in rec:
            continue
        v = rec[k]
        if k in ("date", "follow_up"):
            out[k] = db.to_date(v)
        elif k == "equip_ids":
            ids = v if isinstance(v, (list, tuple)) else _ids(v)
            out[k] = ",".join(str(int(i)) for i in ids)
        else:
            out[k] = db.to_str(v)
    if "kind" in out and out["kind"] not in KINDS:
        out["kind"] = out["kind"] or KINDS[0]
    if "status" in out and out["status"] not in STATUSES:
        out["status"] = "접수"
    if "equip_ids" in out:
        names = db._equip_names()
        out["equip_ref"] = ", ".join(names.get(i, "") for i in _ids(out["equip_ids"]) if names.get(i))
    return out


def check(rec: dict) -> list[str]:
    errs = []
    if not db.to_date(rec.get("date")):
        errs.append("활동일을 넣어 주세요.")
    if not (db.to_str(rec.get("title")) or db.to_str(rec.get("content"))):
        errs.append("제목이나 내용 중 하나는 적어 주세요.")
    return errs


def insert(records: list[dict]) -> list[str]:
    if not records:
        return []
    now = db._now()
    rows = []
    for rid, r in zip(db._new_ids(len(records)), records):
        row = _clean(r)
        row.update(id=rid, created_by=db.who(), created_at=now, updated_at=now, updated_by=db.who())
        rows.append(row)
    db.get_store().append(T, db._rows(T, rows))
    ids = [str(r["id"]) for r in rows]
    db._step(("delete", T, ids), f"CS활동 {len(rows)}건 추가")
    db.log("추가", "CS활동", f"{len(rows)}건: " + " / ".join(summary(r) for r in rows[:3]))
    load.clear()
    return ids


def update(changes: dict[str, dict]) -> int:
    if not changes:
        return 0
    store = db.get_store()
    df = store.read(T)
    keys = df["id"].astype(str).str.strip()
    now = db._now()
    out, before = {}, {}
    for rid, vals in changes.items():
        hit = df[keys == str(rid)]
        if hit.empty:
            continue
        cur = hit.iloc[0].to_dict()
        before[str(rid)] = [str(cur.get(c, "")) for c in db.cols(T)]
        cur.update(_clean(vals))
        cur.update(updated_at=now, updated_by=db.who())
        out[str(rid)] = db._rows(T, [cur])[0]
    n = store.update_rows(T, out)
    if n:
        db._step(("put", T, before), f"CS활동 {n}건 수정")
        db.log("수정", "CS활동", f"{n}건: " + " / ".join(
            summary(dict(zip(db.cols(T), out[k]))) for k in list(out)[:3]))
    load.clear()
    return n


def delete(ids: list[str]) -> int:
    keys = {str(i) for i in ids}
    if not keys:
        return 0
    cur = db._raw(T)
    gone = cur[cur["id"].str.strip().isin(keys)]
    trash_ids = db._to_trash(T, gone.to_dict("records"))
    n = db.get_store().delete_ids(T, list(keys))
    if n:
        db._step(("readd", T, gone.values.tolist(), trash_ids), f"CS활동 {n}건 삭제")
        db.log("삭제", "CS활동", f"{n}건: " + " / ".join(summary(r) for r in gone.to_dict("records")[:3]))
    load.clear()
    return n


def stats(df: pd.DataFrame, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    month = df[(df["date"].dt.year == today.year) & (df["date"].dt.month == today.month)]
    wk_s = pd.Timestamp(today - dt.timedelta(days=today.weekday()))
    wk_e = wk_s + pd.Timedelta(days=6)
    open_ = df[df["status"] != "완료"]
    return {
        "month": len(month),
        "year": int((df["date"].dt.year == today.year).sum()),
        "open": len(open_),
        "follow": int(((open_["follow_up"] >= wk_s) & (open_["follow_up"] <= wk_e)).sum()),
        "overdue": int((open_["follow_up"] < pd.Timestamp(today)).sum()),
        "companies": int(month.loc[month["company"] != "", "company"].nunique()),
    }


def to_excel(df: pd.DataFrame) -> bytes:
    import io
    view = pd.DataFrame({
        "활동일": df["date"].dt.date, "제목": df["title"], "업체": df["company"],
        "업체 담당자": df["contact"], "TP담당자": df["staff"], "관련 장비": df["equip_ref"],
        "내용": df["content"],
    })
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        view.to_excel(xw, sheet_name="CS활동", index=False)
        ws = xw.sheets["CS활동"]
        for col, wdt in zip("ABCDEFGHIJK", (12, 11, 30, 22, 14, 11, 24, 50, 40, 9, 12)):
            ws.column_dimensions[col].width = wdt
        ws.freeze_panes = "A2"
    return bio.getvalue()
