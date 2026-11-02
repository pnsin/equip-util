"""데이터 저장소.

secrets.toml 에 db_url(PostgreSQL, 예: Supabase)이 있으면 그 DB를 쓰고,
없으면 data/equip.db (SQLite) 파일을 씁니다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os

import pandas as pd
import sqlalchemy as sa
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

metadata = sa.MetaData()

equipment = sa.Table(
    "equipment", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("code", sa.String(50), default=""),
    sa.Column("kind", sa.String(20), default="주장비"),
    sa.Column("annual_hours", sa.Float, nullable=True),  # 비어 있으면 설정의 기본값 사용
    sa.Column("acquired_on", sa.Date, nullable=True),
    sa.Column("retired_on", sa.Date, nullable=True),
    sa.Column("in_kpi", sa.Boolean, default=True),
    sa.Column("manager", sa.String(50), default=""),
    sa.Column("note", sa.String(500), default=""),
)

usage = sa.Table(
    "usage_log", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("equip_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
    sa.Column("purpose", sa.String(20)),
    sa.Column("usage_type", sa.String(20)),
    sa.Column("company", sa.String(200), default=""),
    sa.Column("brn", sa.String(20), default=""),
    sa.Column("dept", sa.String(100), default=""),
    sa.Column("industry", sa.String(50), default=""),
    sa.Column("item", sa.String(50), default=""),
    sa.Column("sub_item", sa.String(50), default=""),
    sa.Column("product", sa.String(200), default=""),
    sa.Column("samples", sa.Integer, default=1),
    sa.Column("disclose", sa.String(1), default="N"),
    sa.Column("detail", sa.Text, default=""),
    sa.Column("start_date", sa.Date, nullable=False),
    sa.Column("end_date", sa.Date, nullable=False),
    sa.Column("include_holidays", sa.String(1), default="Y"),
    sa.Column("hours", sa.Integer, nullable=False),
    sa.Column("fee", sa.BigInteger, default=0),
    sa.Column("purpose_detail", sa.String(500), default=""),
    sa.Column("etc", sa.String(500), default=""),
    sa.Column("created_by", sa.String(50), default=""),
    sa.Column("created_at", sa.DateTime),
    sa.Column("updated_at", sa.DateTime),
)

settings_t = sa.Table(
    "settings", metadata,
    sa.Column("key", sa.String(100), primary_key=True),
    sa.Column("value", sa.Text),
)

DEFAULT_SETTINGS = {
    "org_name": "차세대에너지센터 차세대전지팀",
    "org_suffix": "배터리연구지원센터",
    "dept_default": "차세대에너지센터",
    "annual_hours": 2000,
    "target_util": 60.0,
    "alloc_mode": "spread",  # spread: 기간에 고르게 배분 / start: 시작일에 전부 반영
    "members": [],
    "template_b64": "",
}

LOG_FIELDS = [c.name for c in usage.columns if c.name not in ("id", "created_at", "updated_at")]


def _db_url() -> str:
    try:
        url = st.secrets.get("db_url", "")
    except Exception:  # secrets.toml 이 없을 때
        url = ""
    url = str(url or "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def is_local() -> bool:
    return not _db_url()


@st.cache_resource
def get_engine() -> sa.Engine:
    url = _db_url()
    if not url:
        os.makedirs(DATA_DIR, exist_ok=True)
        url = "sqlite:///" + os.path.join(DATA_DIR, "equip.db")
    engine = sa.create_engine(url, pool_pre_ping=True)
    metadata.create_all(engine)
    return engine


def clear_caches() -> None:
    load_equipment.clear()
    load_logs.clear()
    get_settings.clear()


# ── 값 정리 도우미 ──────────────────────────────────────────────

def to_date(v) -> dt.date | None:
    if v is None or v == "":
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return pd.Timestamp(v).date()
    except Exception:
        return None


def to_num(v, default=None):
    if v is None or v == "":
        return default
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_str(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def digits(v) -> str:
    return "".join(ch for ch in to_str(v) if ch.isdigit())


# ── 설정 ────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_settings() -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(sa.select(settings_t.c.key, settings_t.c.value)).all()
    out = dict(DEFAULT_SETTINGS)
    for k, v in rows:
        try:
            out[k] = json.loads(v)
        except (TypeError, ValueError):
            pass
    return out


def save_settings(**kv) -> None:
    with get_engine().begin() as conn:
        for k, v in kv.items():
            conn.execute(settings_t.delete().where(settings_t.c.key == k))
            conn.execute(settings_t.insert().values(key=k, value=json.dumps(v, ensure_ascii=False)))
    get_settings.clear()


# ── 장비 ────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_equipment() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(sa.select(equipment).order_by(equipment.c.name, equipment.c.code), conn)
    for c in ("acquired_on", "retired_on"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["code"] = df["code"].fillna("")
    df["kind"] = df["kind"].fillna("주장비")
    df["manager"] = df["manager"].fillna("")
    df["note"] = df["note"].fillna("")
    df["in_kpi"] = df["in_kpi"].map(lambda v: True if v is None or pd.isna(v) else bool(v))
    labels = [f"{n} ({c})" if c else n for n, c in zip(df["name"], df["code"])]
    seen: dict[str, int] = {}
    for lb in labels:
        seen[lb] = seen.get(lb, 0) + 1
    df["label"] = [f"{lb} #{i}" if seen[lb] > 1 else lb for lb, i in zip(labels, df["id"])]
    return df


def save_equipment(edited: pd.DataFrame) -> list[str]:
    """장비 표 편집 결과를 반영합니다. 실적이 있는 장비는 삭제하지 않고 오류로 돌려줍니다."""
    current = load_equipment()
    orig_ids = set(int(i) for i in current["id"])
    with get_engine().connect() as conn:
        used_ids = {r[0] for r in conn.execute(sa.select(usage.c.equip_id).distinct())}
    errors: list[str] = []
    keep: set[int] = set()
    with get_engine().begin() as conn:
        for r in edited.to_dict("records"):
            name = to_str(r.get("name"))
            if not name:
                continue
            in_kpi = r.get("in_kpi")
            vals = {
                "name": name,
                "code": to_str(r.get("code")),
                "kind": to_str(r.get("kind")) or "주장비",
                "annual_hours": to_num(r.get("annual_hours")),
                "acquired_on": to_date(r.get("acquired_on")),
                "retired_on": to_date(r.get("retired_on")),
                "in_kpi": True if in_kpi is None or (isinstance(in_kpi, float) and pd.isna(in_kpi)) else bool(in_kpi),
                "manager": to_str(r.get("manager")),
                "note": to_str(r.get("note")),
            }
            rid = to_num(r.get("id"))
            if rid is not None and int(rid) in orig_ids:
                conn.execute(equipment.update().where(equipment.c.id == int(rid)).values(**vals))
                keep.add(int(rid))
            else:
                conn.execute(equipment.insert().values(**vals))
        for gone in orig_ids - keep:
            if gone in used_ids:
                name = current.loc[current["id"] == gone, "label"].iloc[0]
                errors.append(f"'{name}'은(는) 사용실적이 있어 삭제하지 않았습니다. 불용일을 입력해 주세요.")
            else:
                conn.execute(equipment.delete().where(equipment.c.id == gone))
    clear_caches()
    return errors


# ── 사용실적 ────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_logs() -> pd.DataFrame:
    q = (
        sa.select(
            usage,
            equipment.c.name.label("equip_name"),
            equipment.c.code.label("equip_code"),
            equipment.c.kind.label("equip_kind"),
        )
        .select_from(usage.outerjoin(equipment, usage.c.equip_id == equipment.c.id))
        .order_by(usage.c.start_date.desc(), usage.c.id.desc())
    )
    with get_engine().connect() as conn:
        df = pd.read_sql(q, conn)
    for c in ("start_date", "end_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in ("hours", "fee", "samples"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    text_cols = [c for c in df.columns if df[c].dtype == object and c not in ("created_at", "updated_at")]
    df[text_cols] = df[text_cols].fillna("")
    return df


def _clean_log(rec: dict) -> dict:
    out = {k: rec.get(k) for k in LOG_FIELDS if k in rec}
    for k in ("start_date", "end_date"):
        if k in out:
            out[k] = to_date(out[k])
    for k in ("hours", "fee", "samples", "equip_id"):
        if k in out:
            out[k] = int(round(to_num(out[k], 0)))
    if "brn" in out:
        out["brn"] = digits(out["brn"])
    for k in ("purpose", "usage_type", "company", "dept", "industry", "item", "sub_item", "product",
              "disclose", "detail", "include_holidays", "purpose_detail", "etc", "created_by"):
        if k in out:
            out[k] = to_str(out[k])
    return out


def insert_logs(records: list[dict], user: str = "") -> int:
    now = dt.datetime.now()
    rows = []
    for r in records:
        row = _clean_log(r)
        row.setdefault("created_by", user)
        row["created_at"] = now
        row["updated_at"] = now
        rows.append(row)
    if rows:
        with get_engine().begin() as conn:
            conn.execute(usage.insert(), rows)
    load_logs.clear()
    return len(rows)


def update_logs(changes: dict[int, dict]) -> int:
    now = dt.datetime.now()
    with get_engine().begin() as conn:
        for log_id, vals in changes.items():
            row = _clean_log(vals)
            row["updated_at"] = now
            conn.execute(usage.update().where(usage.c.id == int(log_id)).values(**row))
    load_logs.clear()
    return len(changes)


def delete_logs(ids: list[int]) -> int:
    if not ids:
        return 0
    with get_engine().begin() as conn:
        conn.execute(usage.delete().where(usage.c.id.in_([int(i) for i in ids])))
    load_logs.clear()
    return len(ids)


def import_parsed(rows: list[dict], equip_master: list[tuple[str, str]], user: str) -> dict:
    """i-Tube 양식에서 읽은 행을 등록합니다. 없는 장비는 새로 만들고, 이미 있는 실적은 건너뜁니다."""
    eq = load_equipment()
    by_code = {c: int(i) for c, i in zip(eq["code"], eq["id"]) if c}
    by_name = {}
    for n, i in zip(eq["name"], eq["id"]):
        by_name.setdefault(n, int(i))
    code_of = {int(i): c for i, c in zip(eq["id"], eq["code"])}
    created = 0
    with get_engine().begin() as conn:
        def ensure(name: str, code: str, kind: str = "주장비") -> int | None:
            nonlocal created
            if code and code in by_code:
                return by_code[code]
            if name in by_name:
                eid = by_name[name]
                if code and not code_of.get(eid):
                    # 장비번호가 비어 있던 장비면 양식의 번호를 채워 넣음
                    conn.execute(equipment.update().where(equipment.c.id == eid).values(code=code))
                    code_of[eid] = code
                    by_code[code] = eid
                    return eid
                if not code or code_of.get(eid) == code:
                    return eid
            if not name:
                return None
            res = conn.execute(equipment.insert().values(
                name=name, code=code, kind=kind or "주장비", in_kpi=True, manager="", note=""))
            eid = int(res.inserted_primary_key[0])
            by_name.setdefault(name, eid)
            code_of[eid] = code
            if code:
                by_code[code] = eid
            created += 1
            return eid

        for name, code in equip_master:
            ensure(name, code)
        prepared = []
        for r in rows:
            eid = ensure(r.get("equip_name", ""), r.get("equip_code", ""), r.get("equip_kind", ""))
            if eid is None:
                continue
            rr = dict(r)
            rr["equip_id"] = eid
            prepared.append(rr)
    clear_caches()

    logs = load_logs()
    existing = {
        (int(e), to_date(s), to_date(f), str(c), int(h))
        for e, s, f, c, h in zip(logs["equip_id"], logs["start_date"], logs["end_date"], logs["company"], logs["hours"])
    }
    new_rows, skipped = [], 0
    for r in prepared:
        c = _clean_log(r)
        key = (c["equip_id"], c["start_date"], c["end_date"], c.get("company", ""), c["hours"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        new_rows.append(r)
    inserted = insert_logs(new_rows, user)
    return {"inserted": inserted, "skipped": skipped, "created_equipment": created}


# ── 백업 / 복원 ─────────────────────────────────────────────────

def backup_bytes() -> bytes:
    with get_engine().connect() as conn:
        eq = pd.read_sql(sa.select(equipment), conn)
        lg = pd.read_sql(sa.select(usage), conn)
        st_df = pd.read_sql(sa.select(settings_t).where(settings_t.c.key != "template_b64"), conn)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        eq.to_excel(xw, sheet_name="equipment", index=False)
        lg.to_excel(xw, sheet_name="usage_log", index=False)
        st_df.to_excel(xw, sheet_name="settings", index=False)
    return bio.getvalue()


def restore_bytes(data: bytes) -> dict:
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    eq = sheets["equipment"]
    lg = sheets["usage_log"]
    st_df = sheets.get("settings", pd.DataFrame(columns=["key", "value"]))

    def records(df: pd.DataFrame, table: sa.Table) -> list[dict]:
        cols = [c.name for c in table.columns if c.name in df.columns]
        out = []
        for r in df[cols].to_dict("records"):
            row = {}
            for c in cols:
                v = r[c]
                col_type = table.c[c].type
                if isinstance(col_type, sa.Date):
                    v = to_date(v)
                elif isinstance(col_type, sa.DateTime):
                    v = pd.Timestamp(v).to_pydatetime() if to_date(v) else None
                elif isinstance(col_type, sa.Boolean):
                    v = True if to_num(v) is None else bool(to_num(v))
                elif isinstance(col_type, (sa.Integer, sa.BigInteger)):
                    n = to_num(v)
                    v = None if n is None else int(n)
                elif isinstance(col_type, sa.Float):
                    v = to_num(v)
                else:
                    v = to_str(v)
                row[c] = v
            out.append(row)
        return out

    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(usage.delete())
        conn.execute(equipment.delete())
        conn.execute(settings_t.delete().where(settings_t.c.key != "template_b64"))
        eq_rows = records(eq, equipment)
        lg_rows = records(lg, usage)
        if eq_rows:
            conn.execute(equipment.insert(), eq_rows)
        if lg_rows:
            conn.execute(usage.insert(), lg_rows)
        st_rows = [{"key": to_str(k), "value": to_str(v)} for k, v in zip(st_df["key"], st_df["value"]) if to_str(k)]
        if st_rows:
            conn.execute(settings_t.insert(), st_rows)
        if eng.dialect.name == "postgresql":
            for t in ("equipment", "usage_log"):
                conn.execute(sa.text(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"))
    clear_caches()
    return {"equipment": len(eq_rows), "usage_log": len(lg_rows)}
