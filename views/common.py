"""여러 화면이 함께 쓰는 기간 선택 위젯."""
import datetime as dt

import pandas as pd
import streamlit as st

from core.calc import period_bounds

HALF = ["상반기", "하반기"]


def period_picker(key: str, kinds: list[str], default_kind: str, completed: bool = False,
                  years: list[int] | None = None, extra=None) -> tuple[dt.date, dt.date, str, str]:
    """기간 단위와 기간을 한 줄에서 고르게 하고 (시작일, 종료일, 이름, 단위)를 돌려줍니다.

    completed=True 면 기본값이 '직전에 끝난 기간'(예: 11월이면 3분기)입니다.
    extra 가 있으면 줄 오른쪽 끝 칸에서 extra(칸)을 불러 다른 위젯을 그립니다.
    """
    today = dt.date.today()
    row = st.columns([2.6, 1, 1, 0.2, 2.2] if extra else [2.6, 1, 1, 2.4], vertical_alignment="bottom")
    with row[0]:
        kind = st.segmented_control("기간 단위", kinds, default=default_kind, key=f"{key}_kind") or default_kind
    if extra:
        with row[4]:
            extra()
    ref = today
    if completed and kind in ("월", "분기", "반기"):
        ref = period_bounds(kind, today)[0] - dt.timedelta(days=1)

    if kind == "직접 지정":  # 시작일과 종료일을 따로 고름 (기본: 이번 달 1일 ~ 오늘)
        s = row[1].date_input("시작일", value=today.replace(day=1), format="YYYY-MM-DD", key=f"{key}_from")
        e = row[2].date_input("종료일", value=today, format="YYYY-MM-DD", key=f"{key}_to")
        s, e = s or today.replace(day=1), e or today
        if e < s:
            s, e = e, s
        return s, e, f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", kind
    if kind == "주":
        d = row[1].date_input("기준일", value=today, format="YYYY-MM-DD", key=f"{key}_week",
                              help="고른 날이 속한 주(월~일)를 봅니다.")
        s, e, label = period_bounds("주", d)
        return s, e, label, kind

    years = sorted(set((years or []) + [today.year, ref.year]), reverse=True)
    year = row[1].selectbox("연도", years, index=years.index(ref.year), key=f"{key}_year",
                            format_func=lambda v: f"{v}년")
    if kind == "월":
        m = row[2].selectbox("월", list(range(1, 13)), index=ref.month - 1, format_func=lambda v: f"{v}월",
                             key=f"{key}_month")
        d = dt.date(year, m, 1)
    elif kind == "분기":
        q = row[2].selectbox("분기", [1, 2, 3, 4], index=(ref.month - 1) // 3, format_func=lambda v: f"{v}분기",
                             key=f"{key}_q")
        d = dt.date(year, (q - 1) * 3 + 1, 1)
    elif kind == "반기":
        h = row[2].selectbox("반기", HALF, index=0 if ref.month <= 6 else 1, key=f"{key}_h")
        d = dt.date(year, 1 if h == "상반기" else 7, 1)
    else:
        d = dt.date(year, 1, 1)
    s, e, label = period_bounds(kind, d)
    return s, e, label, kind


# ── 목록 표의 '삭제' 칸 ─────────────────────────────────────────

DEL = "삭제"


def with_delete_column(view):
    """표 맨 앞에 '삭제' 체크 칸을 붙입니다."""
    view = view.copy()
    view.insert(0, DEL, False)
    return view


def delete_config() -> dict:
    return {DEL: st.column_config.CheckboxColumn(DEL, width="small", default=False,
                                                 help="지울 행에 체크한 뒤 저장을 누르세요.")}


def split_deleted(edited, name_col: str):
    """(남길 행, 지울 행 이름 목록)."""
    mask = edited[DEL].fillna(False).astype(bool)
    names = [str(n) for n in edited.loc[mask, name_col] if str(n) not in ("", "None", "<NA>", "nan")]
    return edited[~mask].drop(columns=[DEL]), names


