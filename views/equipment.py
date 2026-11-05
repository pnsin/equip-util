"""기준 정보 › 장비: 장비 › 세부장비 › 세세부를 한 표에서 엑셀처럼 고칩니다.

- 셀을 바로 고치고, 여러 칸을 끌어 선택해 복사·붙여넣기(Ctrl+C/V), Delete 로 지우기, 머리글을 눌러 정렬.
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
from views.common import (center_pick, excel_box, merge_edits, pin_table, unpin, confirm_delete, delete_config, filtered_editor, search_box, split_deleted,
                          with_delete_column)

KPI_COL = w("가동률 산정")
TREE = "　"          # 구조 표시 칸 (읽기 전용)
OPEN = "펼침"         # 세부장비가 있는 장비: 체크하면 세부장비를 펼침 (처음엔 모두 접힘)
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
BASIC = [OPEN, TREE, "장비명(한글)", "대분류", "주장비(종)", PARENT, "ITUBE번호", "장비구분", "대수", "관리자", "장비위치",
         "장비용도"]
# 2026-11-05 장비 단가를 장비 목록에 합침: '단가' 를 켜면 이 열들이 보이고, 저장하면 단가 탭에 같이 저장
RATE = {"name": "견적서 이름", "spec": "견적 용량", "unit": "단위", "price_req": "의뢰 단가", "price_self": "직접 단가"}

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
</style>"""


def _tree_mark(depth: int) -> str:
    return "■" if depth <= 0 else "　" * (depth - 1) + "└"


def _summary(eq: pd.DataFrame) -> None:
    top = eq[eq["depth"] == 0]
    sub = eq[eq["depth"] > 0]
    unreg = top[top["code"] == ""]
    pills = [("a", "장비", len(top)), ("", "세부장비", len(sub)), ("w", "ITUBE번호 없음", len(unreg))]
    st.markdown("<div class='eq-sum'>" + "".join(
        f"<div class='p {c}'>{html.escape(t)}<b>{n:,}</b></div>" for c, t, n in pills) + "</div>",
        unsafe_allow_html=True)


