"""데이터 저장소.

secrets 에 [gsheets] spreadsheet_id 와 [gcp_service_account] 가 있으면 구글 시트에 저장하고,
없으면 data/ 폴더의 CSV 파일에 저장합니다 (내 PC에서 시험할 때).

구글 시트 구조: 탭 5개 (장비 / 업체 / 담당자 / 사용실적 / 설정). 없는 탭은 처음 연결할 때 자동으로 만듭니다. 1행 열 제목은 바꾸거나 옮기면 안 됩니다.
사용실적 탭의 '장비명(참고)' 열은 사람이 보기 위한 사본이며 프로그램은 읽지 않습니다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import threading
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
        # 아래는 2026-11 추가 (장비 현황 엑셀 항목). 새 열은 항상 맨 뒤에만 덧붙임
        ("nfec", "국가연구시설장비번호"), ("model", "모델명"), ("location", "장비위치"), ("use", "장비용도"),
        # 2026-11-04 장비 분류 (장비 리스트 엑셀 '내부기준' 탭). 상위장비ID 로 장비 › 세부장비 › 세세부를 잇습니다.
        ("parent_id", "상위장비ID"), ("group", "대분류"), ("species", "주장비(종)"), ("category", "구분"),
        ("asset_no", "자산번호"), ("qty", "대수"), ("maker", "제조사"), ("vendor", "구매처"),
        ("system", "시스템 구성"), ("order", "순서"),
    ]),
    "companies": ("업체", [
        ("id", "ID"), ("name", "기업명"), ("brn", "사업자등록번호"), ("contact", "담당자"),
        ("phone", "연락처"), ("industry", "업종"), ("item", "품목"), ("sub_item", "세부품목"), ("note", "비고"),
    ]),
    "staff": ("담당자", [
        ("id", "ID"), ("name", "이름"), ("phone", "연락처"), ("email", "이메일"), ("role", "담당업무"),
        ("active", "재직"), ("note", "비고"),
        # 2026-11-04 팀원 명단(부서·팀·파트) 추가. 새 열은 항상 맨 뒤에만 덧붙임
        # 화면에서는 '파트' 대신 '담당업무'(role)를 쓰고 '재직'은 숨김 (모두 재직으로 저장). 열은 시트 호환 때문에 남겨 둠
        ("dept", "부서"), ("team", "팀"), ("part", "파트"),
        ("title", "직급"), ("birthday", "생일"),  # 2026-11-05 추가
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
        # 2026-11 추가. 새 열은 항상 맨 뒤에만 덧붙임
        ("updated_by", "수정자"),
        # 2026-11-04 충방전기 챔버 (챔버구성 탭 ID, 쉼표로 여러 개) · 채널 일부만 쓸 때 (예: 1-8)
        ("chambers", "챔버ID"), ("ch_part", "채널(일부)"),
        # 몇 달짜리 기간 실적은 i-Tube 규칙(같은 해 · 2개월 이내) 때문에 달마다 한 줄씩 나눠 저장하고 같은 묶음ID로 이음
        ("series", "묶음ID"),
        # 2026-11-05 수수료를 나눠·늦게 받을 때 받은 내역 (JSON: [{"date","amount","memo"}]). 사용료 = 합계
        ("fee_log", "수수료 받은 내역"),
    ]),
    # 충방전기 챔버 구성 (건물 › 장비명 › 싸이클러 › 챔버 › 채널). 예전 '충방전기 장비사용 현황표' 엑셀과 같은 모양
    "channels": ("챔버구성", [
        ("id", "ID"), ("equip_id", "장비ID"), ("center", "건물"), ("unit", "장비명"), ("cycler", "싸이클러"),
        ("chamber", "챔버"), ("channels", "채널 no."), ("ch_count", "채널수"), ("order", "순서"),
    ]),
    # 2026-11-04 견적서: 장비 단가 (시간당). 장비ID 가 비어 있으면 장비 목록에 없는 시험·기타 항목 (클린룸, 시험 종류별 단가 등)
    "rates": ("장비단가", [
        ("id", "ID"), ("equip_id", "장비ID"), ("name", "견적서 장비명"), ("spec", "용량"), ("unit", "단위"),
        ("price_req", "의뢰 단가"), ("price_self", "직접 단가"), ("note", "비고"), ("order", "순서"),
    ]),
    # 발급한 견적서 (발급대장 한 줄 = 한 행). data = 견적서 내용 전체(JSON) — 다시 열거나 PDF 를 다시 만들 때 씀
    "quotes": ("견적서", [
        ("id", "ID"), ("seq", "No."), ("no", "견적번호"), ("issued_on", "발급일자"), ("company", "업체명"),
        ("equip_text", "기기명"), ("model", "모델명"), ("requester", "의뢰자"), ("region", "광역/도"),
        ("amount", "계(VAT별도)"), ("amount_vat", "계(부가세 포함)"), ("status", "진행여부"), ("writer", "발행자"),
        ("note", "비고"), ("form", "양식"), ("title", "제목"), ("data", "내용"), ("created_at", "작성일시"),
        ("updated_at", "수정일시"),
    ]),
    # 2026-11-04 장비 정보 › 유지보수: 언제 · 누가 · 어떤 장비에 · 어떤 유지보수를 했는지 (단순 기록)
    "maint": ("유지보수", [
        ("id", "ID"), ("date", "날짜"), ("equip_id", "장비ID"), ("equip_ref", "장비명(참고)"),
        ("kind", "종류"), ("content", "내용"), ("staff", "담당자"), ("note", "비고"),
        ("cost", "비용(원)"),  # 2026-11-05 추가
    ]),
    # 2026-11-04 CS활동 (업체 대상 문의·방문·기술지원 등). 관련 장비는 장비ID를 쉼표로 이어 저장
    "cs": ("CS활동", [
        ("id", "ID"), ("date", "활동일"), ("kind", "유형"), ("title", "제목"), ("company", "업체"),
        ("contact", "업체 담당자"), ("staff", "우리 담당자"), ("equip_ids", "관련 장비ID"),
        ("equip_ref", "관련 장비(참고)"), ("content", "내용"), ("action", "조치·결과"), ("status", "상태"),
        ("follow_up", "후속 일정"), ("created_by", "작성자"), ("created_at", "작성일시"),
        ("updated_at", "수정일시"), ("updated_by", "수정자"),
    ]),
    # 지운 행을 보관했다가 '관리 › 휴지통 · 기록'에서 되살림 (data = 원래 행, JSON)
    "trash": ("휴지통", [
        ("id", "ID"), ("deleted_at", "지운 시각"), ("deleted_by", "지운 사람"), ("table", "종류"),
        ("summary", "내용"), ("data", "원본"),
    ]),
    # 누가 언제 무엇을 바꿨는지
    "history": ("수정기록", [
        ("at", "시각"), ("who", "누가"), ("action", "작업"), ("target", "대상"), ("summary", "내용"),
    ]),
    "settings": ("설정", [("key", "항목"), ("value", "값")]),
    # 2026-11-04 '장비 정보' 화면: 장비 한 대의 사양 · 자료(링크) · 사진 · 메모. equip_id = 장비 탭 ID
    "equip_specs": ("장비사양", [("id", "ID"), ("equip_id", "장비ID"), ("item", "항목"), ("value", "값"),
                               ("order", "순서")]),
    "equip_docs": ("장비자료", [("id", "ID"), ("equip_id", "장비ID"), ("kind", "종류"), ("title", "제목"),
                              ("url", "링크"), ("note", "메모"), ("order", "순서")]),
    # 사진은 앱에서 줄여 글자(base64 JPEG)로 저장. 셀 한도(50,000자) 안에 들게 줄임
    "equip_photos": ("장비사진", [("id", "ID"), ("equip_id", "장비ID"), ("title", "설명"), ("order", "순서"),
                                ("thumb", "작은사진"), ("photo", "사진"), ("created_at", "올린시각"),
                                ("created_by", "올린사람")]),
    # 장비마다 한 줄 (id = 장비ID)
    "equip_notes": ("장비메모", [("id", "장비ID"), ("caution", "사용 시 주의"), ("contact", "A/S 연락처"),
                               ("updated_at", "수정일시"), ("updated_by", "수정자")]),
}
INFO_TABS = ("equip_specs", "equip_docs", "equip_photos", "equip_notes")

DEFAULT_SETTINGS = {
    "org_name": "차세대에너지센터 차세대전지팀",
    "org_suffix": "배터리연구지원센터",
    "dept_default": "차세대에너지센터",
    "annual_hours": 2000,
    "target_util": 60.0,
    "alloc_mode": "spread",  # spread: 기간에 고르게 배분 / start: 시작일에 전부 반영
    "members": [],
    "template_b64": "",
    # 대시보드 보기 설정 (설정 화면에서 바꿈)
    "idle_days": 90,          # 이 날수 넘게 안 쓴 장비를 저활용·유휴 후보로
    "chart_top": 25,          # 장비별 그래프에 보여 줄 최대 대수
    "default_period": "월",   # 대시보드를 열 때 기간 단위
    "quote_next_seq": 145,    # 앱에 저장된 올해 견적서가 없을 때 쓸 다음 견적 번호 (2026 엑셀 대장이 144번까지)
}

CHUNK = 40000  # 구글 시트 셀 한도(50,000자)보다 작게 나눠 저장
LOG_FIELDS = [k for k, _ in TABLES["usage"][1] if k not in ("id", "equip_ref", "created_at", "updated_at", "updated_by")]


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
                elif len(first) < len(head) and head[:len(first)] == first:
                    # 예전 열 제목 뒤에 새 열이 생긴 경우: 열 제목만 뒤에 덧붙임 (기존 데이터는 그대로)
                    if ws.col_count < len(head):
                        _call(ws.add_cols, len(head) - ws.col_count)
                    _call(ws.update, values=[head], range_name="A1", value_input_option="RAW")
                elif first[:len(head)] != head:
                    raise StorageError(f"구글 시트 '{title}' 탭의 1행 열 제목이 프로그램 기준과 다릅니다. "
                                       f"열 제목을 고치거나 열을 옮기지 마세요. (기대: {', '.join(head[:4])} …)")
            self.ws[t] = ws

    @staticmethod
    def _frame(t: str, values: list[list]) -> pd.DataFrame:
        n = len(cols(t))
        rows = [(list(r) + [""] * n)[:n] for r in values[1:] if any(str(c).strip() for c in r)]
        return pd.DataFrame(rows, columns=cols(t))

    def read(self, t: str) -> pd.DataFrame:
        return self._frame(t, _call(self.ws[t].get_all_values))

    def read_many(self, ts: list[str]) -> dict[str, pd.DataFrame]:
        """여러 탭을 구글 API 요청 한 번으로 읽습니다 (탭마다 따로 읽으면 그만큼 기다림)."""
        ranges = ["'" + self.ws[t].title.replace("'", "''") + "'" for t in ts]
        res = _call(self.ss.values_batch_get, ranges)
        vrs = res.get("valueRanges", [])
        return {t: self._frame(t, (vrs[i].get("values", []) if i < len(vrs) else [])) for i, t in enumerate(ts)}

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

    def _row_numbers(self, t: str) -> dict[str, int]:
        """지금 시트에 있는 ID → 행 번호 (저장 직전에 다시 읽어 다른 사람이 추가한 행도 반영)."""
        ids = _call(self.ws[t].col_values, 1)
        return {str(v).strip(): i for i, v in enumerate(ids, start=1) if i > 1 and str(v).strip()}

    def update_rows(self, t: str, rows: dict[str, list]) -> int:
        """ID가 같은 행만 고칩니다. 전체를 다시 쓰지 않으므로 동시에 입력한 다른 사람의 행이 지워지지 않습니다."""
        from gspread.utils import rowcol_to_a1
        where = self._row_numbers(t)
        n = len(cols(t))
        data = [{"range": f"A{where[rid]}:{rowcol_to_a1(where[rid], n)}", "values": [row]}
                for rid, row in rows.items() if rid in where]
        if data:
            _call(self.ws[t].batch_update, data, value_input_option="RAW")
        return len(data)

    def delete_ids(self, t: str, ids: list[str]) -> int:
        where = self._row_numbers(t)
        nums = sorted({where[i] for i in ids if i in where}, reverse=True)  # 아래 행부터 지워야 번호가 안 밀림
        if nums:
            sid = self.ws[t].id
            reqs = [{"deleteDimension": {"range": {"sheetId": sid, "dimension": "ROWS",
                                                   "startIndex": r - 1, "endIndex": r}}} for r in nums]
            _call(self.ss.batch_update, {"requests": reqs})
        return len(nums)


class CsvStore:
    label = "로컬 파일 (시험용)"
    persistent = False

    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def _path(self, t: str) -> str:
        return os.path.join(self.folder, f"{t}.csv")

    def read_many(self, ts: list[str]) -> dict[str, pd.DataFrame]:
        return {t: self.read(t) for t in ts}

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

    def update_rows(self, t: str, rows: dict[str, list]) -> int:
        df = self.read(t)
        n = 0
        for rid, row in rows.items():
            mask = df["id"].astype(str).str.strip() == rid
            if mask.any():
                df.loc[mask, cols(t)] = [str(v) for v in row]
                n += 1
        self.rewrite(t, df.values.tolist())
        return n

    def delete_ids(self, t: str, ids: list[str]) -> int:
        df = self.read(t)
        mask = df["id"].astype(str).str.strip().isin(set(ids))
        self.rewrite(t, df[~mask].values.tolist())
        return int(mask.sum())


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
    # 표 구성(열 제목)도 키에 넣어, 새 열·새 탭이 생긴 코드가 배포되면 예전 연결을 버리고 새로 연결함
    schema = "|".join(f"{t}:{','.join(heads(t))}" for t in TABLES)
    key = (sid if info else "", (info or {}).get("client_email", ""), schema)
    store = _open_store(*key)
    if not isinstance(store, (SheetStore, CsvStore)) or (
            hasattr(store, "ws") and not all(t in getattr(store, "ws", {}) for t in TABLES)):
        # 새 탭(예: 업체)이 생기기 전에 연결된 저장소가 남아 있으면 다시 연결해 탭을 만듦
        _open_store.clear()
        store = _open_store(*key)
    return store


@st.cache_resource
def _open_store(spreadsheet_id: str, client_email: str, schema: str = ""):
    info, _ = _sheet_secrets()
    if info and spreadsheet_id:
        return SheetStore(info, spreadsheet_id)
    return CsvStore(DATA_DIR)


def is_local() -> bool:
    return not get_store().persistent


def storage_label() -> str:
    return get_store().label


# 화면에서 늘 쓰는 탭은 한 번에 읽어 2분 동안 기억합니다 (휴지통·수정기록은 그 화면에서만 따로 읽음)
SNAPSHOT_TABS = ("equipment", "companies", "staff", "usage", "settings", "channels", "maint")


@st.cache_data(ttl=120, show_spinner=False)
def _snapshot() -> dict[str, pd.DataFrame]:
    return get_store().read_many(list(SNAPSHOT_TABS))


def _tab(t: str) -> pd.DataFrame:
    df = _snapshot()[t].copy()
    for c in cols(t) if t in TABLES else ():  # 시트에 아직 없는 새 열은 빈 칸으로 (앱 재시작 전)
        if c not in df.columns:
            df[c] = ""
    return df


def refresh_data() -> None:
    """저장한 뒤: 화면용 데이터를 버려 다음 화면에서 시트를 새로 읽게 함 (요청 한 번)."""
    _snapshot.clear()
    load_equipment.clear()
    load_companies.clear()
    load_staff.clear()
    load_logs.clear()
    load_channels.clear()
    get_settings.clear()
    from core import cs  # CS활동 탭은 그 화면에서만 따로 읽음
    cs.load.clear()


def clear_caches() -> None:
    _snapshot.clear()
    for f in ("load_rates", "load_quotes"):  # 아래(견적서)에 정의
        if f in globals():
            globals()[f].clear()
    load_info.clear()
    load_trash.clear()
    load_history.clear()
    load_equipment.clear()
    load_companies.clear()
    load_staff.clear()
    load_logs.clear()
    load_channels.clear()
    get_settings.clear()
    from core import cs
    cs.load.clear()


def _new_ids(n: int) -> list[str]:
    """동시에 저장해도 겹치지 않도록 시각 기반 ID (글자로 저장)."""
    base = int(time.time() * 1000) * 1000
    return [str(base + i) for i in range(n)]


# ── 누가 · 되돌리기 · 휴지통 · 수정 기록 ─────────────────────────
# 모든 저장 함수는 바꾸기 전 모습을 '되돌리기 단계'로 남깁니다. 화면에서 db.undo_last()를 부르면
# 마지막 작업을 거꾸로 적용합니다. 지운 행은 '휴지통' 탭에 원본째 보관해 나중에도 되살릴 수 있습니다.

TABLE_NAMES = {"usage": "실적", "equipment": "장비", "companies": "업체", "staff": "담당자", "settings": "설정",
               "channels": "챔버 구성", "rates": "장비 단가", "quotes": "견적서", "maint": "유지보수",
               "equip_specs": "장비 사양", "equip_docs": "장비 자료", "equip_photos": "장비 사진",
               "equip_notes": "장비 메모", "cs": "CS활동"}
UNDO_KEEP = 30


def who() -> str:
    """지금 앱을 쓰는 사람 (이름을 고르지 않으므로 보통 빈 값)."""
    try:
        return to_str(st.session_state.get("me", ""))
    except Exception:  # noqa: BLE001 - 화면 밖(테스트)
        return ""


def _now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def _state() -> dict:
    try:
        return st.session_state
    except Exception:  # noqa: BLE001
        return {}


def undo_stack() -> list[dict]:
    return _state().setdefault("_undo_stack", [])


class undo_group:
    """with db.undo_group("10/28 저장"): ... 안의 여러 저장을 되돌리기 한 번으로 묶습니다."""

    def __init__(self, label: str):
        self.label = label
        self.outer = False

    def __enter__(self):
        ss = _state()
        if ss.get("_undo_open") is not None:
            self.outer = True
        else:
            ss["_undo_open"] = {"label": self.label, "steps": [], "at": _now()}
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.outer:
            return False
        ss = _state()
        group = ss.pop("_undo_open", None)
        if group and group["steps"]:
            _push(group)
        return False


def _push(entry: dict) -> None:
    stack = undo_stack()
    stack.append(entry)
    del stack[:-UNDO_KEEP]


def _step(step: tuple, label: str) -> None:
    group = _state().get("_undo_open")
    if group is not None:
        group["steps"].append(step)
    else:
        _push({"label": label, "steps": [step], "at": _now()})


def last_undo() -> dict | None:
    stack = undo_stack()
    return stack[-1] if stack else None


_LOG_LOCK = threading.Lock()


def log(action: str, target: str, summary: str) -> None:
    """수정 기록 한 줄. 저장을 기다리게 하지 않도록 뒤에서 씁니다. 기록이 실패해도 저장은 그대로 둡니다."""
    try:
        store = get_store()
        rows = _rows("history", [{"at": _now(), "who": who() or "-", "action": action, "target": target,
                                  "summary": summary[:500]}])
    except Exception:  # noqa: BLE001
        return

    def write() -> None:
        try:
            with _LOG_LOCK:  # 기록 순서가 섞이지 않게 한 줄씩
                store.append("history", rows)
            load_history.clear()
        except Exception:  # noqa: BLE001
            pass

    if getattr(store, "persistent", False):
        threading.Thread(target=write, daemon=True).start()
    else:  # 로컬 파일(시험용)은 바로 씀
        write()


def _usage_summary(r: dict) -> str:
    h = to_num(r.get("hours"), 0) or 0
    return (f"{to_str(r.get('start_date'))[:10]} {to_str(r.get('equip_ref'))} · "
            f"{to_str(r.get('company')) or '내부'} · {h:g}h")


def _master_summary(t: str, r: dict) -> str:
    if t == "maint":
        return " ".join(x for x in (to_str(r.get("date")), to_str(r.get("equip_ref")), to_str(r.get("content"))) if x) \
            or f"ID {to_str(r.get('id'))}"
    if t == "channels":
        return f"{to_str(r.get('unit'))} {to_str(r.get('chamber'))}".strip() or f"ID {to_str(r.get('id'))}"
    if t == "cs":
        return " · ".join(x for x in (to_str(r.get("date"))[:10], to_str(r.get("company")), to_str(r.get("title"))) if x)
    if t == "quotes":
        return f"{to_str(r.get('no'))} {to_str(r.get('company'))}".strip() or f"ID {to_str(r.get('id'))}"
    for k in ("name", "item", "title"):
        if to_str(r.get(k)):
            return to_str(r.get(k))
    if t == "equip_photos":
        return f"사진 (장비 ID {to_str(r.get('equip_id'))})"
    return f"ID {to_str(r.get('id'))}"


def _to_trash(t: str, rows: list[dict]) -> list[str]:
    """지운 행(원래 시트 글자 그대로)을 휴지통에 넣고 휴지통 ID를 돌려줍니다."""
    if not rows:
        return []
    ids = _new_ids(len(rows))
    now = _now()
    recs = [{"id": i, "deleted_at": now, "deleted_by": who(), "table": t,
             "summary": _usage_summary(r) if t == "usage" else _master_summary(t, r),
             "data": json.dumps({k: ("" if k == "thumb" else str(v)) for k, v in r.items()}, ensure_ascii=False)}
            for i, r in zip(ids, rows)]  # 작은사진은 빼서 셀 한도 안에 (되살리면 큰 사진으로 대신 보임)
    get_store().append("trash", _rows("trash", recs))
    load_trash.clear()
    return ids


def _raw(t: str) -> pd.DataFrame:
    return get_store().read(t).astype(str)


def _apply(step: tuple) -> None:
    store = get_store()
    kind, t = step[0], step[1]
    if kind == "delete":  # 추가한 것 지우기
        store.delete_ids(t, step[2])
    elif kind == "put":  # 고치기 전 값으로
        rows: dict[str, list] = step[2]
        have = set(store.read(t)["id"].astype(str).str.strip())
        store.update_rows(t, {k: v for k, v in rows.items() if k in have})
        store.append(t, [v for k, v in rows.items() if k not in have])
    elif kind == "readd":  # 지운 것 되살리기
        have = set(store.read(t)["id"].astype(str).str.strip())
        store.append(t, [r for r in step[2] if str(r[0]).strip() not in have])
        if step[3]:
            store.delete_ids("trash", step[3])
    elif kind == "rewrite":  # 표 전체를 예전 모습으로
        store.rewrite(t, step[2])
        if len(step) > 3 and step[3]:
            store.delete_ids("trash", step[3])


def undo_last() -> str | None:
    """마지막 작업을 되돌리고 그 작업 이름을 돌려줍니다."""
    stack = undo_stack()
    if not stack:
        return None
    entry = stack.pop()
    for step in reversed(entry["steps"]):
        _apply(step)
    clear_caches()
    log("되돌리기", "", entry["label"])
    return entry["label"]


@st.cache_data(ttl=120)
def load_trash() -> pd.DataFrame:
    df = get_store().read("trash")
    df["deleted_at"] = pd.to_datetime(df["deleted_at"], errors="coerce")
    return df.sort_values("deleted_at", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=120)
def load_history() -> pd.DataFrame:
    df = get_store().read("history")
    df["at"] = pd.to_datetime(df["at"], errors="coerce")
    return df.sort_values("at", ascending=False).reset_index(drop=True)


def restore_trash(trash_ids: list[str]) -> dict:
    """휴지통에서 골라 되살립니다. 이미 있는 실적은 건너뛰고, 장비·업체·담당자는 ID가 겹치면 새 ID를 붙입니다."""
    store = get_store()
    tr = store.read("trash")
    tr = tr[tr["id"].astype(str).isin([str(i) for i in trash_ids])]
    done, skipped, used = [], 0, {}
    added_steps: list[tuple] = []
    for r in tr.to_dict("records"):
        t = r["table"]
        if t not in TABLES or t in ("trash", "history", "settings"):
            continue
        try:
            data = json.loads(r["data"])
        except (TypeError, ValueError):
            continue
        if t not in used:
            used[t] = set(store.read(t)["id"].astype(str).str.strip())
        rid = str(data.get("id", "")).strip()
        if rid in used[t]:
            if t in ("usage", "cs"):
                skipped += 1
                done.append(r["id"])
                continue
            nums = [int(x) for x in used[t] if x.isdigit()]
            rid = str((max(nums) if nums else 0) + 1)
        data["id"] = rid
        used[t].add(rid)
        store.append(t, [[data.get(c, "") for c in cols(t)]])
        added_steps.append(("delete", t, [rid]))
        done.append(r["id"])
    if done:
        store.delete_ids("trash", done)
    if added_steps:
        _push({"label": f"휴지통에서 {len(added_steps)}건 되살리기", "steps": added_steps, "at": _now()})
        log("되살리기", "휴지통", f"{len(added_steps)}건")
    clear_caches()
    return {"restored": len(added_steps), "skipped": skipped}


def purge_trash(trash_ids: list[str]) -> int:
    n = get_store().delete_ids("trash", [str(i) for i in trash_ids])
    load_trash.clear()
    if n:
        log("영구 삭제", "휴지통", f"{n}건")
    return n


def _save_master(t: str, out: list[dict]) -> None:
    """장비·업체·담당자 표 전체를 다시 쓰고, 예전 모습은 되돌리기로, 빠진 행은 휴지통으로."""
    store = get_store()
    cur = _raw(t)
    old_rows = cur.values.tolist()
    old_map = {str(r[0]).strip(): [str(x) for x in r] for r in old_rows}
    new_rows = _rows(t, out)
    new_ids = {str(r[0]).strip() for r in new_rows}
    gone = [r for r in cur.to_dict("records") if str(r["id"]).strip() and str(r["id"]).strip() not in new_ids]
    added = sum(1 for i in new_ids if i not in old_map)
    changed = sum(1 for r in new_rows if str(r[0]).strip() in old_map
                  and [str(x) for x in r] != old_map[str(r[0]).strip()][:len(r)])
    if not (added or gone or changed):
        return
    trash_ids = _to_trash(t, gone)
    store.rewrite(t, new_rows)
    _step(("rewrite", t, old_rows, trash_ids), f"{TABLE_NAMES[t]} 저장")
    log("저장", TABLE_NAMES[t], f"추가 {added} · 수정 {changed} · 삭제 {len(gone)}"
        + (" (" + ", ".join(_master_summary(t, g) for g in gone[:5]) + ")" if gone else ""))


# ── 장비 정보 (사양 · 자료 · 사진 · 메모) ────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def load_info() -> dict[str, pd.DataFrame]:
    """장비 정보 화면에서만 읽는 네 탭 (사진이 커서 다른 화면의 묶음 읽기에는 넣지 않음)."""
    out = get_store().read_many(list(INFO_TABS))
    for t, df in out.items():
        df = df.astype(str).apply(lambda c: c.str.strip())
        df = df[df["id"] != ""]
        if "order" in df:
            df["order"] = pd.to_numeric(df["order"], errors="coerce").fillna(0)
            df = df.sort_values(["equip_id", "order"], kind="stable")
        out[t] = df.reset_index(drop=True)
    return out


def save_info_rows(t: str, equip_id: int, records: list[dict], label: str = "") -> int:
    """장비 한 대의 사양·자료·사진 줄을 저장합니다. 그 장비 줄만 행 단위로 고치므로
    다른 장비를 동시에 고치는 사람의 내용은 건드리지 않습니다. 바뀐 줄 수를 돌려줍니다."""
    store = get_store()
    cur = store.read(t).astype(str)
    eid = str(int(equip_id))
    mine = cur[cur["equip_id"].str.strip() == eid]
    old = {str(r["id"]).strip(): r for r in mine.to_dict("records")}
    recs = []
    for i, r in enumerate(records):
        r = dict(r)
        r["equip_id"] = eid
        if "order" in cols(t):
            r["order"] = i
        recs.append(r)
    fresh = [r for r in recs if not to_str(r.get("id"))]
    for r, nid in zip(fresh, _new_ids(len(fresh))):
        r["id"] = nid
    keep = {to_str(r["id"]) for r in recs}
    gone = [r for k, r in old.items() if k not in keep]
    rows = {to_str(r["id"]): _rows(t, [{**old.get(to_str(r["id"]), {}), **r}])[0] for r in recs}
    changed = {k: v for k, v in rows.items() if k in old and [str(x) for x in v] != [str(old[k].get(c, "")) for c in cols(t)]}
    added = [v for k, v in rows.items() if k not in old]
    if not (gone or changed or added):
        return 0
    name = TABLE_NAMES.get(t, t)
    with undo_group(label or f"{name} 저장"):
        if changed:
            store.update_rows(t, changed)
            _step(("put", t, {k: [str(old[k].get(c, "")) for c in cols(t)] for k in changed}), label or name)
        if added:
            store.append(t, added)
            _step(("delete", t, [str(v[0]) for v in added]), label or name)
        if gone:
            trash_ids = _to_trash(t, gone)
            store.delete_ids(t, [to_str(r["id"]) for r in gone])
            _step(("readd", t, [[str(r.get(c, "")) for c in cols(t)] for r in gone], trash_ids), label or name)
    log("저장", name, f"장비 ID {eid} · 추가 {len(added)} · 수정 {len(changed)} · 삭제 {len(gone)}")
    load_info.clear()
    return len(gone) + len(changed) + len(added)


def save_info_note(equip_id: int, caution: str, contact: str) -> bool:
    """장비 한 대의 '사용 시 주의'와 'A/S 연락처'."""
    store = get_store()
    eid = str(int(equip_id))
    cur = store.read("equip_notes").astype(str)
    hit = cur[cur["id"].str.strip() == eid]
    rec = {"id": eid, "caution": caution.strip(), "contact": contact.strip(), "updated_at": _now(),
           "updated_by": who()}
    if not hit.empty:
        o = hit.iloc[0].to_dict()
        if to_str(o.get("caution")) == rec["caution"] and to_str(o.get("contact")) == rec["contact"]:
            return False
        store.update_rows("equip_notes", {eid: _rows("equip_notes", [rec])[0]})
        _step(("put", "equip_notes", {eid: [str(o.get(c, "")) for c in cols("equip_notes")]}), "장비 메모 저장")
    else:
        store.append("equip_notes", _rows("equip_notes", [rec]))
        _step(("delete", "equip_notes", [eid]), "장비 메모 저장")
    log("저장", "장비 메모", f"장비 ID {eid}")
    load_info.clear()
    return True


# ── 설정 ────────────────────────────────────────────────────────

def _settings_raw(df: pd.DataFrame | None = None) -> dict[str, str]:
    df = get_store().read("settings") if df is None else df
    return {to_str(k): str(v) for k, v in zip(df["key"], df["value"]) if to_str(k)}


@st.cache_data(ttl=120)
def get_settings() -> dict:
    plain, chunks = {}, {}
    for k, v in _settings_raw(_tab("settings")).items():
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
    old = _raw("settings").values.tolist()
    get_store().rewrite("settings", [[k, v] for k, v in raw.items()])
    _step(("rewrite", "settings", old), "설정 저장")
    log("저장", "설정", ", ".join(k for k in kv if k != "template_b64") or "i-Tube 양식")
    refresh_data()


# ── 장비 ────────────────────────────────────────────────────────

EQUIP_TEXT = ("name", "code", "kind", "manager", "note", "nfec", "model", "location", "use",
              "group", "species", "category", "asset_no", "maker", "vendor", "system")


def _equipment_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=cols("equipment"))  # 빠진 열이 있어도 멈추지 않게
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    df["annual_hours"] = pd.to_numeric(df["annual_hours"].astype(str).str.replace(",", ""), errors="coerce")
    for c in ("acquired_on", "retired_on"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["in_kpi"] = df["in_kpi"].map(lambda v: str(v).strip().upper() not in ("N", "FALSE", "0", "아니오"))
    for c in EQUIP_TEXT:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["kind"] = df["kind"].replace("", "주장비")
    for c in ("parent_id", "qty", "order"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    ids = set(df["id"])
    # 없는 장비나 자기 자신을 가리키면 최상위로
    df["parent_id"] = [p if pd.notna(p) and int(p) in ids and int(p) != i else pd.NA
                       for p, i in zip(df["parent_id"], df["id"])]
    df["parent_id"] = df["parent_id"].astype("Int64")
    return _tree_sort(df)


def _tree_sort(df: pd.DataFrame) -> pd.DataFrame:
    """상위 장비 바로 아래에 하위 장비가 오도록 정렬하고 depth·root_id·itube_id 를 붙입니다.

    정렬 기준은 '순서' 열(엑셀 순서), 없으면 이름. 고리(A의 상위가 B, B의 상위가 A)는 끊어서 최상위로 둡니다.
    itube_id = 자신 또는 가장 가까운 상위 중 ITUBE번호가 있는 장비 (i-Tube 제출 단위).
    """
    if df.empty:
        for c, v in (("depth", 0), ("root_id", 0), ("itube_id", 0)):
            df[c] = pd.Series(dtype="int64")
        return df.reset_index(drop=True)
    recs = {int(r["id"]): r for r in df.to_dict("records")}
    parent = {i: (int(r["parent_id"]) if pd.notna(r["parent_id"]) else None) for i, r in recs.items()}
    for i in list(parent):  # 고리 끊기
        seen, cur = {i}, parent[i]
        while cur is not None:
            if cur in seen:
                parent[i] = None
                break
            seen.add(cur)
            cur = parent.get(cur)
    kids: dict = {}
    for i, p in parent.items():
        kids.setdefault(p, []).append(i)

    def key(i):
        o = recs[i]["order"]
        return (o if pd.notna(o) else float("inf"), recs[i]["name"], recs[i]["code"], i)

    out, depth, root, itube = [], {}, {}, {}

    def walk(i, d, r, t):
        t = i if recs[i]["code"] else t
        out.append(i)
        depth[i], root[i], itube[i] = d, r, t
        for k in sorted(kids.get(i, []), key=key):
            walk(k, d + 1, r, t)

    for i in sorted(kids.get(None, []), key=key):
        walk(i, 0, i, None)
    df = df.set_index("id").loc[out].reset_index()
    df["parent_id"] = pd.array([parent[i] for i in out], dtype="Int64")
    df["depth"] = [depth[i] for i in out]
    df["root_id"] = [root[i] for i in out]
    df["itube_id"] = pd.array([itube[i] for i in out], dtype="Int64")
    return df


def descendants(eq: pd.DataFrame) -> dict[int, list[int]]:
    """장비 ID → 자신과 모든 하위 장비 ID (세부장비 시간을 위로 더할 때 씀)."""
    if eq.empty or "parent_id" not in eq:
        return {int(i): [int(i)] for i in eq.get("id", [])}
    parent = {int(i): (int(p) if pd.notna(p) else None) for i, p in zip(eq["id"], eq["parent_id"])}
    out = {i: [i] for i in parent}
    for i in parent:
        seen, cur = {i}, parent[i]
        while cur is not None and cur not in seen and cur in out:
            out[cur].append(i)
            seen.add(cur)
            cur = parent.get(cur)
    return out


@st.cache_data(ttl=120)
def load_equipment() -> pd.DataFrame:
    df = _equipment_frame(_tab("equipment"))
    names = dict(zip(df["id"], df["name"]))
    labels = []
    for n, c, d, r in zip(df["name"], df["code"], df["depth"], df["root_id"]):
        lb = f"{n} ({c})" if c else n
        if d > 0 and names.get(r) and names[r] != n:
            lb = f"{lb} · {names[r]}"  # 세부장비는 어느 장비 소속인지 함께
        labels.append(lb)
    seen: dict[str, int] = {}
    for lb in labels:
        seen[lb] = seen.get(lb, 0) + 1
    df["label"] = [f"{lb} #{i}" if seen[lb] > 1 else lb for lb, i in zip(labels, df["id"])]
    return add_pick_labels(df)


CENTERS = ["배터리제조검증지원센터", "MV배터리안전성평가센터", "배터리연구지원센터"]
CENTER_SHORT = {"제조검증": CENTERS[0], "MV": CENTERS[1], "문백": CENTERS[2]}  # 충방전기 현황표의 건물 이름


def center_name(text: str) -> str:
    """장비위치·건물 이름 → 세 센터 중 하나 (모르면 "")."""
    t = to_str(text)
    if "제조검증" in t:
        return CENTERS[0]
    if "MV" in t.upper() or "안전성" in t:
        return CENTERS[1]
    if "연구지원" in t or "문백" in t:
        return CENTERS[2]
    return ""


def equip_centers(eq: pd.DataFrame) -> dict[int, str]:
    """장비 ID → 센터. 세부장비에 위치가 없으면 소속 장비의 센터를 따름."""
    own = {int(i): center_name(loc) for i, loc in zip(eq["id"], eq["location"])}
    parent = {int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)}
    out = {}
    for i in own:
        c, j, n = own[i], i, 0
        while not c and j in parent and n < 10:
            j, n = parent[j], n + 1
            c = own.get(j, "")
        out[i] = c
    return out


def _center(loc: str) -> str:
    """'배터리연구지원센터(문백)' → '문백' (괄호 안 지역명, 없으면 그대로)."""
    loc = to_str(loc)
    if "(" in loc and loc.endswith(")"):
        return loc[loc.rindex("(") + 1:-1].strip()
    return loc


def add_pick_labels(df: pd.DataFrame) -> pd.DataFrame:
    """입력 화면용 짧은 이름(short)과 맨 아래 장비 여부(leaf)를 붙입니다.

    short 는 장비 이름만 씁니다 (예: '5L 믹서(양극)'). 이름이 겹칠 때만 구분할 말을 붙입니다:
    센터 지역명 → 그래도 겹치면 i-Tube 장비번호 → 그래도 겹치면 #ID.
    leaf = 세부장비가 없는 장비 (실적은 여기에 입력).
    """
    df = df.copy()
    if df.empty:
        df["short"], df["leaf"] = pd.Series(dtype=str), pd.Series(dtype=bool)
        return df
    ids = df["id"].astype(int)
    has_kids = set(int(p) for p in df["parent_id"].dropna()) if "parent_id" in df else set()
    df["leaf"] = [i not in has_kids for i in ids]
    code_of = dict(zip(ids, df["code"]))
    itube = df["itube_id"] if "itube_id" in df else pd.Series([pd.NA] * len(df))
    tube = [code_of.get(int(t), "") if pd.notna(t) else "" for t in itube]
    names = list(df["name"])
    extras = ([_center(v) for v in df.get("location", [""] * len(df))], tube)
    groups: dict = {}
    for k, n in enumerate(names):
        groups.setdefault(n, []).append(k)
    out = list(names)
    for n, ks in groups.items():
        if len(ks) < 2:
            continue
        for ex in extras:  # 이 묶음을 서로 다르게 만드는 첫 구분 말을 씀
            vals = [ex[k] for k in ks]
            if all(vals) and len(set(vals)) == len(ks):
                for k in ks:
                    out[k] = f"{n} · {ex[k]}"
                break
    cnt: dict = {}
    for o in out:
        cnt[o] = cnt.get(o, 0) + 1
    d = {o for o, c in cnt.items() if c > 1}
    df["short"] = [f"{o} #{i}" if o in d else o for o, i in zip(out, ids)]
    return df


def pick_ids(eq: pd.DataFrame, day: dt.date | None = None) -> list[int]:
    """실적을 입력할 장비 = 세부장비가 없는 맨 아래 장비 (그날 보유 중인 것만, 장비 목록 순서).

    세부장비가 전부 불용이면 그 위 장비를 고를 수 있게 합니다.
    """
    if eq.empty:
        return []
    act = eq
    if day is not None:
        ts = pd.Timestamp(day)
        act = eq[(eq["retired_on"].isna() | (eq["retired_on"] >= ts)) &
                 (eq["acquired_on"].isna() | (eq["acquired_on"] <= ts))]
    has_kids = set(int(p) for p in act["parent_id"].dropna()) if "parent_id" in act else set()
    return [int(i) for i in act["id"] if int(i) not in has_kids]


def path_text(eq: pd.DataFrame, eid: int) -> str:
    """'5L 믹서 › 고안전성 전지 시제품 전극제조 시스템 (2212-C-0709)' 처럼 위쪽 장비들 (가까운 것부터)."""
    if eq.empty or "parent_id" not in eq:
        return ""
    rec = {int(r["id"]): r for r in eq[["id", "name", "code", "parent_id"]].to_dict("records")}
    parts, seen = [], {int(eid)}
    p = rec.get(int(eid), {}).get("parent_id")
    while p is not None and pd.notna(p) and int(p) in rec and int(p) not in seen:
        r = rec[int(p)]
        parts.append(f"{r['name']} ({r['code']})" if r["code"] else r["name"])
        seen.add(int(p))
        p = r["parent_id"]
    return " › ".join(parts)


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
        "nfec": to_str(r.get("nfec")),
        "model": to_str(r.get("model")),
        "location": to_str(r.get("location")),
        "use": to_str(r.get("use")),
        "parent_id": None if to_num(r.get("parent_id")) is None else int(to_num(r.get("parent_id"))),
        "group": to_str(r.get("group")),
        "species": to_str(r.get("species")),
        "category": to_str(r.get("category")),
        "asset_no": to_str(r.get("asset_no")),
        "qty": to_num(r.get("qty")),
        "maker": to_str(r.get("maker")),
        "vendor": to_str(r.get("vendor")),
        "system": to_str(r.get("system")),
        "order": to_num(r.get("order")),
    }


def save_equipment(edited: pd.DataFrame) -> list[str]:
    """장비 표 편집 결과를 반영합니다. 실적이 있는 장비는 삭제하지 않고 오류로 돌려줍니다.

    표의 행 순서를 '순서'로 저장합니다 (새 행은 소속 장비의 맨 아래로 감).
    지운 장비 아래에 있던 세부장비는 한 단계 위 장비로 옮겨 붙습니다.
    """
    store = get_store()
    current = _equipment_frame(store.read("equipment"))
    orig = {int(r["id"]): r for r in current.to_dict("records")}
    used_ids = set(pd.to_numeric(store.read("usage")["equip_id"], errors="coerce").dropna().astype(int))
    errors: list[str] = []
    out, keep = [], set()
    next_id = (max(orig) if orig else 0) + 1
    for pos, r in enumerate(edited.to_dict("records"), start=1):
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
        rec["order"] = pos
        out.append(rec)
    for gone in sorted(set(orig) - keep):
        if gone in used_ids:
            errors.append(f"'{orig[gone]['name']}'은(는) 사용실적이 있어 삭제하지 않았습니다. 불용일을 입력해 주세요.")
            o = orig[gone]
            out.append(_equip_record(o) | {"id": gone, "order": o["order"] if pd.notna(o["order"]) else None})
    alive = {r["id"] for r in out}
    old_parent = {i: (int(r["parent_id"]) if pd.notna(r["parent_id"]) else None) for i, r in orig.items()}
    for rec in out:
        p = rec["parent_id"]
        while p is not None and p not in alive:  # 지운 상위 장비 → 그 위 장비로
            p = old_parent.get(p)
        rec["parent_id"] = p if p != rec["id"] else None
    _save_master("equipment", out)
    clear_caches()
    return errors


# ── 업체 ────────────────────────────────────────────────────────

COMPANY_TEXT = ("name", "brn", "contact", "phone", "industry", "item", "sub_item", "note")


@st.cache_data(ttl=120)
def load_companies() -> pd.DataFrame:
    df = _tab("companies")
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    for c in COMPANY_TEXT:
        df[c] = df[c].map(to_str)
    return df.sort_values("name").reset_index(drop=True)


def check_companies(edited: pd.DataFrame) -> list[str]:
    """업체 표를 저장하기 전에 검사합니다. 문제가 없으면 빈 목록."""
    from core import seed  # 순환 import 방지
    errors, seen = [], {}
    for r in edited.to_dict("records"):
        name = to_str(r.get("name"))
        if not name:
            continue
        key = name.replace(" ", "")
        if key in seen:
            errors.append(f"'{name}'이(가) 두 번 등록되어 있습니다 ('{seen[key]}'). 하나로 합쳐 주세요.")
        seen[key] = name
        brn_raw = to_str(r.get("brn"))
        if brn_raw and digits(brn_raw) != brn_raw.replace("-", ""):
            errors.append(f"[{name}] 사업자등록번호는 숫자와 '-'만 입력하세요.")
        elif brn_raw and len(digits(brn_raw)) != 10:
            errors.append(f"[{name}] 사업자등록번호는 10자리 숫자입니다.")
        ind, item, sub = (to_str(r.get(k)) for k in ("industry", "item", "sub_item"))
        if item and item not in seed.ITEMS.get(ind, []):
            errors.append(f"[{name}] 품목 '{item}'은(는) 업종 '{ind or '(비어 있음)'}'에 없습니다.")
        elif sub and sub not in seed.SUBITEMS.get(item, []):
            errors.append(f"[{name}] 세부품목 '{sub}'은(는) 품목 '{item or '(비어 있음)'}'에 없습니다.")
    return errors


def sync_company_contact(name: str, contact: str, phone: str) -> None:
    """견적서에 적은 업체 담당자·전화번호를 업체 정보에도 반영 (없는 업체면 새로 추가)."""
    name, phone = to_str(name), to_str(phone)
    contact = to_str(contact).removesuffix("님").strip()
    if not name:
        return
    df = load_companies()
    hit = df["name"] == name
    if not hit.any():
        new = {c: "" for c in COMPANY_TEXT} | {"id": None, "name": name, "contact": contact, "phone": phone}
        save_companies(pd.concat([df, pd.DataFrame([new])], ignore_index=True))
        return
    i = df.index[hit][0]
    changed = False
    for col, v in (("contact", contact), ("phone", phone)):
        if v and df.at[i, col] != v:
            df.at[i, col] = v
            changed = True
    if changed:
        save_companies(df)


def save_companies(edited: pd.DataFrame) -> None:
    store = get_store()
    current = store.read("companies")
    old_ids = set(pd.to_numeric(current["id"], errors="coerce").dropna().astype(int))
    next_id = (max(old_ids) if old_ids else 0) + 1
    out = []
    for r in edited.to_dict("records"):
        rec = {c: to_str(r.get(c)) for c in COMPANY_TEXT}
        if not rec["name"]:
            continue
        rec["brn"] = digits(rec["brn"])
        rid = to_num(r.get("id"))
        if rid is not None and int(rid) in old_ids:
            rec["id"] = int(rid)
        else:
            rec["id"] = next_id
            next_id += 1
        out.append(rec)
    _save_master("companies", out)
    refresh_data()


# ── 담당자 ──────────────────────────────────────────────────────

STAFF_TEXT = ("name", "phone", "email", "role", "note", "dept", "team", "part", "title", "birthday")


@st.cache_data(ttl=120)
def load_staff() -> pd.DataFrame:
    df = _tab("staff")
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    for c in STAFF_TEXT:
        df[c] = df[c].map(to_str)
    df["active"] = df["active"].map(lambda v: to_str(v).upper() not in ("N", "FALSE", "0", "퇴직"))
    df = df[df["name"] != ""]
    if df.empty:  # 예전 '설정 → 팀원 명단'에 적어 둔 이름이 있으면 그대로 보여 줌 (저장하면 담당자 탭으로 옮겨짐)
        members = [to_str(m) for m in (get_settings().get("members") or []) if to_str(m)]
        df = pd.DataFrame({"id": range(1, len(members) + 1), "name": members, "phone": "", "email": "",
                           "role": "", "active": True, "note": "", "dept": "", "team": "", "part": "",
                           "title": "", "birthday": ""})
    return df.sort_values("name").reset_index(drop=True)


def staff_names(include: list[str] | None = None) -> list[str]:
    """입력 화면에서 고를 담당자 이름 (재직 중인 사람 + include 로 넘긴 기존 값)."""
    df = load_staff()
    names = list(df.loc[df["active"], "name"])
    return names + sorted({n for n in (include or []) if n and n not in names})


def check_staff(edited: pd.DataFrame) -> list[str]:
    errors, seen = [], set()
    for r in edited.to_dict("records"):
        name = to_str(r.get("name"))
        if not name:
            continue
        if name in seen:
            errors.append(f"'{name}'이(가) 두 번 등록되어 있습니다. 동명이인이면 '홍길동(시험)'처럼 구분해 주세요.")
        seen.add(name)
    return errors


def save_staff(edited: pd.DataFrame) -> None:
    store = get_store()
    old_ids = set(pd.to_numeric(store.read("staff")["id"], errors="coerce").dropna().astype(int))
    next_id = (max(old_ids) if old_ids else 0) + 1
    out = []
    for r in edited.to_dict("records"):
        rec = {c: to_str(r.get(c)) for c in STAFF_TEXT}
        if not rec["name"]:
            continue
        a = r.get("active")
        rec["active"] = "N" if a is False or to_str(a).upper() in ("N", "FALSE", "0") else "Y"
        rid = to_num(r.get("id"))
        if rid is not None and int(rid) in old_ids:
            rec["id"] = int(rid)
        else:
            rec["id"] = next_id
            next_id += 1
        out.append(rec)
    _save_master("staff", out)
    refresh_data()


# ── 충방전기 챔버 구성 ────────────────────────────────────────

CHARGER_DAY_MAX = 8  # 충방전기는 챔버·채널이 여러 개라도 하루 최대 8시간으로 셈 (주말·공휴일 제외)


@st.cache_data(ttl=120)
def load_channels() -> pd.DataFrame:
    df = _tab("channels")
    for c in ("id", "equip_id", "ch_count", "order"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    for c in ("center", "unit", "cycler", "chamber", "channels"):
        df[c] = df[c].map(to_str)
    df["ch_count"] = df["ch_count"].fillna(0).astype("int64")
    df["order"] = df["order"].fillna(df["id"])
    return df.sort_values(["order", "id"]).reset_index(drop=True)


def charger_ids(eq: pd.DataFrame | None = None, ch: pd.DataFrame | None = None) -> set[int]:
    """충방전기 = 챔버 구성에 연결된 장비, 또는 이름에 '충방전기'가 들어간 맨 아래 장비."""
    eq = load_equipment() if eq is None else eq
    ch = load_channels() if ch is None else ch
    ids = {int(i) for i in ch["equip_id"].dropna()} if not ch.empty else set()
    if not eq.empty:
        leaf = eq["leaf"] if "leaf" in eq else pd.Series([True] * len(eq), index=eq.index)
        ids |= {int(i) for i, n, lf in zip(eq["id"], eq["name"], leaf) if lf and "충방전기" in to_str(n)}
    return ids


def charger_caps() -> dict[int, tuple[float, int]]:
    """가동률 계산용: 충방전기 장비 ID → (하루 최대 시간, 묶음 = 맨 위 주장비 ID).

    같은 주장비 아래 충방전기 여러 대가 같은 날 돌아도 주장비 합계가 하루 최대 시간을 넘지 않게 묶어서 셉니다.
    """
    lim = float(to_num(get_settings().get("charger_day_max"), CHARGER_DAY_MAX) or CHARGER_DAY_MAX)
    eq = load_equipment()
    root = dict(zip(eq["id"].astype(int), eq["root_id"])) if "root_id" in eq else {}
    return {i: (lim, int(root.get(i, i)) if pd.notna(root.get(i, i)) else i) for i in charger_ids(eq)}


def chamber_ids(v) -> list[int]:
    """실적의 '챔버ID' 칸 ('3,4') → [3, 4]."""
    out = []
    for x in to_str(v).replace(" ", "").split(","):
        n = to_num(x)
        if n is not None:
            out.append(int(n))
    return out


def save_channels(edited: pd.DataFrame) -> None:
    store = get_store()
    old_ids = set(pd.to_numeric(store.read("channels")["id"], errors="coerce").dropna().astype(int))
    next_id = (max(old_ids) if old_ids else 0) + 1
    out = []
    for k, r in enumerate(edited.to_dict("records"), start=1):
        rec = {c: to_str(r.get(c)) for c in ("center", "unit", "cycler", "chamber", "channels")}
        if not (rec["unit"] or rec["chamber"]):
            continue
        eid, n = to_num(r.get("equip_id")), to_num(r.get("ch_count"))
        rec["equip_id"] = int(eid) if eid is not None else ""
        rec["ch_count"] = int(n) if n is not None else _count_channels(rec["channels"])
        rec["order"] = k
        rid = to_num(r.get("id"))
        if rid is not None and int(rid) in old_ids:
            rec["id"] = int(rid)
        else:
            rec["id"] = next_id
            next_id += 1
        out.append(rec)
    _save_master("channels", out)
    refresh_data()


def _count_channels(text: str) -> int | str:
    """'17~32' → 16, '1' → 1. 모르면 빈 값."""
    t = to_str(text).replace("~", "-").replace("–", "-").replace(" ", "")
    if not t:
        return ""
    total = 0
    for part in t.split(","):
        a, _, b = part.partition("-")
        try:
            total += (int(b) - int(a) + 1) if b else 1
        except ValueError:
            return ""
    return total


# ── 유지보수 ────────────────────────────────────────────────────

MAINT_KINDS = ["점검", "수리", "교정", "부품 교체", "청소", "기타"]
MAINT_TEXT = ("kind", "content", "staff", "note")


def load_maint() -> pd.DataFrame:
    """유지보수 기록 (최근 날짜부터). date 는 날짜, equip_id 는 숫자(없으면 비움)."""
    df = _tab("maint")
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    df["date"] = df["date"].map(to_date)
    df["equip_id"] = pd.to_numeric(df["equip_id"], errors="coerce").astype("Int64")
    for c in MAINT_TEXT + ("equip_ref",):
        df[c] = df[c].map(to_str)
    df["cost"] = pd.to_numeric(df["cost"].map(lambda v: to_str(v).replace(",", "")), errors="coerce").astype("Int64")
    df["_o"] = df["date"].map(lambda d: d.toordinal() if d else 10 ** 7)  # 날짜 없는 줄은 맨 위
    return df.sort_values(["_o", "id"], ascending=False).drop(columns="_o").reset_index(drop=True)


def save_maint(edited: pd.DataFrame) -> int:
    """화면 표 전체를 저장합니다. 장비도 내용도 없는 빈 줄은 버립니다. 저장한 줄 수를 돌려줍니다."""
    store = get_store()
    old_ids = set(pd.to_numeric(store.read("maint")["id"], errors="coerce").dropna().astype(int))
    next_id = (max(old_ids) if old_ids else 0) + 1
    names = dict(zip(load_equipment()["id"].astype(int), load_equipment()["name"]))
    out = []
    for r in edited.to_dict("records"):
        rec = {c: to_str(r.get(c)) for c in MAINT_TEXT}
        eid = to_num(r.get("equip_id"))
        rec["equip_id"] = int(eid) if eid is not None else ""
        rec["equip_ref"] = names.get(int(eid), "") if eid is not None else to_str(r.get("equip_ref"))
        d = to_date(r.get("date"))
        rec["date"] = d
        cost = to_num(r.get("cost"))
        rec["cost"] = int(cost) if cost is not None else ""
        if not (rec["equip_id"] != "" or rec["equip_ref"] or rec["content"] or rec["kind"]):
            continue
        rid = to_num(r.get("id"))
        if rid is not None and int(rid) in old_ids:
            rec["id"] = int(rid)
        else:
            rec["id"] = next_id
            next_id += 1
        out.append(rec)
    out.sort(key=lambda x: int(x["id"]))
    _save_master("maint", out)
    refresh_data()
    return len(out)


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


@st.cache_data(ttl=120)
def load_logs() -> pd.DataFrame:
    df = _usage_frame(_tab("usage")).drop(columns=["equip_ref"])
    eq = load_equipment()[["id", "name", "code", "kind"]].rename(columns={
        "id": "_eid", "name": "equip_name", "code": "equip_code", "kind": "equip_kind"})
    df = df.merge(eq, left_on="equip_id", right_on="_eid", how="left").drop(columns=["_eid"])
    for c in ("equip_name", "equip_code", "equip_kind"):
        df[c] = df[c].fillna("")
    # i-Tube 에 올릴 때 쓰는 장비 = 자신 또는 ITUBE번호가 있는 가장 가까운 상위 장비
    full = load_equipment()
    by_id = full.set_index("id")
    it = {int(i): (int(t) if pd.notna(t) else None) for i, t in zip(full["id"], full["itube_id"])}
    tid = df["equip_id"].map(lambda v: it.get(int(v)) if pd.notna(v) else None)
    # ITUBE번호 없는 장비가 섞이면 tid 가 숫자+NaN 이 되므로 None 대신 notna 로 확인
    for col, key in (("itube_name", "name"), ("itube_code", "code"), ("itube_kind", "kind")):
        df[col] = tid.map(lambda t, k=key: by_id.at[int(t), k] if pd.notna(t) and int(t) in by_id.index else "")
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
              "disclose", "detail", "include_holidays", "purpose_detail", "etc", "created_by", "chambers", "ch_part", "series", "fee_log"):
        if k in out:
            out[k] = to_str(out[k])
    return out


def _equip_names() -> dict[int, str]:
    eq = load_equipment()
    return dict(zip(eq["id"].astype(int), eq["label"]))


def insert_logs(records: list[dict], user: str = "", ids_out: list | None = None) -> int:
    """실적을 추가하고 추가한 건수를 돌려줍니다. ids_out 을 주면 새 id 를 담아 줍니다 (되돌리기용)."""
    if not records:
        return 0
    now = dt.datetime.now().replace(microsecond=0)
    names = _equip_names()
    rows = []
    for rid, r in zip(_new_ids(len(records)), records):
        row = _clean_log(r)
        if not row.get("created_by"):
            row["created_by"] = user or who()
        row.update(id=rid, equip_ref=names.get(row.get("equip_id"), ""), created_at=now, updated_at=now,
                   updated_by=who())
        rows.append(row)
        if ids_out is not None:
            ids_out.append(rid)
    get_store().append("usage", _rows("usage", rows))
    _step(("delete", "usage", [str(r["id"]) for r in rows]), f"실적 {len(rows)}건 추가")
    log("추가", "실적", f"{len(rows)}건: " + " / ".join(_usage_summary(r) for r in rows[:3])
        + (" …" if len(rows) > 3 else ""))
    refresh_data()
    return len(rows)


def update_logs(changes: dict[int, dict]) -> int:
    """고친 실적만 그 행에 다시 씁니다 (다른 사람이 동시에 추가·수정한 행은 건드리지 않음)."""
    if not changes:
        return 0
    store = get_store()
    df = store.read("usage")
    names = _equip_names()
    now = dt.datetime.now().replace(microsecond=0)
    ids = df["id"].astype(str).str.strip()
    out: dict[str, list] = {}
    before: dict[str, list] = {}
    for log_id, vals in changes.items():
        key = str(int(log_id))
        hit = df[ids == key]
        if hit.empty:
            continue  # 그 사이 다른 사람이 지운 실적
        cur = hit.iloc[0].to_dict()
        before[key] = [str(cur.get(c, "")) for c in cols("usage")]
        row = _clean_log(vals)
        row["updated_at"] = now
        row["updated_by"] = who()
        if "equip_id" in row:
            row["equip_ref"] = names.get(row["equip_id"], "")
        cur.update(row)
        out[key] = _rows("usage", [cur])[0]
    n = store.update_rows("usage", out)
    if n:
        _step(("put", "usage", before), f"실적 {n}건 수정")
        log("수정", "실적", f"{n}건: " + " / ".join(
            _usage_summary(dict(zip(cols("usage"), out[k]))) for k in list(out)[:3]) + (" …" if n > 3 else ""))
    refresh_data()
    return n


def delete_logs(ids: list[int]) -> int:
    if not ids:
        return 0
    keys = {str(int(i)) for i in ids}
    cur = _raw("usage")
    gone = cur[cur["id"].str.strip().isin(keys)]
    trash_ids = _to_trash("usage", gone.to_dict("records"))
    n = get_store().delete_ids("usage", list(keys))
    if n:
        _step(("readd", "usage", gone.values.tolist(), trash_ids), f"실적 {n}건 삭제")
        log("삭제", "실적", f"{n}건: " + " / ".join(_usage_summary(r) for r in gone.to_dict("records")[:3])
            + (" …" if n > 3 else ""))
    refresh_data()
    return n


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
        _save_master("equipment", eq)
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
        store.read("companies").to_excel(xw, sheet_name="companies", index=False)
        store.read("staff").to_excel(xw, sheet_name="staff", index=False)
        store.read("usage").to_excel(xw, sheet_name="usage_log", index=False)
        store.read("maint").to_excel(xw, sheet_name="maint", index=False)
        st_df.to_excel(xw, sheet_name="settings", index=False)
        store.read("rates").to_excel(xw, sheet_name="rates", index=False)
        store.read("quotes").to_excel(xw, sheet_name="quotes", index=False)
        for t in ("equip_specs", "equip_docs", "equip_notes"):  # 사진은 엑셀 셀에 안 들어가 뺌
            store.read(t).to_excel(xw, sheet_name=t, index=False)
        store.read("cs").to_excel(xw, sheet_name="cs", index=False)
    return bio.getvalue()


def restore_bytes(data: bytes) -> dict:
    with undo_group("백업 복원"):
        for t in ("equipment", "usage", "staff", "companies", "settings", "rates", "quotes", "maint", "cs"):
            _step(("rewrite", t, _raw(t).values.tolist()), "백업 복원")
        res = _restore_bytes(data)
    log("복원", "전체", f"장비 {res['equipment']}대, 실적 {res['usage_log']}건")
    return res


def _restore_bytes(data: bytes) -> dict:
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
    eq = sheets["equipment"].reindex(columns=cols("equipment")).fillna("")
    lg = sheets["usage_log"].reindex(columns=cols("usage")).fillna("")
    store = get_store()
    store.rewrite("equipment", eq.values.tolist())
    store.rewrite("usage", lg.values.tolist())
    if "staff" in sheets:
        store.rewrite("staff", sheets["staff"].reindex(columns=cols("staff")).fillna("").values.tolist())
    if "companies" in sheets:  # 업체 탭이 생기기 전 백업에는 없음
        store.rewrite("companies", sheets["companies"].reindex(columns=cols("companies")).fillna("").values.tolist())
    for t in ("rates", "quotes"):  # 견적서 기능(2026-11-04) 전 백업에는 없음
        if t in sheets:
            store.rewrite(t, sheets[t].reindex(columns=cols(t)).fillna("").values.tolist())
    if "maint" in sheets:  # 유지보수 탭이 생기기 전 백업에는 없음
        store.rewrite("maint", sheets["maint"].reindex(columns=cols("maint")).fillna("").values.tolist())
    if "cs" in sheets:  # CS활동 탭이 생기기 전 백업에는 없음
        store.rewrite("cs", sheets["cs"].reindex(columns=cols("cs")).fillna("").values.tolist())
    if "settings" in sheets:
        keep = {k: v for k, v in _settings_raw().items() if k.startswith("template_b64")}
        st_df = sheets["settings"].reindex(columns=["key", "value"]).fillna("")
        rows = [[k, v] for k, v in st_df.values.tolist() if k and not k.startswith("template_b64")]
        store.rewrite("settings", rows + [[k, v] for k, v in keep.items()])
    clear_caches()
    return {"equipment": len(eq), "usage_log": len(lg)}


# ── 견적서 · 장비 단가 ──────────────────────────────────────────

RATE_TEXT = ("name", "spec", "unit", "note")


@st.cache_data(ttl=120)
def load_rates() -> pd.DataFrame:
    """장비 단가. 장비ID 가 있으면 장비 목록의 장비, 없으면 시험·기타 항목."""
    df = get_store().read("rates")
    for c in ("id", "equip_id", "price_req", "price_self", "order"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype("int64")
    for c in RATE_TEXT:
        df[c] = df[c].map(to_str)
    df["unit"] = df["unit"].replace("", "hr")
    df["order"] = df["order"].fillna(df["id"])
    return df.sort_values(["order", "id"]).reset_index(drop=True)


def save_rates(rows: list[dict]) -> None:
    """장비 단가 표 전체 저장 (값이 하나도 없는 장비 줄은 저장하지 않음). 예전 모습은 되돌리기로."""
    old_ids = set(pd.to_numeric(get_store().read("rates")["id"], errors="coerce").dropna().astype(int))
    next_id = (max(old_ids) if old_ids else 0) + 1
    out = []
    for i, r in enumerate(rows, start=1):
        rec = {c: to_str(r.get(c)) for c in RATE_TEXT}
        eid = to_num(r.get("equip_id"))
        rec["equip_id"] = int(eid) if eid is not None else ""
        for c in ("price_req", "price_self"):
            v = to_num(r.get(c))
            rec[c] = (int(v) if float(v).is_integer() else v) if v is not None else ""
        if rec["equip_id"] == "" and not rec["name"]:
            continue
        if rec["equip_id"] != "" and rec["price_req"] == "" and rec["price_self"] == "" and not rec["note"] \
                and not rec["spec"] and not r.get("_named"):
            continue
        rid = to_num(r.get("id"))
        if rid is not None and int(rid) in old_ids:
            rec["id"] = int(rid)
        else:
            rec["id"] = next_id
            next_id += 1
        rec["order"] = i
        out.append(rec)
    _save_master("rates", out)
    load_rates.clear()


@st.cache_data(ttl=120)
def load_quotes() -> pd.DataFrame:
    df = get_store().read("quotes")
    df["id"] = df["id"].map(to_str)
    df = df[df["id"] != ""]
    for c in ("amount", "amount_vat"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df["issued_on"] = pd.to_datetime(df["issued_on"], errors="coerce")
    return df.sort_values(["issued_on", "created_at"], ascending=False).reset_index(drop=True)


def quote_seqs(year: int) -> list[str]:
    df = load_quotes()
    df = df[df["issued_on"].dt.year == year]
    return [to_str(s) for s in df["seq"]]


def save_quote(rec: dict) -> str:
    """견적서 한 건 저장 (id 가 있으면 고치기, 없으면 새로). 저장한 id 를 돌려줍니다."""
    store = get_store()
    rec = dict(rec)
    now = _now()
    rid = to_str(rec.get("id"))
    have = store.read("quotes")
    have_ids = {to_str(x) for x in have["id"]}
    rec["updated_at"] = now
    if rid and rid in have_ids:
        old = have[have["id"].map(to_str) == rid].iloc[0].astype(str).tolist()
        rec["created_at"] = to_str(have.loc[have["id"].map(to_str) == rid, "created_at"].iloc[0]) or now
        store.update_rows("quotes", {rid: _rows("quotes", [rec])[0]})
        _step(("put", "quotes", {rid: old}), f"견적서 {rec.get('no', '')} 고치기")
        log("수정", "견적서", f"{rec.get('no', '')} {rec.get('company', '')}")
    else:
        rid = _new_ids(1)[0]
        rec["id"] = rid
        rec["created_at"] = now
        store.append("quotes", _rows("quotes", [rec]))
        _step(("delete", "quotes", [rid]), f"견적서 {rec.get('no', '')} 발급")
        log("발급", "견적서", f"{rec.get('no', '')} {rec.get('company', '')}")
    load_quotes.clear()
    return rid
