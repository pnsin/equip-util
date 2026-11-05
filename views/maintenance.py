"""장비 정보 › 유지보수: 언제 · 누가 · 어떤 장비에 · 어떤 유지보수를 했는지 적는 단순 기록 표.

- 장비는 장비 목록(기준 정보 › 장비)에서 고릅니다. 세부장비는 '세부장비 · 소속 장비' 로 보입니다.
- 셀을 바로 고치고, 끌어 선택해 Ctrl+C / Ctrl+V, Delete, 머리글을 눌러 정렬 (엑셀처럼).
- 맨 아래 빈 줄에 적으면 새 기록이 됩니다.
"""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import db
from ui_style import page_header
from views.common import center_pick, filtered_editor, search_box

COLS = {"id": "id", "date": "날짜", "equip": "장비", "kind": "종류", "content": "내용", "staff": "담당자",
        "cost": "비용(원)", "note": "비고"}
SHOW = ["날짜", "장비", "종류", "내용", "비용(원)", "담당자", "비고"]

CSS = """<style>
.mt-sum {display:flex; flex-wrap:wrap; gap:.5rem; margin:-.2rem 0 1rem;}
.mt-sum .p {display:flex; align-items:baseline; gap:.45rem; padding:.45rem .95rem; border-radius:999px;
  background:var(--panel); border:1px solid var(--line); box-shadow:var(--card-shadow); font-size:.85rem; color:var(--muted);}
.mt-sum .p b {font-size:1.05rem; font-weight:700; color:var(--ink); font-variant-numeric:tabular-nums;}
.mt-sum .p.a {background:var(--accent-bg); border-color:color-mix(in srgb, var(--accent) 25%, transparent);}
.mt-sum .p.a b {color:var(--accent);}
.mt-sum .p.g {background:var(--ok-bg); border-color:color-mix(in srgb, var(--ok) 25%, transparent);}
.mt-sum .p.g b {color:var(--ok);}
</style>"""


def _summary(df: pd.DataFrame) -> None:
    today = dt.date.today()
    dates = [d for d in df["date"] if d]
    month = sum(1 for d in dates if d.year == today.year and d.month == today.month)
    year = sum(1 for d in dates if d.year == today.year)
    cost = int(sum(int(c) for d, c in zip(df["date"], df["cost"]) if d and d.year == today.year and pd.notna(c)))
    pills = [("a", "이번 달", f"{month:,}"), ("g", "올해", f"{year:,}"), ("", "전체", f"{len(df):,}"),
             ("", "올해 비용", f"{cost:,}원")]
    st.markdown("<div class='mt-sum'>" + "".join(
        f"<div class='p {c}'>{html.escape(t)}<b>{n}</b></div>" for c, t, n in pills) + "</div>",
        unsafe_allow_html=True)


def _by_equipment(df: pd.DataFrame, eq: pd.DataFrame, center: str | None) -> None:
    """주장비 아래 세부장비까지 한 줄씩: 마지막 유지보수 · 올해 횟수 · 올해 비용 (빠진 장비가 없게)."""
    year = dt.date.today().year
    if center:
        cen = db.equip_centers(eq)
        eq = eq[eq["id"].astype(int).map(cen).eq(center)]
    last, cnt, cost = {}, {}, {}
    for e, d, c in zip(df["equip_id"], df["date"], df["cost"]):
        if pd.isna(e):
            continue
        e = int(e)
        if d and (e not in last or d > last[e]):
            last[e] = d
        if d and d.year == year:
            cnt[e] = cnt.get(e, 0) + 1
            cost[e] = cost.get(e, 0) + (int(c) if pd.notna(c) else 0)
    ids = eq["id"].astype(int)
    tbl = pd.DataFrame({
        "장비": ["■ " + n if d <= 0 else "　" * (d - 1) + "└ " + n for n, d in zip(eq["name"], eq["depth"])],
        "마지막 유지보수": [last.get(i) for i in ids],
        f"{year}년 횟수": [cnt.get(i, 0) for i in ids],
        f"{year}년 비용(원)": [cost.get(i, 0) for i in ids],
    })
    none = int(sum(1 for i in ids if i not in last))
    st.dataframe(tbl, hide_index=True, width="stretch", height=min(700, 38 + 35 * (len(tbl) + 1)),
                 column_config={"마지막 유지보수": st.column_config.DateColumn(format="YYYY-MM-DD"),
                                f"{year}년 비용(원)": st.column_config.NumberColumn(format="localized")})
    st.caption(f"전체 {len(tbl)}대 · 유지보수 기록이 한 번도 없는 장비 {none}대")


