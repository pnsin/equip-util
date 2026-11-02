"""데이터 저장소.

secrets 에 [gsheets] spreadsheet_id 와 [gcp_service_account] 가 있으면 구글 시트에 저장하고,
없으면 data/ 폴더의 CSV 파일에 저장합니다 (내 PC에서 시험할 때).

구글 시트 구조: 탭 3개 (장비 / 사용실적 / 설정). 1행 열 제목은 바꾸거나 옮기면 안 됩니다.
사용실적 탭의 '장비명(참고)' 열은 사람이 보기 위한 사본이며 프로그램은 읽지 않습니다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import time

import pandas as pd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 테이블: (탭 이름, [(내부 키, 시트 열 제목)])
TABLES = {
    "equipment": ("장비", [
        ("id", "ID"), ("name", "장비명"), ("code", "장비번호"), ("kind", "장비구분"),
        ("annual_hours", "연간기준시간"), ("acquired_on", "도입일"), ("retired_on", "불용일"),
        ("in_kpi", "가동률산정"), ("manager", "담당자"), ("note", "비고"),
    ]),
    "usage": ("사용실적", [
        ("id", "ID"), ("equip_id", "장비ID"), ("equip_ref", "장비명(참고)"),
        ("purpose", "사용목적"), ("usage_type", "활용유형"), ("company", "사용기관 기업명"),
        ("brn", "사업자등록번호"), ("dept", "내부부서명"), ("industry", "업종"), ("item", "품목"),
        ("sub_item", "세부품목"), ("product", "제품명"), ("samples", "시료수"), ("disclose", "세부지원공개여부"),
        ("detail", "세부지원내용"), ("start_date", "사용시작일"), ("end_date", "사용종료일"),
        ("include_holidays", "휴무일자포함"), ("hours", "사용시간"), ("fee", "사용료"),
        ("purpose_detail", "사용목적(상세)"), ("etc", "기타"), ("created_by", "작성자"),
        ("created_at", "작성일시"), ("updated_at", "수정일시"),
    ]),
    "settings": ("설정", [("key", "항목"), ("value", "값")]),
}

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

CHUNK = 40000  # 구글 시트 셀 한도(50,000자)보다 작게 나눠 저장
LOG_FIELDS = [k for k, _ in TABLES["usage"][1] if k not in ("id", "equip_ref", "created_at", "updated_at")]


class StorageError(Exception):
    pass


def cols(t: str) -> list[str]:
    return [k for k, _ in TABLES[t][1]]


def heads(t: str) -> list[str]:
    return [h for _, h in TABLES[t][1]]


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
        return float(str(v).replace(",", "")) if isinstance(v, str) else float(v)
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


def _cell(v):
    """시트에 쓸 값. 날짜는 'YYYY-MM-DD' 글자로, 빈 값은 ''."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Y" if v else "N"
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        if pd.isna(v):
            return ""
        return v.strftime("%Y-%m-%d %H:%M:%S") if (v.hour or v.minute or v.second) else v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):  # numpy 숫자
        v = v.item()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _rows(t: str, records: list[dict]) -> list[list]:
    return [[_cell(r.get(c)) for c in cols(t)] for r in records]


# ── 저장소 (구글 시트 / CSV) ─────────────────────────────────────

def explain_error(e: Exception) -> str:
    code = getattr(getattr(e, "response", None), "status_code", None)
    text = str(e)
    if type(e).__name__ == "SpreadsheetNotFound" or code == 404:
        return ("스프레드시트를 찾을 수 없습니다. secrets의 spreadsheet_id를 확인하고, "
                "서비스 계정 이메일을 시트에 '편집자'로 공유했는지 확인하세요.")
    if code == 403 and ("has not been used" in text or "SERVICE_DISABLED" in text):
        return "Google Sheets API가 사용 설정되지 않았습니다. 구글 클라우드 콘솔에서 Google Sheets API를 사용 설정하세요."
    if code == 403:
        return "시트 접근 권한이 없습니다. 서비스 계정 이메일을 시트에 '편집자'로 공유했는지 확인하세요."
    if code == 429:
        return "구글 시트 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요."
    if isinstance(e, (ValueError, KeyError)):
        return f"서비스 계정 인증 정보 형식이 올바르지 않습니다 ({type(e).__name__}). secrets의 [gcp_service_account]를 확인하세요."
    return f"구글 시트에 연결하지 못했습니다 ({type(e).__name__}). 네트워크와 인증 설정을 확인하세요."


