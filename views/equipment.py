"""기준 정보 › 장비 목록 및 수수료 단가: ① 장비 목록 ② 수수료 단가 (장비 단가 + 시험·기타 항목).

- 평소엔 표가 잠겨 있고, '선택'한 줄만 아래에서 고쳐 [저장] / [삭제] (2026-11-10).
- '소속 장비'를 고르면 그 장비의 세부장비가 되고, 세부장비 시간은 소속 장비로 합산됩니다.
- 쓰지 않는 장비는 지우지 말고 불용일을 넣습니다 (실적이 있는 장비는 지워지지 않음).
"""
import html

import pandas as pd
import streamlit as st

from core import db, quotes, seed
from core.quote_doc import UNITS
from core.terms import w
from ui_style import page_header
from views.common import center_pick, excel_box, pick_done, pick_table, search_box

KPI_COL = w("가동률 산정")
XK = "시험·기타"  # 장비가 아닌 단가 항목의 장비구분
TREE = "　"          # 구조 표시 칸 (읽기 전용)
PARENT = "소속 장비"  # 상위 장비 (고르면 세부장비가 됨)
NO_PARENT = "—"       # 소속 없음 (독립 장비)

# 화면 열 이름은 장비 리스트 엑셀(260310 내부기준 탭)의 항목 이름을 따름
COLS = {
    "id": "id", "group": "대분류", "species": "주장비(종)", "name": "장비명(한글)", "code": "ITUBE번호",
    "kind": "장비구분", "category": "구분", "qty": "대수", "manager": "관리자", "location": "장비위치", "use": "장비용도",
    "model": "모델명", "maker": "제조사", "vendor": "구매처", "asset_no": "자산번호", "nfec": "국가연구시설장비번호",
    "system": "시스템 구성", "annual_hours": "연간기준시간", "acquired_on": "도입일", "retired_on": "불용일",
    "in_kpi": KPI_COL, "note": "비고",
}
BASIC = ["장비명(한글)", "대분류", "주장비(종)", PARENT, "ITUBE번호", "장비구분", "대수", "관리자", "장비위치",
         "장비용도"]
# 2026-11-05 장비 단가를 장비 목록에 합침: '단가' 를 켜면 이 열들이 보이고, 저장하면 단가 탭에 같이 저장
RATE = {"spec": "견적 용량", "unit": "단위", "price_req": "의뢰 단가", "price_self": "직접 단가"}

CSS = """<style>
.eq-sum {display:flex; flex-wrap:wrap; gap:.5rem; margin:-.2rem 0 1rem;}
.eq-sum .p {display:flex; align-items:baseline; gap:.45rem; padding:.45rem .95rem; border-radius:999px;
  background:var(--panel); border:1px solid var(--line); box-shadow:var(--card-shadow); font-size:.85rem; color:var(--muted);}
.eq-sum .p b {font-size:1.05rem; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums;}
.eq-sum .p.a {background:var(--accent-bg); border-color:color-mix(in srgb, var(--accent) 25%, transparent);}
.eq-sum .p.a b {color:var(--accent);}
.eq-sum .p.w {background:var(--warn-bg); border-color:color-mix(in srgb, var(--warn) 25%, transparent);}
.eq-sum .p.w b {color:var(--warn);}
.eq-sum .p.m b {color:var(--muted);}
.eq-h {font-weight:700; color:var(--ink); font-size:.95rem; margin:.6rem 0 .2rem;}
.eq-h span {color:var(--muted); font-weight:600; margin-left:.3rem;}
</style>"""


def _tree_mark(depth: int) -> str:
    return "" if depth <= 0 else "　" * (depth - 1) + "└"


def _summary(eq: pd.DataFrame) -> None:
    top = eq[eq["depth"] == 0]
    sub = eq[eq["depth"] > 0]
    unreg = top[top["code"] == ""]
    pills = [("a", "장비", len(top)), ("", "세부장비", len(sub)), ("w", "ITUBE번호 없음", len(unreg))]
    st.markdown("<div class='eq-sum'>" + "".join(
        f"<div class='p {c}'>{html.escape(t)}<b>{n:,}</b></div>" for c, t, n in pills) + "</div>",
        unsafe_allow_html=True)