def confirm_delete(names: list[str], key: str, unit: str = "개") -> bool:
    """지울 행이 있으면 무엇이 지워지는지 한 줄로 알려 줍니다 (지운 것은 되돌리기·휴지통으로 살릴 수 있음)."""
    if names:
        shown = ", ".join(names[:5]) + (f" 외 {len(names) - 5}{unit}" if len(names) > 5 else "")
        st.caption(f"저장하면 {len(names)}{unit} 삭제: {shown} · 실수해도 '되돌리기'나 휴지통에서 살릴 수 있습니다.")
    return True


# ── 여러 사람이 같이 쓸 때: 내가 고치기 시작한 표를 붙잡아 두고, 저장할 때 남이 고친 것과 합침 ──────

def _has_edits(v) -> bool:
    return isinstance(v, dict) and any(v.get(x) for x in ("edited_rows", "added_rows", "deleted_rows"))


def pin_table(prefix: str, view: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """고치는 중이면 처음 펼친 표를 그대로 돌려줌 (그사이 다른 사람이 저장해도 내 칸이 엉뚱한 줄로 가지 않게).

    돌려주는 값: (화면에 쓸 표, 다른 사람이 바꾼 최신 표 또는 None).
    """
    ss = st.session_state
    pk = f"_pin_{prefix}"
    busy = any(_has_edits(ss[k]) for k in list(ss.keys()) if str(k).startswith(prefix) and k != pk)
    if busy and pk in ss:
        base = ss[pk]
        same = base.shape == view.shape and base.astype(str).equals(view.astype(str))
        return base, (None if same else view)
    ss[pk] = view.copy()
    return view, None


def unpin(prefix: str) -> None:
    st.session_state.pop(f"_pin_{prefix}", None)


def merge_edits(base: pd.DataFrame, edited: pd.DataFrame, latest: pd.DataFrame, key: str = "id") -> pd.DataFrame:
    """내가 바꾼 줄만 최신 표에 얹습니다 (남이 그사이 고친·추가한 줄은 그대로 둠).

    - base: 내가 고치기 시작할 때 표, edited: 내가 고친 표, latest: 지금 시트의 표
    - 내가 지운 줄은 최신 표에서도 지우고, 내가 새로 넣은 줄(ID 없음)은 맨 뒤에 붙임
    """
    def k(v):
        n = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
        return None if pd.isna(n) else int(n)

    def norm(v):
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).strip()

    def row_s(r):
        return {c: norm(r.get(c)) for c in base.columns if c != key}

    b = {k(r[key]): r for r in base.to_dict("records") if k(r[key]) is not None}
    e_rows = edited.to_dict("records")
    e = {k(r[key]): r for r in e_rows if k(r[key]) is not None}
    out, seen = [], set()
    for r in latest.to_dict("records"):
        i = k(r[key])
        if i in b and i not in e:      # 내가 지운 줄
            continue
        if i in e and row_s(e[i]) != row_s(b.get(i, {})):  # 내가 고친 줄
            r = {**r, **e[i]}
        out.append(r)
        seen.add(i)
    out += [r for r in e_rows if k(r[key]) is None]  # 내가 새로 넣은 줄
    return pd.DataFrame(out, columns=list(edited.columns)).reset_index(drop=True)


# ── 검색해도 바로 고칠 수 있는 목록 표 ───────────────────────────

POS = "_pos"


def center_pick(key: str) -> str | None:
    """전체 / 센터 셋 중 고르기. 전체면 None."""
    from core import db
    c = st.segmented_control("센터", ["전체"] + db.CENTERS + ["기타"], default="전체", key=key,
                             label_visibility="collapsed")
    return None if c in (None, "전체") else c