def _call(fn, *args, **kw):
    """구글 API 호출. 한도·서버 오류는 최대 5회 재시도."""
    delay = 1.5
    for attempt in range(5):
        try:
            return fn(*args, **kw)
        except Exception as e:  # noqa: BLE001
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise StorageError(explain_error(e)) from e


class SheetStore:
    label = "구글 시트"
    persistent = True

    def __init__(self, service_account_info: dict, spreadsheet_id: str):
        try:
            import gspread
            client = gspread.service_account_from_dict(
                dict(service_account_info), scopes=["https://www.googleapis.com/auth/spreadsheets"])
            self.ss = client.open_by_key(spreadsheet_id)
        except Exception as e:  # noqa: BLE001
            raise StorageError(explain_error(e)) from e
        existing = {w.title: w for w in _call(self.ss.worksheets)}
        self.ws = {}
        for t, (title, _) in TABLES.items():
            head = heads(t)
            ws = existing.get(title)
            if ws is None:
                ws = _call(self.ss.add_worksheet, title=title, rows=500, cols=len(head))
                _call(ws.update, values=[head], range_name="A1", value_input_option="RAW")
                try:
                    ws.freeze(rows=1)
                except Exception:  # noqa: BLE001 - 고정은 필수가 아님
                    pass
            else:
                first = [str(c).strip() for c in _call(ws.row_values, 1)]
                if not first:
                    _call(ws.update, values=[head], range_name="A1", value_input_option="RAW")
                elif first[:len(head)] != head:
                    raise StorageError(f"구글 시트 '{title}' 탭의 1행 열 제목이 프로그램 기준과 다릅니다. "
                                       f"열 제목을 고치거나 열을 옮기지 마세요. (기대: {', '.join(head[:4])} …)")
            self.ws[t] = ws

    def read(self, t: str) -> pd.DataFrame:
        n = len(cols(t))
        values = _call(self.ws[t].get_all_values)
        rows = [(list(r) + [""] * n)[:n] for r in values[1:] if any(str(c).strip() for c in r)]
        return pd.DataFrame(rows, columns=cols(t))

    def append(self, t: str, rows: list[list]) -> None:
        if rows:
            _call(self.ws[t].append_rows, rows, value_input_option="RAW", table_range="A1")

    def rewrite(self, t: str, rows: list[list]) -> None:
        ws = self.ws[t]
        n = len(cols(t))
        old = len(_call(ws.col_values, 1))
        values = [heads(t)] + rows
        values += [[""] * n for _ in range(max(0, old - len(values)))]  # 줄어든 만큼 아래 행 비우기
        if ws.row_count < len(values):
            _call(ws.add_rows, len(values) - ws.row_count)
        _call(ws.update, values=values, range_name="A1", value_input_option="RAW")


class CsvStore:
    label = "로컬 파일 (시험용)"
    persistent = False

    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def _path(self, t: str) -> str:
        return os.path.join(self.folder, f"{t}.csv")

    def read(self, t: str) -> pd.DataFrame:
        if not os.path.exists(self._path(t)):
            return pd.DataFrame(columns=cols(t))
        df = pd.read_csv(self._path(t), dtype=str, keep_default_na=False)
        return df.reindex(columns=cols(t), fill_value="")

    def append(self, t: str, rows: list[list]) -> None:
        df = pd.concat([self.read(t), pd.DataFrame(rows, columns=cols(t)).astype(str)], ignore_index=True)
        df.to_csv(self._path(t), index=False)

    def rewrite(self, t: str, rows: list[list]) -> None:
        pd.DataFrame(rows, columns=cols(t)).to_csv(self._path(t), index=False)