def _page(title: str) -> tuple[pd.DataFrame, dict]:
    page_header(title, "기준 정보")
    st.markdown(CSS, unsafe_allow_html=True)
    msg = st.session_state.pop("equip_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    return db.load_equipment(full=True), db.get_settings()


def render() -> None:
    """기준 정보 › 장비 목록 (2026-11-10 수수료 단가는 따로 메뉴)."""
    eq, cfg = _page("장비 목록")
    _devices(eq, cfg)


def render_prices() -> None:
    """예전 주소(/prices, /rates) → 장비 목록과 같은 화면 (2026-11-10 수수료 단가는 장비 목록 표 안으로)."""
    render()


def _devices(eq: pd.DataFrame, cfg: dict) -> None:
    """① 장비 목록: 평소엔 잠겨 있고 '선택'한 줄만 고쳐 저장 / 삭제 (2026-11-10)."""
    _summary(eq)
    label_of = dict(zip(eq["id"].astype(int), eq["label"]))
    view = eq[list(COLS)].rename(columns=COLS)
    view.insert(1, TREE, [_tree_mark(d) for d in eq["depth"]])
    view.insert(2, PARENT, [label_of.get(int(p), NO_PARENT) if pd.notna(p) else NO_PARENT for p in eq["parent_id"]])
    rates = db.load_rates()
    rate_of = {int(r["equip_id"]): r for r in rates.to_dict("records") if pd.notna(r["equip_id"])}
    chg = db.charger_ids(eq)
    ids = eq["id"].astype(int).tolist()
    g = lambda i, c: rate_of.get(i, {}).get(c)
    # 2026-11-10: 수수료 단가도 장비 목록 표 안에 (메뉴 하나로)
    view[RATE["spec"]] = [g(i, "spec") or "" for i in ids]
    view[RATE["unit"]] = [g(i, "unit") or ("ch" if i in chg else "hr") for i in ids]
    view[RATE["price_req"]] = pd.to_numeric([g(i, "price_req") for i in ids], errors="coerce")
    view[RATE["price_self"]] = pd.to_numeric([g(i, "price_self") for i in ids], errors="coerce")
    view["도입일"] = view["도입일"].dt.date
    view["불용일"] = view["불용일"].dt.date
    # 2026-11-10: 장비가 아닌 시험·기타 항목(클린룸, 고온시험 등)도 같은 표에 (장비구분 = '시험·기타 항목', 단가 탭에만 저장)
    view["_x"] = None
    known = set(ids)
    ex = rates[rates["equip_id"].isna() | ~rates["equip_id"].fillna(-1).astype(int).isin(known)]
    n_dev = len(view)
    if not ex.empty:
        view = pd.concat([view, pd.DataFrame({
            "_x": ex["id"].values, "장비명(한글)": ex["name"].fillna("").values, "장비구분": XK, PARENT: NO_PARENT,
            RATE["spec"]: ex["spec"].fillna("").values, RATE["unit"]: ex["unit"].fillna("hr").replace("", "hr").values,
            RATE["price_req"]: pd.to_numeric(ex["price_req"], errors="coerce").values,
            RATE["price_self"]: pd.to_numeric(ex["price_self"], errors="coerce").values,
            "비고": ex["note"].fillna("").values})], ignore_index=True)
    is_x = pd.Series([i >= n_dev for i in range(len(view))], index=view.index)
    xl_eq = eq.copy()  # 엑셀 내려받기용: 장비 열 + 단가 열 (2026-11-10 한 표에 단가까지)
    for v in RATE.values():
        xl_eq[v] = list(view[v][:n_dev])
    extras_now = view.iloc[n_dev:].copy()

    xl_heads = {"parent_id": "소속 장비 ID"} | {k: v for k, v in COLS.items()
                                               if k not in ("id", "retired_on", "in_kpi")} | {v: v for v in RATE.values()}
    with st.container(horizontal=True, vertical_alignment="center"):
        center = center_pick("equip_center")
        st.space("stretch")
        sub = st.toggle("세부장비도 보기", key="equip_subs")
        excel_box("equip_xl", xl_eq, xl_heads, "장비", lambda m: _apply_excel(m, rates, extras_now))
    # 2026-11-10 주장비를 골라 그 아래 세부장비를 펼쳐 봄 (표 안에서 바로 펼치기는 Streamlit 표가 지원하지 않음)
    pid = {int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)}
    has_kids = set(pid.values())
    open_opts = [label_of[i] for i in eq["id"].astype(int) if i in has_kids and i not in pid]
    if center and open_opts:  # 센터를 고르면 그 센터 장비만 고를 수 있게
        cen0 = db.equip_centers(eq)
        id_of_label = {l: i for i, l in label_of.items()}
        open_opts = [l for l in open_opts if cen0.get(id_of_label[l]) == center]
    opened = st.multiselect("세부장비 펼치기", open_opts, key="equip_open", placeholder="장비를 검색해 고르면 그 아래 세부장비가 함께 보여요",
                            label_visibility="collapsed") if open_opts and not sub else []
    open_ids = {i for i, l in label_of.items() if l in opened}

    def _shown(i: int) -> bool:
        if i not in pid:
            return True
        n = 0
        while i in pid and n < 10:  # 위쪽 장비 중 하나라도 펼쳤으면 그 아래 전부 보임
            i, n = pid[i], n + 1
            if i in open_ids:
                return True
        return False
    q = search_box("equip_q", "장비명·ITUBE번호·관리자·자산번호·비고")
    mask = pd.Series(True, index=view.index)
    if q:
        hay = view[["장비명(한글)", "ITUBE번호", "관리자", "자산번호", "주장비(종)", "모델명", "비고"]].fillna("").astype(str).agg(" ".join, axis=1)
        mask &= hay.str.contains(q, case=False, regex=False)
    elif not sub:
        mask &= pd.Series([_shown(int(i)) for i in eq["id"]] + [True] * (len(view) - n_dev), index=view.index)
    if center:
        cen = db.equip_centers(eq)
        mask &= pd.to_numeric(view["id"], errors="coerce").map(cen).eq(center) & ~is_x

    kinds = list(dict.fromkeys(seed.EQUIP_KINDS_ALL + [k for k in eq["kind"] if k] + [XK]))
    cats = list(dict.fromkeys(["단독장비", "시스템장비", "시스템시설", "단독장비(복수구매)"] + [c for c in eq["category"] if c]))
    uses = list(dict.fromkeys(list(seed.PURPOSES) + ["제조"] + [u for u in eq["use"] if u]))
    action, out, gone = pick_table(
        view, "equip_tbl", mask=mask, name_col="장비명(한글)", add_label="장비 추가",
        height=min(640, 38 + 35 * (int(mask.sum()) + 1)),
        column_order=BASIC + list(RATE.values()) + ["비고"], edit_order=BASIC + list(RATE.values()) + ["모델명", "제조사", "구매처", "자산번호",
                                                                          "국가연구시설장비번호", "연간기준시간", "도입일",
                                                                          "불용일", KPI_COL, "비고"],
        column_config={
            TREE: st.column_config.TextColumn(TREE, width=36, disabled=True),
            "장비명(한글)": st.column_config.TextColumn(required=True, width=280),
            PARENT: st.column_config.SelectboxColumn(
                options=[NO_PARENT] + list(label_of.values()), width="medium", default=NO_PARENT,
                help="고르면 그 장비의 세부장비가 되고, 사용시간이 그 장비로 합산됩니다."),
            "대분류": st.column_config.TextColumn(width="small"),
            "주장비(종)": st.column_config.TextColumn(width="medium"),
            "ITUBE번호": st.column_config.TextColumn(width="small", help="비우면 i-Tube 제출 파일에서 빠집니다."),
            "장비구분": st.column_config.SelectboxColumn(options=kinds, width="small"),
            "구분": st.column_config.SelectboxColumn(options=cats),
            "장비용도": st.column_config.SelectboxColumn(options=uses, width="small"),
            "대수": st.column_config.NumberColumn(min_value=0, step=1, format="%d", width=56),
            "관리자": st.column_config.TextColumn(width="small"),
            "장비위치": st.column_config.TextColumn(width="medium"),
            "연간기준시간": st.column_config.NumberColumn(min_value=0, step=100, format="%d",
                                                     help=f"비워 두면 기본값 {float(cfg.get('annual_hours') or 2000):,.0f}시간."),
            "도입일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "불용일": st.column_config.DateColumn(format="YYYY-MM-DD", help="쓰지 않게 된 날. 지우는 대신 넣으세요."),
            KPI_COL: st.column_config.CheckboxColumn(default=True),
            "비고": st.column_config.TextColumn(width="medium"),
            RATE["spec"]: st.column_config.TextColumn(width="small"),
            RATE["unit"]: st.column_config.SelectboxColumn(options=UNITS, default="hr", width=64,
                                                         help="ch = 채널 1개 · 1시간 단가"),
            RATE["price_req"]: st.column_config.NumberColumn(format="localized", min_value=0, width="small",
                                                             help="우리가 운전할 때"),
            RATE["price_self"]: st.column_config.NumberColumn(format="localized", min_value=0, width="small",
                                                              help="업체가 직접 쓸 때"),
        })
    if action:
        id_of = {v: k for k, v in label_of.items()}
        xo = out["_x"].notna() | (out["장비구분"].eq(XK) & pd.to_numeric(out["id"], errors="coerce").isna())
        extras, out = out[xo], out[~xo]
        o = out.drop(columns=[TREE, "_x"] + list(RATE.values())).rename(columns={v: k for k, v in COLS.items()})
        o["parent_id"] = [id_of.get(p) if isinstance(p, str) and p and p != NO_PARENT else None for p in out[PARENT]]
        o = o.drop(columns=[PARENT])
        errors = db.save_equipment(o)
        for e in errors:
            st.warning(e)
        if not errors:
            _save_rates_from(out, rates, extras)
            pick_done("equip_tbl")
            st.session_state.equip_saved = f"{len(gone)}대 삭제했어요." if gone else "저장했어요."
            st.rerun()