def render() -> None:
    cfg = db.get_settings()
    page_header("장비 목록", "기준 정보")
    st.markdown(CSS, unsafe_allow_html=True)
    msg = st.session_state.pop("equip_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    eq = db.load_equipment()
    _summary(eq)

    label_of = dict(zip(eq["id"].astype(int), eq["label"]))
    view = eq[list(COLS)].rename(columns=COLS)
    view.insert(1, TREE, [_tree_mark(d) for d in eq["depth"]])
    view.insert(2, PARENT, [label_of.get(int(p), NO_PARENT) if pd.notna(p) else NO_PARENT for p in eq["parent_id"]])
    view["도입일"] = view["도입일"].dt.date
    view["불용일"] = view["불용일"].dt.date
    rates = db.load_rates()
    rate_of = {int(r["equip_id"]): r for r in rates.to_dict("records") if pd.notna(r["equip_id"])}
    chg = db.charger_ids(eq)
    for k, h in RATE.items():
        view[h] = [rate_of.get(int(i), {}).get(k) for i in eq["id"]]
    view[RATE["name"]] = [(lambda n: "" if n == nm else n)(rate_of.get(int(i), {}).get("name") or "")
                          for i, nm in zip(eq["id"], eq["name"])]  # 장비명과 같으면 비움 (장비명을 바꾸면 따라감)
    view[RATE["spec"]] = [(rate_of.get(int(i), {}).get("spec") or "") for i in eq["id"]]
    view[RATE["unit"]] = [rate_of.get(int(i), {}).get("unit") or ("ch" if int(i) in chg else "hr") for i in eq["id"]]
    for h in (RATE["price_req"], RATE["price_self"]):
        view[h] = pd.to_numeric(view[h], errors="coerce")

    xl_heads = {"parent_id": "소속 장비 ID"} | {k: v for k, v in COLS.items()
                                               if k not in ("id", "retired_on", "in_kpi")}

    def _apply_xl(m):
        bad = [e for e in db.save_equipment(m)]
        return bad

    with st.container(horizontal=True, vertical_alignment="center"):
        center = center_pick("equip_center")
        excel_box("equip_xl", eq, xl_heads, "장비", _apply_xl)
    q = search_box("equip_q", "장비명·ITUBE번호·관리자·자산번호")

    # 접기·펼치기: 처음엔 맨 위 장비만, '펼침'을 체크하면 그 아래 세부장비가 보임 (검색 중엔 모두 보임)
    opened: set = st.session_state.setdefault("equip_open", set())
    par = {int(i): (int(p) if pd.notna(p) else None) for i, p in zip(eq["id"], eq["parent_id"])}
    has_kids = {p for p in par.values() if p is not None}
    view.insert(0, OPEN, [(int(i) in opened) if int(i) in has_kids else None for i in eq["id"]])
    view, newer = pin_table("equip_editor_", view)
    view[OPEN] = [(int(i) in opened) if pd.notna(i) and int(i) in has_kids else None for i in view["id"]]

    def _visible(i) -> bool:
        p = par.get(int(i)) if pd.notna(i) else None
        while p is not None:
            if p not in opened:
                return False
            p = par.get(p)
        return True
    mask = pd.Series(True, index=view.index)
    if q:
        hay = view[["장비명(한글)", "ITUBE번호", "관리자", "자산번호", "주장비(종)", "모델명"]].astype(str).agg(" ".join, axis=1)
        mask &= hay.str.contains(q, case=False, regex=False)
    if not q:
        mask &= view["id"].map(_visible)
    if center:
        cen = db.equip_centers(eq)
        mask &= pd.to_numeric(view["id"], errors="coerce").map(cen).eq(center)
    filtered = True
    ekey = f"equip_editor_{q}_{hash(frozenset(opened))}"

    kinds = list(dict.fromkeys(seed.EQUIP_KINDS_ALL + [k for k in eq["kind"] if k]))
    cats = list(dict.fromkeys(["단독장비", "시스템장비", "시스템시설", "단독장비(복수구매)"] + [c for c in eq["category"] if c]))
    uses = list(dict.fromkeys(list(seed.PURPOSES) + ["제조"] + [u for u in eq["use"] if u]))
    edited, shown = filtered_editor(
        with_delete_column(view), mask if filtered else None,
        key=ekey, num_rows="dynamic", on_change=_toggle, args=(ekey, view[mask]["id"].tolist()), hide_index=True, width="stretch",
        height=min(680, 38 + 35 * (int(mask.sum()) + 2)),
        column_order=BASIC + list(RATE.values()) + ["삭제"],
        column_config=delete_config() | {
            OPEN: st.column_config.CheckboxColumn(OPEN, width=58, help="체크하면 세부장비가 펼쳐져요."),
            TREE: st.column_config.TextColumn(TREE, width=36, disabled=True),
            "장비명(한글)": st.column_config.TextColumn(required=True, width=260),
            PARENT: st.column_config.SelectboxColumn(
                options=[NO_PARENT] + list(label_of.values()), width="medium", default=NO_PARENT,
                help="고르면 그 장비의 세부장비가 되고, 사용시간이 그 장비로 합산됩니다. 비우면 독립 장비."),
            "대분류": st.column_config.TextColumn(width="small"),
            "주장비(종)": st.column_config.TextColumn(width="medium"),
            "ITUBE번호": st.column_config.TextColumn(help="예: 2312-C-0436 · 비우면 i-Tube 제출 파일에서 빠집니다 "
                                                          "(세부장비는 소속 장비 번호로 올라감)."),
            "장비구분": st.column_config.SelectboxColumn(options=kinds),
            "구분": st.column_config.SelectboxColumn(options=cats),
            "장비용도": st.column_config.SelectboxColumn(options=uses),
            "대수": st.column_config.NumberColumn(min_value=0, step=1, format="%d", width="small"),
            "연간기준시간": st.column_config.NumberColumn(min_value=0, step=100, format="%d",
                                                     help=f"비워 두면 기본값 {float(cfg.get('annual_hours') or 2000):,.0f}시간(설정)."),
            "도입일": st.column_config.DateColumn(format="YYYY-MM-DD", help="이 날 이전은 가용시간에서 빠집니다."),
            "불용일": st.column_config.DateColumn(format="YYYY-MM-DD", help="쓰지 않게 된 날. 지우는 대신 넣으세요."),
            KPI_COL: st.column_config.CheckboxColumn(default=True, help=w("가동률 합계에 넣을 장비. 소속 장비가 대상이면 세부장비는 따로 세지 않습니다.")),
            "시스템 구성": st.column_config.TextColumn(width="medium"),
            "비고": st.column_config.TextColumn(width="large"),
            RATE["name"]: st.column_config.TextColumn(width="medium", help="견적서에 찍히는 이름. 비우면 장비명."),
            RATE["unit"]: st.column_config.SelectboxColumn(options=UNITS, width="small",
                                                         help="ch = 채널 1개 · 1시간 단가 (견적서에서 채널 수를 곱함)"),
            RATE["price_req"]: st.column_config.NumberColumn(format="localized", min_value=0, help="우리가 운전할 때 시간당"),
            RATE["price_self"]: st.column_config.NumberColumn(format="localized", min_value=0, help="업체가 직접 쓸 때 시간당"),
        },
    )
    _extras(rates)
    st.caption("셀을 끌어 선택하고 Ctrl+C / Ctrl+V 로 엑셀처럼 복사할 수 있어요. "
               "머리글을 누르면 정렬됩니다.")

    edited, deleted = split_deleted(edited, "장비명(한글)")
    ok = confirm_delete(deleted, "equip_editor_del", "대")
    if st.button("변경 내용 저장", type="primary", disabled=not ok, icon=":material/save:"):
        if newer is not None:  # 그사이 다른 분이 저장함 → 내가 바꾼 줄만 얹기
            edited = merge_edits(view, edited, newer)
        unpin("equip_editor_")
        id_of = {v: k for k, v in label_of.items()}
        rate_rows = edited[["id"] + list(RATE.values())].rename(columns={v: k for k, v in RATE.items()})
        out = edited.drop(columns=[OPEN, TREE] + list(RATE.values())).rename(columns={v: k for k, v in COLS.items()})
        out["parent_id"] = [id_of.get(p) if isinstance(p, str) and p else None for p in edited[PARENT].replace(NO_PARENT, "")]
        out = out.drop(columns=[PARENT])
        errors = db.save_equipment(out)
        for e in errors:
            st.warning(e)
        if not errors:
            _save_prices(rate_rows, rates, eq)
            st.session_state.equip_saved = "장비 목록을 저장했어요." + (f" ({len(deleted)}대 삭제)" if deleted else "")
            for k in [k for k in st.session_state if str(k).startswith("equip_editor_")]:
                st.session_state.pop(k, None)
            st.rerun()


def _toggle(key: str, ids: list) -> None:
    """'펼침' 칸을 누르면 그 장비를 펼치거나 접음 (다른 칸 수정은 그대로 둠)."""
    ss = st.session_state
    rows = (ss.get(key) or {}).get("edited_rows", {})
    for pos, ch in list(rows.items()):
        if OPEN in ch and int(pos) < len(ids) and pd.notna(ids[int(pos)]):
            ss.equip_open ^= {int(ids[int(pos)])}
            ch.pop(OPEN, None)


def _save_prices(rows: pd.DataFrame, rates: pd.DataFrame, eq: pd.DataFrame) -> None:
    """장비 줄의 단가 + 시험·기타 항목(그대로)을 단가 탭에 저장. 바뀐 게 없으면 시트를 건드리지 않음."""
    old = {int(r["equip_id"]): r for r in rates.to_dict("records") if pd.notna(r["equip_id"])}
    name_of = dict(zip(eq["id"].astype(int), eq["name"]))
    out = []
    for r in rows.to_dict("records"):
        eid = db.to_num(r.get("id"))
        if eid is None or int(eid) not in name_of:
            continue
        o = old.get(int(eid), {})
        nm = quotes._s(r.get("name"))
        out.append({"id": o.get("id"), "equip_id": int(eid), "name": nm, "_named": bool(nm),
                    "spec": r.get("spec"), "unit": r.get("unit"), "price_req": r.get("price_req"),
                    "price_self": r.get("price_self"), "note": o.get("note", "")})
    out += [r for r in rates.to_dict("records") if pd.isna(r["equip_id"]) or int(r["equip_id"]) not in name_of]
    db.save_rates(out)


def _extras(rates: pd.DataFrame) -> None:
    """장비 목록에 없는 시험·기타 항목 (클린룸, 고온시험 등) 단가."""
    known = set(db.load_equipment()["id"].astype(int))
    ex = rates[rates["equip_id"].isna() | ~rates["equip_id"].fillna(-1).astype(int).isin(known)]
    ex = ex[["id", "name", "spec", "unit", "price_req", "price_self", "note"]].reset_index(drop=True)
    with st.expander(f"시험 · 기타 항목 단가 ({len(ex)})", icon=":material/science:"):
        ed = st.data_editor(ex, key="equip_extras", hide_index=True, width="stretch", num_rows="dynamic",
                            column_order=["name", "spec", "unit", "price_req", "note"],
                            column_config={
                                "name": st.column_config.TextColumn("항목", width="large", required=True),
                                "spec": st.column_config.TextColumn("용량", width="small"),
                                "unit": st.column_config.SelectboxColumn("단위", options=UNITS, default="hr", width="small"),
                                "price_req": st.column_config.NumberColumn("단가", format="localized", min_value=0),
                                "note": st.column_config.TextColumn("비고", width="large")})
        if st.button("항목 단가 저장", key="equip_extras_save", icon=":material/save:"):
            dev = [r for r in rates.to_dict("records") if pd.notna(r["equip_id"]) and int(r["equip_id"]) in known]
            dev = [r | {"_named": True} for r in dev]
            db.save_rates(dev + [r | {"equip_id": None} for r in ed.to_dict("records") if quotes._s(r.get("name"))])
            st.session_state.equip_saved = "항목 단가를 저장했어요."
            st.rerun()