def in_center(cen, center: str):
    """센터 이름 시리즈 → 고른 센터인지. '기타' 는 세 센터 어디에도 없는 장비."""
    from core import db
    return ~cen.isin(db.CENTERS) if center == "기타" else cen.eq(center)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def excel_box(key: str, df, heads: dict, sheet: str, apply, extra_sheet: tuple | None = None) -> None:
    """엑셀로 내려받기 → 고쳐서 올리기. apply(합친 목록) 은 오류 목록을 돌려줌."""
    from core import sheet_io
    with st.popover("엑셀로 한번에 고치기", icon=":material/table_view:"):
        data = sheet_io.to_xlsx(df, heads, sheet)
        if extra_sheet:  # 읽기용 참고 시트 (올려도 반영되지 않음)
            data = sheet_io.add_sheet(data, *extra_sheet)
        st.download_button("1. 지금 목록 내려받기", data, mime=XLSX,
                           file_name=f"{sheet}_목록_{dt.date.today():%y%m%d}.xlsx", icon=":material/download:",
                           key=f"{key}_dl", width="stretch")
        st.caption("맨 앞 ID는 고치지 마세요. 새 줄은 ID를 비워 두면 추가돼요. 파일에서 뺀 줄은 지워지지 않아요.")
        up = st.file_uploader("2. 고친 엑셀 올리기", type=["xlsx"], key=f"{key}_up")
        if up is None:
            return
        try:
            merged, n_add, n_upd, notes = sheet_io.merge(df, up.getvalue(), heads)
        except Exception as e:  # 다른 양식
            st.error(f"파일을 읽지 못했어요: {e}")
            return
        for n in notes:
            st.caption(n)
        if not (n_add or n_upd):
            st.caption("바뀐 내용이 없어요.")
            return
        if st.button(f"3. 반영하기 (수정 {n_upd} · 추가 {n_add})", type="primary", key=f"{key}_go", width="stretch"):
            errors = apply(merged)
            for e in errors or []:
                st.error(e)
            if not errors:
                st.session_state.pop(f"{key}_up", None)
                st.toast(f"엑셀 내용을 반영했어요 (수정 {n_upd} · 추가 {n_add})", icon=":material/check_circle:")
                st.rerun()


def search_box(key: str, placeholder: str) -> str:
    return st.text_input("검색", placeholder=placeholder, key=key, label_visibility="collapsed",
                         icon=":material/search:")


def filtered_editor(view, mask, **kwargs):
    """검색에 맞는 행만 보여 주되 그대로 고칠 수 있는 표.

    돌려주는 값은 전체 목록(숨긴 행 + 고친 행 + 새 행)이며, 원래 순서를 지키고 새 행은 맨 뒤에 둡니다.
    view 에는 이미 '삭제' 칸이 있어야 합니다.
    """
    view = view.copy()
    view[POS] = range(len(view))
    order = kwargs.pop("column_order", None)
    shown = view if mask is None else view[mask].reset_index(drop=True)
    edited = st.data_editor(shown, column_order=order, **kwargs)
    full = edited if mask is None else pd.concat([view[~mask], edited])
    full = full.sort_values(POS, na_position="last", kind="stable").drop(columns=[POS])
    return full.reset_index(drop=True), len(edited)


# ── 다른 화면으로 바로 가기 (대시보드에서 누르면 장비 상세·수수료 입력) ─────────

PAGES: dict = {}  # app.py 가 채움: {"equip": st.Page, "records": st.Page, ...}
_CLICK_KEYS = ("dash_equip_chart", "dash_heat", "dash_equip_tbl", "dash_comp_chart")


def _leave() -> None:
    # 눌러 둔 그래프 선택이 남아 있으면 대시보드로 돌아왔을 때 또 넘어가므로 지움
    for k in _CLICK_KEYS:
        st.session_state.pop(k, None)


def go_equipment(equip_id: int) -> None:
    st.session_state.detail_equip = int(equip_id)
    _leave()
    if "equip" in PAGES:
        st.switch_page(PAGES["equip"])


def go_master_equipment(name: str) -> None:
    """'기준 정보 › 장비' 표를 이 장비 이름으로 찾아 둔 채 엽니다."""
    st.session_state.equip_q = name
    _leave()
    if "equipment" in PAGES:
        st.switch_page(PAGES["equipment"])


def go_records(company: str | None = None, equip_label: str | None = None, start=None, end=None) -> None:
    st.session_state.records_prefilter = {"company": company, "equip": equip_label, "start": start, "end": end}
    _leave()
    if "records" in PAGES:
        st.switch_page(PAGES["records"])