def _apply_excel(merged: pd.DataFrame, rates: pd.DataFrame, extras: pd.DataFrame) -> list[str]:
    """엑셀로 올린 장비 + 단가 반영: 장비를 먼저 저장하고, 오류가 없으면 단가도 저장."""
    rate_cols = list(RATE.values())
    errors = list(db.save_equipment(merged.drop(columns=rate_cols, errors="ignore")))
    if errors:
        return errors
    out = merged.rename(columns={"name": "장비명(한글)"})[["id", "장비명(한글)"] + rate_cols]
    _save_rates_from(out, rates, extras)
    return []


RATE_HEADS = {"equip_id": "장비ID", "name": "견적서 이름", "spec": "용량", "unit": "단위", "price_req": "의뢰 단가",
              "price_self": "직접 단가", "note": "비고"}


def _save_rates_from(out: pd.DataFrame, rates: pd.DataFrame, extras: pd.DataFrame) -> None:
    """장비 목록 표의 단가 칸을 단가 탭에 저장. 새 장비는 이름으로 id를 찾고, 지운 장비의 단가는 함께 지움."""
    eq = db.load_equipment(full=True)
    id_by_name = dict(zip(eq["name"], eq["id"].astype(int)))
    known = set(eq["id"].astype(int))
    old = {int(r["equip_id"]): r for r in rates.to_dict("records") if pd.notna(r["equip_id"])}
    rows = []
    for r in out.to_dict("records"):
        eid = db.to_num(r.get("id")) or id_by_name.get(r.get("장비명(한글)"))
        if eid is None or int(eid) not in known:
            continue
        eid = int(eid)
        rows.append({"id": (old.get(eid) or {}).get("id"), "equip_id": eid, "name": "", "_named": True,
                     "spec": r.get(RATE["spec"]), "unit": r.get(RATE["unit"]), "price_req": r.get(RATE["price_req"]),
                     "price_self": r.get(RATE["price_self"]), "note": (old.get(eid) or {}).get("note", "")})
    seen = {r["equip_id"] for r in rows}
    rows += [r | {"_named": True} for r in rates.to_dict("records")
             if pd.notna(r["equip_id"]) and int(r["equip_id"]) in known and int(r["equip_id"]) not in seen]
    for r in extras.to_dict("records"):  # 시험·기타 항목
        nm = quotes._s(r.get("장비명(한글)"))
        if nm:
            rid = db.to_num(r.get("_x"))
            rows.append({"id": int(rid) if rid is not None else None, "equip_id": None, "name": nm,
                         "spec": r.get(RATE["spec"]), "unit": r.get(RATE["unit"]), "price_req": r.get(RATE["price_req"]),
                         "price_self": r.get(RATE["price_self"]), "note": r.get("비고")})
    db.save_rates(rows)