def _sheet_secrets() -> tuple[dict | None, str]:
    try:
        info = st.secrets.get("gcp_service_account")
        sid = (st.secrets.get("gsheets") or {}).get("spreadsheet_id", "")
    except Exception:  # secrets.toml 이 없을 때
        return None, ""
    return (dict(info) if info else None), str(sid or "")


def get_store():
    info, sid = _sheet_secrets()
    # Secrets가 바뀌면(시트 ID·서비스 계정) 캐시 키가 달라져 새로 연결됨
    return _open_store(sid if info else "", (info or {}).get("client_email", ""))


@st.cache_resource
def _open_store(spreadsheet_id: str, client_email: str):
    info, _ = _sheet_secrets()
    if info and spreadsheet_id:
        return SheetStore(info, spreadsheet_id)
    return CsvStore(DATA_DIR)


def is_local() -> bool:
    return not get_store().persistent


def storage_label() -> str:
    return get_store().label


def clear_caches() -> None:
    load_equipment.clear()
    load_logs.clear()
    get_settings.clear()


def _new_ids(n: int) -> list[str]:
    """동시에 저장해도 겹치지 않도록 시각 기반 ID (글자로 저장)."""
    base = int(time.time() * 1000) * 1000
    return [str(base + i) for i in range(n)]


# ── 설정 ────────────────────────────────────────────────────────

def _settings_raw() -> dict[str, str]:
    df = get_store().read("settings")
    return {to_str(k): str(v) for k, v in zip(df["key"], df["value"]) if to_str(k)}


@st.cache_data(ttl=30)
def get_settings() -> dict:
    plain, chunks = {}, {}
    for k, v in _settings_raw().items():
        if "#" in k:
            base, i = k.rsplit("#", 1)
            chunks.setdefault(base, []).append((int(i) if i.isdigit() else 0, v))
        else:
            plain[k] = v
    for base, parts in chunks.items():
        plain[base] = "".join(v for _, v in sorted(parts))
    out = dict(DEFAULT_SETTINGS)
    for k, v in plain.items():
        try:
            out[k] = json.loads(v)
        except (TypeError, ValueError):
            pass
    return out


def save_settings(**kv) -> None:
    raw = _settings_raw()
    for k, v in kv.items():
        raw = {rk: rv for rk, rv in raw.items() if rk != k and not rk.startswith(k + "#")}
        s = json.dumps(v, ensure_ascii=False)
        if len(s) > CHUNK:
            for i in range(0, len(s), CHUNK):
                raw[f"{k}#{i // CHUNK}"] = s[i:i + CHUNK]
        else:
            raw[k] = s
    get_store().rewrite("settings", [[k, v] for k, v in raw.items()])
    get_settings.clear()


# ── 장비 ────────────────────────────────────────────────────────