# ── 입력 화면에서 바로 새 업체 등록 ─────────────────────────────

def _idx(options: list, value, default: int = 0) -> int:
    return options.index(value) if value in options else default


@st.dialog("새 업체 등록")
def new_company_dialog() -> None:
    """입력하던 화면을 떠나지 않고 업체를 추가합니다. 등록하면 바로 목록에서 고를 수 있습니다."""
    from core import db, seed
    name = st.text_input("업체명", placeholder="예: ○○배터리", key="nc_name")
    brn = st.text_input("사업자등록번호", placeholder="숫자 10자리 (- 는 넣어도 됨)", key="nc_brn")
    c1, c2, c3 = st.columns(3)
    ind = c1.selectbox("업종", seed.INDUSTRIES, index=_idx(seed.INDUSTRIES, "전기전자"), key="nc_ind")
    items = seed.ITEMS[ind]
    item = c2.selectbox("품목", items, index=_idx(items, "이차전지_에너지"), key=f"nc_item_{ind}")
    subs = seed.SUBITEMS.get(item, [])
    sub = c3.selectbox("세부품목", subs, key=f"nc_sub_{item}") if subs else ""
    c1, c2 = st.columns(2)
    contact = c1.text_input("업체 담당자", key="nc_contact")
    phone = c2.text_input("연락처", key="nc_phone")
    if st.button("등록", type="primary", icon=":material/add_business:", width="stretch", disabled=not name.strip()):
        comp = db.load_companies()
        rows = comp.to_dict("records") + [{"name": name.strip(), "brn": brn, "industry": ind, "item": item,
                                           "sub_item": sub or "", "contact": contact, "phone": phone, "note": ""}]
        df = pd.DataFrame(rows)
        errors = db.check_companies(df)
        if errors:
            for e in errors:
                st.error(e)
            return
        db.save_companies(df)
        st.session_state.company_added = name.strip()
        for k in [k for k in st.session_state if str(k).startswith("nc_")]:
            st.session_state.pop(k, None)
        st.rerun()


def _num_step(key: str, delta: float, lo: float, hi: float | None) -> None:
    try:
        v = float(str(st.session_state.get(key, "0")).replace(",", "") or 0)
    except ValueError:
        v = 0
    v = max(lo, v + delta)
    if hi is not None:
        v = min(hi, v)
    st.session_state[key] = f"{int(v):,}" if v == int(v) else f"{v:g}"


def num_input(container, label: str, key: str, value: float, step: float = 1, lo: float = 0,
              hi: float | None = None, steppers: bool = True) -> float:
    """숫자 칸 (−/＋ 버튼 + 직접 입력). Streamlit 숫자 칸 대신 글자 칸을 써서 가볍고 오류가 없음."""
    if key not in st.session_state:
        st.session_state[key] = f"{int(value):,}" if float(value) == int(value) else f"{value:g}"
    box = container.container(key=f"num_{key}", gap=None)
    box.markdown(f"<div class='num-l'>{label}</div>", unsafe_allow_html=True)
    with box.container(horizontal=True, gap=None, vertical_alignment="center", key=f"numr_{key}"):
        if steppers:
            st.button("−", key=f"{key}_dn", on_click=_num_step, args=(key, -step, lo, hi))
        st.text_input(label, key=key, label_visibility="collapsed")
        if steppers:
            st.button("＋", key=f"{key}_up", on_click=_num_step, args=(key, step, lo, hi))
    try:
        v = float(str(st.session_state.get(key, "0")).replace(",", "") or 0)
    except ValueError:
        box.caption(":red[숫자만 입력하세요]")
        return float(value)
    v = max(lo, v)
    return min(hi, v) if hi is not None else v


# ── 잠긴 표 + 고른 줄만 고치기 (2026-11-10 사용자 요청: 평소엔 수정 막고, 선택한 줄만 고쳐서 저장 / 삭제) ──

PICK = "선택"


