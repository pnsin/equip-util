"""기준 정보 › 장비: 장비 › 세부장비 › 세세부를 한 표에서 엑셀처럼 고칩니다.

- 셀을 바로 고치고, 여러 칸을 끌어 선택해 복사·붙여넣기(Ctrl+C/V), Delete 로 지우기, 머리글을 눌러 정렬.
- '소속 장비'를 고르면 그 장비의 세부장비가 되고, 세부장비 시간은 소속 장비로 합산됩니다.
- 쓰지 않는 장비는 지우지 말고 불용일을 넣습니다 (실적이 있는 장비는 지워지지 않음).
"""
import html

import pandas as pd
import streamlit as st

from core import db, seed
from core.terms import w
from ui_style import page_header
from views.common import (center_pick, excel_box, merge_edits, pin_table, unpin, confirm_delete, delete_config, filtered_editor, search_box, split_deleted,
                          with_delete_column)

KPI_COL = w("가동률 산정")
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
BASIC = [TREE, "장비명(한글)", "대분류", "주장비(종)", PARENT, "ITUBE번호", "장비구분", "대수", "관리자", "장비위치",
         "장비용도"]
ALL = ([TREE, "장비명(한글)", "대분류", "주장비(종)", PARENT]
       + [c for c in COLS.values() if c not in ("id", "대분류", "주장비(종)", "장비명(한글)", "불용일")])

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
    page_header("장비", "기준 정보")
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

    xl_heads = {"parent_id": "소속 장비 ID"} | {k: v for k, v in COLS.items()
                                               if k not in ("id", "retired_on", "in_kpi")}

    def _apply_xl(m):
        bad = [e for e in db.save_equipment(m)]
        return bad

    with st.container(horizontal=True, vertical_alignment="center"):
        center = center_pick("equip_center")
        excel_box("equip_xl", eq, xl_heads, "장비", _apply_xl)
    c1, c3, c4 = st.columns([3, 1, 1], vertical_alignment="center")
    with c1:
        q = search_box("equip_q", "장비명·ITUBE번호·관리자·자산번호")
    groups = [g for g in dict.fromkeys(eq["group"]) if g]
    pick = st.pills("대분류", groups, selection_mode="multi", key="equip_groups", label_visibility="collapsed")
    only_top = c3.toggle("장비만", key="equip_only_top", help="세부장비를 접고 장비만 봅니다.")
    all_cols = c4.toggle("모든 열", key="equip_all_cols", help="제조사·구매처·자산번호·도입일 같은 열까지 봅니다.")

    view, newer = pin_table("equip_editor_", view)
    mask = pd.Series(True, index=view.index)
    if q:
        hay = view[["장비명(한글)", "ITUBE번호", "관리자", "자산번호", "주장비(종)", "모델명"]].astype(str).agg(" ".join, axis=1)
        mask &= hay.str.contains(q, case=False, regex=False)
    if pick:
        mask &= view["대분류"].isin(pick)
    if only_top:
        mask &= view[TREE] == "■"
    if center:
        cen = db.equip_centers(eq)
        mask &= pd.to_numeric(view["id"], errors="coerce").map(cen).eq(center)
    filtered = bool(q or pick or only_top or center)

    kinds = list(dict.fromkeys(seed.EQUIP_KINDS_ALL + [k for k in eq["kind"] if k]))
    cats = list(dict.fromkeys(["단독장비", "시스템장비", "시스템시설", "단독장비(복수구매)"] + [c for c in eq["category"] if c]))
    uses = list(dict.fromkeys(list(seed.PURPOSES) + ["제조"] + [u for u in eq["use"] if u]))
    edited, shown = filtered_editor(
        with_delete_column(view), mask if filtered else None,
        key=f"equip_editor_{q}_{pick}_{only_top}", num_rows="dynamic", hide_index=True, width="stretch",
        height=min(680, 38 + 35 * (int(mask.sum()) + 2)),
        column_order=(ALL if all_cols else BASIC) + ["삭제"],
        column_config=delete_config() | {
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
        },
    )
    st.caption((f"{shown}개 표시 · " if filtered else "") + "셀을 끌어 선택하고 Ctrl+C / Ctrl+V 로 엑셀처럼 복사할 수 있어요. "
               "머리글을 누르면 정렬됩니다.")

    edited, deleted = split_deleted(edited, "장비명(한글)")
    ok = confirm_delete(deleted, "equip_editor_del", "대")
    if st.button("변경 내용 저장", type="primary", disabled=not ok, icon=":material/save:"):
        if newer is not None:  # 그사이 다른 분이 저장함 → 내가 바꾼 줄만 얹기
            edited = merge_edits(view, edited, newer)
        unpin("equip_editor_")
        id_of = {v: k for k, v in label_of.items()}
        out = edited.drop(columns=[TREE]).rename(columns={v: k for k, v in COLS.items()})
        out["parent_id"] = [id_of.get(p) if isinstance(p, str) and p else None for p in edited[PARENT].replace(NO_PARENT, "")]
        out = out.drop(columns=[PARENT])
        errors = db.save_equipment(out)
        for e in errors:
            st.warning(e)
        if not errors:
            st.session_state.equip_saved = "장비 목록을 저장했어요." + (f" ({len(deleted)}대 삭제)" if deleted else "")
            for k in [k for k in st.session_state if str(k).startswith("equip_editor_")]:
                st.session_state.pop(k, None)
            st.rerun()
