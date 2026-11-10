"""장비 정보 › 유지보수: 언제 · 누가 · 어떤 장비에 · 어떤 유지보수를 했는지 적는 단순 기록 표.

- 장비는 장비 목록(기준 정보 › 장비)에서 고릅니다. 세부장비는 '세부장비 · 소속 장비' 로 보입니다.
- 평소엔 표가 잠겨 있고, '선택'한 줄만 아래에서 고쳐 [저장] / [삭제] (2026-11-10).
"""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import db
from ui_style import page_header
from views.common import center_pick, pick_done, pick_table, search_box

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


def render() -> None:
    page_header("유지보수", "장비")
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
        mask &= pd.Series([cen.get(id_of.get(e)) == center for e in view["장비"]], index=view.index)
    filtered = bool(q or pick or center)

    staff = db.staff_names(include=list(df["staff"]))
    equip_opts = list(label_of.values()) + sorted({v for v in view["장비"].dropna() if v and v not in id_of})
    action, out, gone = pick_table(
        view, "maint_tbl", mask=mask if filtered else None, name_col="내용", add_label="기록 추가",
        column_order=SHOW,
        column_config={
            "날짜": st.column_config.DateColumn(format="YYYY-MM-DD", default=dt.date.today(), width=110),
            "장비": st.column_config.SelectboxColumn(options=equip_opts, width="medium"),
            "종류": st.column_config.SelectboxColumn(options=kinds, width="small"),
            "내용": st.column_config.TextColumn(width="large"),
            "비용(원)": st.column_config.NumberColumn(min_value=0, step=1000, format="localized", width="small"),
            "담당자": st.column_config.SelectboxColumn(options=staff, width="small"),
            "비고": st.column_config.TextColumn(width="small"),
        })
    if action:
        o = out.rename(columns={v: k for k, v in COLS.items()})
        o["equip_id"] = [id_of.get(e) if isinstance(e, str) else None for e in o["equip"]]
        o["equip_ref"] = o["equip"]
        db.save_maint(o.drop(columns=["equip"]))
        pick_done("maint_tbl")
        st.session_state.maint_saved = f"{len(gone)}건 삭제했어요." if gone else "저장했어요."
        st.rerun()