def _as_text(cfg: dict) -> dict:
    """잠긴 표에선 고르기 칸도 글자 칸으로 (고르기 칸은 가운데 정렬이 안 먹어서, 2026-11-10)."""
    out = {}
    for k, c in cfg.items():
        if isinstance(c, dict) and (c.get("type_config") or {}).get("type") == "selectbox":
            c = {**c, "type_config": {"type": "text"}}
        out[k] = c
    return out


def pick_table(view: pd.DataFrame, key: str, *, column_config: dict, column_order: list[str], name_col: str,
               mask=None, height: int | None = None, can_add: bool = True, add_label: str = "새로 추가",
               edit_order: list[str] | None = None) -> tuple[str | None, pd.DataFrame, list[str]]:
    """평소에는 읽기만 되는 표. 맨 앞 '선택'을 체크한 줄만 아래 칸에서 고치고 [저장] / [삭제].

    돌려주는 값: (누른 버튼 'save' · 'delete' · None, 반영한 전체 표, 지운 줄 이름).
    전체 표는 view 순서 그대로이고 새 줄은 맨 뒤에 붙습니다 (기존 save_* 함수에 그대로 넘기면 됨).
    """
    ss = st.session_state
    ver = ss.get(f"{key}_ver", 0)
    view = view.reset_index(drop=True)
    shown = view if mask is None else view[pd.Series(mask, index=view.index).fillna(False).astype(bool)]
    table = shown.copy()
    table.insert(0, PICK, False)
    order = [PICK] + [c for c in column_order if c in table.columns]
    locked = st.data_editor(
        table, key=f"{key}_lock_{ver}", hide_index=True, width="stretch", column_order=order,
        disabled=[c for c in table.columns if c != PICK],
        height=height or min(640, 38 + 35 * (len(table) + 1)),
        column_config={**_as_text(column_config), PICK: st.column_config.CheckboxColumn(PICK, width=64, default=False)})
    sel = [int(i) for i in locked.index[locked[PICK].fillna(False).astype(bool)]]
    n_new = ss.get(f"{key}_new_{ver}", 0)
    action, out, gone = None, view, []
    if sel or n_new:
        blank = pd.DataFrame([{c: None for c in view.columns}] * n_new,
                             index=range(len(view), len(view) + n_new)) if n_new else view.iloc[0:0]
        part = pd.concat([view.loc[sel], blank]) if n_new else view.loc[sel]
        with st.container(border=True, key=f"{key}_editbox"):
            ed = st.data_editor(part, key=f"{key}_edit_{ver}_{'_'.join(map(str, sel))}_{n_new}", hide_index=True,
                                width="stretch", column_order=edit_order or [c for c in column_order if c in part.columns],
                                column_config=column_config)
            with st.container(horizontal=True, gap="small"):
                if st.button("저장", type="primary", icon=":material/save:", key=f"{key}_save_{ver}"):
                    action = "save"
                if sel and st.button("삭제", icon=":material/delete:", key=f"{key}_del_{ver}"):
                    action = "delete"
                if st.button("취소", type="tertiary", key=f"{key}_cancel_{ver}"):
                    ss[f"{key}_ver"] = ver + 1
                    st.rerun()
        if action == "save":
            out = view.copy()
            for i in sel:
                out.loc[i] = ed.loc[i]
            new = ed.loc[[i for i in ed.index if i >= len(view)]]
            new = new[new.apply(lambda r: any(str(v).strip() not in ("", "None", "nan", "<NA>", "NaT")
                                              for v in r.values), axis=1)]
            out = pd.concat([out, new]).reset_index(drop=True)
        elif action == "delete":
            gone = [str(view.at[i, name_col]) for i in sel]
            out = view.drop(index=sel).reset_index(drop=True)
    if can_add and not (sel or n_new):
        if st.button(add_label, icon=":material/add:", key=f"{key}_add_{ver}", type="tertiary"):
            ss[f"{key}_new_{ver}"] = 1
            st.rerun()
    return action, out, gone


def pick_done(key: str) -> None:
    """저장·삭제 뒤 표를 처음 상태로 (선택 풀림)."""
    st.session_state[f"{key}_ver"] = st.session_state.get(f"{key}_ver", 0) + 1