def _equipment_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    df["annual_hours"] = pd.to_numeric(df["annual_hours"].astype(str).str.replace(",", ""), errors="coerce")
    for c in ("acquired_on", "retired_on"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["in_kpi"] = df["in_kpi"].map(lambda v: str(v).strip().upper() not in ("N", "FALSE", "0", "아니오"))
    for c in ("name", "code", "kind", "manager", "note"):
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["kind"] = df["kind"].replace("", "주장비")
    return df.sort_values(["name", "code"]).reset_index(drop=True)


@st.cache_data(ttl=30)
def load_equipment() -> pd.DataFrame:
    df = _equipment_frame(get_store().read("equipment"))
    labels = [f"{n} ({c})" if c else n for n, c in zip(df["name"], df["code"])]
    seen: dict[str, int] = {}
    for lb in labels:
        seen[lb] = seen.get(lb, 0) + 1
    df["label"] = [f"{lb} #{i}" if seen[lb] > 1 else lb for lb, i in zip(labels, df["id"])]
    return df


def _equip_record(r: dict) -> dict:
    in_kpi = r.get("in_kpi")
    return {
        "name": to_str(r.get("name")),
        "code": to_str(r.get("code")),
        "kind": to_str(r.get("kind")) or "주장비",
        "annual_hours": to_num(r.get("annual_hours")),
        "acquired_on": to_date(r.get("acquired_on")),
        "retired_on": to_date(r.get("retired_on")),
        "in_kpi": True if in_kpi is None or (isinstance(in_kpi, float) and pd.isna(in_kpi)) else bool(in_kpi),
        "manager": to_str(r.get("manager")),
        "note": to_str(r.get("note")),
    }


def save_equipment(edited: pd.DataFrame) -> list[str]:
    """장비 표 편집 결과를 반영합니다. 실적이 있는 장비는 삭제하지 않고 오류로 돌려줍니다."""
    store = get_store()
    current = _equipment_frame(store.read("equipment"))
    orig = {int(r["id"]): r for r in current.to_dict("records")}
    used_ids = set(pd.to_numeric(store.read("usage")["equip_id"], errors="coerce").dropna().astype(int))
    errors: list[str] = []
    out, keep = [], set()
    next_id = (max(orig) if orig else 0) + 1
    for r in edited.to_dict("records"):
        rec = _equip_record(r)
        if not rec["name"]:
            continue
        rid = to_num(r.get("id"))
        if rid is not None and int(rid) in orig:
            rec["id"] = int(rid)
            keep.add(int(rid))
        else:
            rec["id"] = next_id
            next_id += 1
        out.append(rec)
    for gone in set(orig) - keep:
        if gone in used_ids:
            errors.append(f"'{orig[gone]['name']}'은(는) 사용실적이 있어 삭제하지 않았습니다. 불용일을 입력해 주세요.")
            out.append(_equip_record(orig[gone]) | {"id": gone})
    store.rewrite("equipment", _rows("equipment", out))
    clear_caches()
    return errors


# ── 사용실적 ────────────────────────────────────────────────────

def _usage_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("id", "equip_id"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    df["equip_id"] = df["equip_id"].fillna(0).astype("int64")
    for c in ("hours", "fee", "samples"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    for c in ("start_date", "end_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


@st.cache_data(ttl=30)
def load_logs() -> pd.DataFrame:
    df = _usage_frame(get_store().read("usage")).drop(columns=["equip_ref"])
    eq = load_equipment()[["id", "name", "code", "kind"]].rename(columns={
        "id": "_eid", "name": "equip_name", "code": "equip_code", "kind": "equip_kind"})
    df = df.merge(eq, left_on="equip_id", right_on="_eid", how="left").drop(columns=["_eid"])
    for c in ("equip_name", "equip_code", "equip_kind"):
        df[c] = df[c].fillna("")
    return df.sort_values(["start_date", "id"], ascending=False).reset_index(drop=True)


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


def _equip_names() -> dict[int, str]:
    eq = load_equipment()
    return dict(zip(eq["id"].astype(int), eq["label"]))


def insert_logs(records: list[dict], user: str = "") -> int:
    if not records:
        return 0
    now = dt.datetime.now().replace(microsecond=0)
    names = _equip_names()
    rows = []
    for rid, r in zip(_new_ids(len(records)), records):
        row = _clean_log(r)
        row.setdefault("created_by", user)
        row.update(id=rid, equip_ref=names.get(row.get("equip_id"), ""), created_at=now, updated_at=now)
        rows.append(row)
    get_store().append("usage", _rows("usage", rows))
    load_logs.clear()
    return len(rows)


def _rewrite_usage(df: pd.DataFrame) -> None:
    get_store().rewrite("usage", _rows("usage", df.to_dict("records")))
    load_logs.clear()


def update_logs(changes: dict[int, dict]) -> int:
    store = get_store()
    df = store.read("usage")
    names = _equip_names()
    now = dt.datetime.now().replace(microsecond=0)
    ids = pd.to_numeric(df["id"], errors="coerce")
    for log_id, vals in changes.items():
        mask = ids == int(log_id)
        row = _clean_log(vals)
        row["updated_at"] = now
        if "equip_id" in row:
            row["equip_ref"] = names.get(row["equip_id"], "")
        for k, v in row.items():
            df.loc[mask, k] = _cell(v)
    _rewrite_usage(df)
    return len(changes)


def delete_logs(ids: list[int]) -> int:
    if not ids:
        return 0
    df = get_store().read("usage")
    keep = ~pd.to_numeric(df["id"], errors="coerce").isin([int(i) for i in ids])
    _rewrite_usage(df[keep])
    return len(ids)


def import_parsed(rows: list[dict], equip_master: list[tuple[str, str]], user: str) -> dict:
    """i-Tube 양식에서 읽은 행을 등록합니다. 없는 장비는 새로 만들고, 이미 있는 실적은 건너뜁니다."""
    store = get_store()
    eq = [dict(r) for r in _equipment_frame(store.read("equipment")).to_dict("records")]
    by_code = {r["code"]: r for r in eq if r["code"]}
    by_name: dict[str, dict] = {}
    for r in eq:
        by_name.setdefault(r["name"], r)
    next_id = max((int(r["id"]) for r in eq), default=0) + 1
    created, changed = 0, False

    def ensure(name: str, code: str, kind: str = "") -> int | None:
        nonlocal next_id, created, changed
        if code and code in by_code:
            return int(by_code[code]["id"])
        if name in by_name:
            r = by_name[name]
            if code and not r["code"]:  # 장비번호가 비어 있던 장비면 양식의 번호를 채움
                r["code"] = code
                by_code[code] = r
                changed = True
                return int(r["id"])
            if not code or r["code"] == code:
                return int(r["id"])
        if not name:
            return None
        r = {"id": next_id, "name": name, "code": code, "kind": kind or "주장비", "annual_hours": None,
             "acquired_on": None, "retired_on": None, "in_kpi": True, "manager": "", "note": ""}
        next_id += 1
        eq.append(r)
        by_name.setdefault(name, r)
        if code:
            by_code[code] = r
        created += 1
        changed = True
        return int(r["id"])

    for name, code in equip_master:
        ensure(name, code)
    prepared = []
    for r in rows:
        eid = ensure(r.get("equip_name", ""), r.get("equip_code", ""), r.get("equip_kind", ""))
        if eid is not None:
            prepared.append(dict(r, equip_id=eid))
    if changed:
        store.rewrite("equipment", _rows("equipment", eq))
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
    store = get_store()
    st_df = store.read("settings")
    st_df = st_df[~st_df["key"].astype(str).str.startswith("template_b64")]
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        store.read("equipment").to_excel(xw, sheet_name="equipment", index=False)
        store.read("usage").to_excel(xw, sheet_name="usage_log", index=False)
        st_df.to_excel(xw, sheet_name="settings", index=False)
    return bio.getvalue()


def restore_bytes(data: bytes) -> dict:
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
    eq = sheets["equipment"].reindex(columns=cols("equipment")).fillna("")
    lg = sheets["usage_log"].reindex(columns=cols("usage")).fillna("")
    store = get_store()
    store.rewrite("equipment", eq.values.tolist())
    store.rewrite("usage", lg.values.tolist())
    if "settings" in sheets:
        keep = {k: v for k, v in _settings_raw().items() if k.startswith("template_b64")}
        st_df = sheets["settings"].reindex(columns=["key", "value"]).fillna("")
        rows = [[k, v] for k, v in st_df.values.tolist() if k and not k.startswith("template_b64")]
        store.rewrite("settings", rows + [[k, v] for k, v in keep.items()])
    clear_caches()
    return {"equipment": len(eq), "usage_log": len(lg)}