def _clear_editor() -> None:
    for k in [k for k in st.session_state if str(k).startswith("maint_editor")]:
        st.session_state.pop(k, None)


def render() -> None:
    page_header("유지보수", "장비 정보")
    st.markdown(CSS, unsafe_allow_html=True)
    msg = st.session_state.pop("maint_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")

    df = db.load_maint()
    eq = db.load_equipment()
    label_of = dict(zip(eq["id"].astype(int), eq["label"]))
    id_of = {v: k for k, v in label_of.items()}
    _summary(df)

    view = pd.DataFrame({
        "id": df["id"].astype("Int64"),
        "날짜": df["date"],
        "장비": [label_of.get(int(e), r or "") if pd.notna(e) else (r or "") for e, r in zip(df["equip_id"], df["equip_ref"])],
        "종류": df["kind"], "내용": df["content"], "비용(원)": df["cost"], "담당자": df["staff"], "비고": df["note"],
    })
    view = view.astype({c: "string" for c in ("장비", "종류", "내용", "담당자", "비고")})
    view["날짜"] = pd.to_datetime(view["날짜"]).dt.date

    c0, c9 = st.columns([4, 1.2], vertical_alignment="center")
    with c0:
        center = center_pick("maint_center")
    mode = c9.segmented_control("보기", ["기록", "장비별"], default="기록", key="maint_mode",
                                label_visibility="collapsed") or "기록"
    if mode == "장비별":
        _by_equipment(df, eq, center)
        return
    c1, c2 = st.columns([2.2, 3], vertical_alignment="center")
    with c1:
        q = search_box("maint_q", "장비 · 내용 · 담당자")
    kinds = list(dict.fromkeys(db.MAINT_KINDS + [k for k in df["kind"] if k]))
    with c2:
        pick = st.pills("종류", kinds, selection_mode="multi", key="maint_kinds", label_visibility="collapsed")

    mask = pd.Series(True, index=view.index)
    if q:
        hay = view[["장비", "종류", "내용", "담당자", "비고"]].fillna("").astype(str).agg(" ".join, axis=1)
        mask &= hay.str.contains(q, case=False, regex=False)
    if pick:
        mask &= view["종류"].isin(pick)
    if center:
        cen = db.equip_centers(eq)
        mask &= pd.Series([cen.get(int(e)) == center if pd.notna(e) else False for e in df["equip_id"]], index=view.index)
    filtered = bool(q or pick or center)

    staff = db.staff_names(include=list(df["staff"]))
    equip_opts = list(label_of.values()) + sorted({v for v in view["장비"].dropna() if v and v not in id_of})
    edited, shown = filtered_editor(
        view, mask if filtered else None,
        key=f"maint_editor_{q}_{pick}", num_rows="dynamic", hide_index=True, width="stretch",
        height=min(700, 38 + 35 * (int(mask.sum()) + 2)),
        column_order=SHOW,
        column_config={
            "날짜": st.column_config.DateColumn(format="YYYY-MM-DD", default=dt.date.today(), width=110),
            "장비": st.column_config.SelectboxColumn(options=equip_opts, width="medium",
                                                   help="장비 목록에서 고릅니다. 세부장비는 '세부장비 · 소속 장비'로 보여요."),
            "종류": st.column_config.SelectboxColumn(options=kinds, width="small"),
            "내용": st.column_config.TextColumn(width="medium"),
            "비용(원)": st.column_config.NumberColumn(min_value=0, step=1000, format="localized", width="small"),
            "담당자": st.column_config.SelectboxColumn(options=staff, width="small"),
            "비고": st.column_config.TextColumn(width="small"),
        },
    )
    st.caption((f"{shown}건 표시 · " if filtered else "")
               + "맨 아래 빈 줄에 적으면 새 기록이 돼요. 줄 왼쪽을 눌러 고른 뒤 Delete 키로 지울 수 있어요.")

    n_del = len(view) - len(edited.dropna(subset=["id"]))
    if st.button("변경 내용 저장", type="primary", icon=":material/save:"):
        out = edited.rename(columns={v: k for k, v in COLS.items()})
        out["equip_id"] = [id_of.get(e) if isinstance(e, str) else None for e in out["equip"]]
        out["equip_ref"] = out["equip"]
        n = db.save_maint(out.drop(columns=["equip"]))
        st.session_state.maint_saved = f"유지보수 기록 {n}건을 저장했어요." + (f" ({n_del}건 삭제)" if n_del > 0 else "")
        _clear_editor()
        st.rerun()
