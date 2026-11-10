"""장비 한 대의 가동 현황: 기본 정보, 기간 지표, 월별 추이, 주요 업체, 실적 목록."""
import datetime as dt
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db
from core.terms import w
from ui_style import CHART_CONFIG, T, chart_layout, nice_step, empty_state, page_header, section_bar
from views.common import period_picker

CFG = CHART_CONFIG


def _info(r: dict, annual: float, parent: str = "", kids: list[str] | None = None) -> None:
    items = [("대분류", r.get("group", "")), ("주장비(종)", r.get("species", "")), ("소속 장비", parent),
             ("센터", r["location"]), ("장비용도", r["use"]), ("장비구분", r["kind"]), ("모델명", r["model"]),
             ("ITUBE번호", r["code"]), ("국가연구시설장비번호", r["nfec"]), ("관리자", r["manager"]),
             ("연간기준시간", f"{(r['annual_hours'] if pd.notna(r['annual_hours']) else annual):,.0f} h"),
             ("제조사", r.get("maker", "")), ("자산번호", r.get("asset_no", "")),
             (w("가동률 산정"), "대상" if r["in_kpi"] else "제외")]
    if kids:
        items.append((f"세부장비 {len(kids)}", ", ".join(kids)))
    cells = "".join(f"<div><span>{html.escape(k)}</span><b title='{html.escape(str(v))}'>{html.escape(str(v) or '-')}</b></div>"
                    for k, v in items if str(v).strip())
    st.markdown(f"<div class='eq-info'>{cells}</div>", unsafe_allow_html=True)


def _sub_breakdown(eq: pd.DataFrame, family: list[int], daily: pd.DataFrame, s, e, annual: float,
                   target: float, top: int) -> None:
    """세부장비별 가동률 + 위 장비 합계. 세부장비 시간은 위 장비에 더해집니다."""
    fam = eq[eq["id"].isin(family)]  # 장비 목록 순서 = 위 장비 바로 아래 세부장비
    sm = calc.equipment_summary(daily, fam, s, e, annual, eq).set_index("equip_id")
    base = int(fam.loc[fam["id"] == top, "depth"].iloc[0])
    top_used = float(sm.at[top, "사용시간"]) if top in sm.index else 0.0
    rows = []
    for r in fam.itertuples(index=False):
        i = int(r.id)
        u = float(sm.at[i, "사용시간"]) if i in sm.index else 0.0
        a = float(sm.at[i, "가용시간"]) if i in sm.index else 0.0
        util = u / a * 100 if a else 0.0
        d = int(r.depth) - base
        share = u / top_used * 100 if top_used else 0.0
        cls = "top" if i == top else ("leaf" if r.leaf else "mid")
        hit = " hit" if target and util >= target else ""
        name = html.escape(r.name if i == top else r.short)
        note = "합계" if i == top else (f"{share:.0f}%" if top_used else "")
        rows.append(
            f"<div class='sb-r {cls}' style='--d:{d}'><div class='sb-n'>{'' if i == top else '<i></i>'}{name}</div>"
            f"<div class='sb-bar'><b class='{hit}' style='width:{min(util, 100):.1f}%'></b></div>"
            f"<div class='sb-v'>{util:.1f}%</div><div class='sb-h'>{u:,.0f} h</div>"
            f"<div class='sb-s'>{note}</div></div>")
    win = calc.window(daily, s, e)
    own = float(win.loc[win["equip_id"].isin(fam.loc[~fam["leaf"], "id"]), "hours"].sum())
    if own > 0:  # 세부장비가 생기기 전에 위 장비에 바로 넣은 실적
        rows.append(f"<div class='sb-r leaf' style='--d:1'><div class='sb-n'><i></i>(위 장비에 바로 입력)</div>"
                    f"<div class='sb-bar'></div><div class='sb-v'></div><div class='sb-h'>{own:,.0f} h</div>"
                    f"<div class='sb-s'>{own / top_used * 100 if top_used else 0:.0f}%</div></div>")
    section_bar(w("세부장비별 가동률"), sub="세부장비 사용시간은 위 장비에 더해집니다 · 오른쪽 %는 합계 중 차지하는 몫")
    head = ("<div class='sb-r sb-head'><div class='sb-n'>장비</div><div class='sb-bar'></div>"
            f"<div class='sb-v'>{html.escape(w('가동률'))}</div><div class='sb-h'>사용시간</div><div class='sb-s'>몫</div></div>")
    st.markdown(f"<div class='sb'>{head}{''.join(rows)}</div>", unsafe_allow_html=True)


def render() -> None:
    st.markdown("""<style>
    .eq-info {display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: .5rem .9rem;
      background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: .8rem 1rem; margin: .2rem 0 1rem;}
    .eq-info div {display: flex; flex-direction: column; gap: .1rem; min-width: 0;}
    .eq-info span {font-size: .75rem; color: var(--muted);}
    .eq-info b {font-size: .92rem; font-weight: 600; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
    .sb {background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: .5rem .9rem; margin-bottom: .6rem;}
    .sb-r {display: grid; grid-template-columns: minmax(150px, 1.6fr) minmax(90px, 2fr) 64px 76px 48px; gap: .7rem;
      align-items: center; padding: .42rem 0; border-bottom: 1px dashed var(--line); font-size: .88rem;}
    .sb-r:last-child {border-bottom: none;}
    .sb-head {font-size: .72rem; color: var(--muted); padding: .2rem 0 .35rem;}
    .sb-n {padding-left: calc(var(--d, 0) * 18px - 18px); min-width: 0; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; color: var(--ink); display: flex; align-items: center; gap: 6px;}
    .sb-r.top .sb-n {padding-left: 0; font-weight: 800;}
    .sb-r.mid .sb-n {font-weight: 700;}
    .sb-n i {flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--accent);
      opacity: .35;}
    .sb-r.leaf .sb-n i {opacity: .8; background: var(--accent-hi);}
    .sb-bar {height: 9px; border-radius: 999px; background: var(--accent-bg); overflow: hidden;}
    .sb-head .sb-bar {background: none;}
    .sb-bar b {display: block; height: 100%; border-radius: 999px; background: color-mix(in srgb, var(--accent) 55%, #fff);}
    .sb-r.top .sb-bar b {background: var(--accent);}
    .sb-bar b.hit {background: var(--accent);}
    .sb-v {text-align: right; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums;}
    .sb-h, .sb-s {text-align: right; color: var(--muted); font-size: .8rem; font-variant-numeric: tabular-nums;}
    @media (max-width: 640px) {.sb-r {grid-template-columns: minmax(110px, 1.4fr) 1fr 56px; } .sb-h, .sb-s {display: none;}}
    </style>""", unsafe_allow_html=True)
    cfg = db.get_settings()
    eq = db.load_equipment()
    logs_all = db.load_logs()
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    if eq.empty:
        empty_state("등록된 장비가 없습니다", "'기준 정보 › 장비'에서 먼저 장비를 추가하세요.")
        return

    top_ids = set(eq.loc[eq["parent_id"].isna(), "id"].astype(int)) if "parent_id" in eq else set()
    ids = [i for i in eq["id"].astype(int) if not top_ids or i in top_ids]  # 주장비만 고름 (세부장비는 아래 표로)
    label_of = dict(zip(eq["id"].astype(int), eq["label"]))
    want = st.session_state.pop("detail_equip", None)
    if want in label_of:  # 세부장비로 들어오면 그 주장비를 보여 줌
        fam = db.descendants(eq)
        st.session_state.detail_sel = next((t for t in ids if int(want) in fam.get(t, [t])), int(want))
    if st.session_state.get("detail_sel") not in ids:
        st.session_state.detail_sel = ids[0]
    years = sorted({d.year for d in logs_all["start_date"].dropna()}) if not logs_all.empty else []
    h1, h2 = st.columns([1, 1.5], vertical_alignment="bottom")
    with h1:
        page_header("장비별 가동률", "현황")
    with h2:
        s, e, label, kind = period_picker("detail", calc.PERIOD_KINDS, "연", years=years)
    eid = st.selectbox("장비", ids, format_func=label_of.get, key="detail_sel", label_visibility="collapsed",
                       placeholder="장비 검색")
    r = eq[eq["id"] == eid].iloc[0].to_dict()
    pid = r.get("parent_id")
    parent = label_of.get(int(pid), "") if pid is not None and pd.notna(pid) else ""
    kids = list(eq.loc[eq["parent_id"] == eid, "name"]) if "parent_id" in eq else []
    _info(r, annual, parent, kids)

    cutoff = dt.date.today()
    e_eff = calc.effective_end(s, e, cutoff)
    one = eq[eq["id"] == eid]
    family = db.descendants(eq).get(int(eid), [int(eid)])  # 세부장비 실적도 함께
    logs = logs_all[logs_all["equip_id"].isin(family)]
    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"), db.charger_caps())
    sm = calc.equipment_summary(daily, one, s, e_eff, annual, eq)
    row = sm.iloc[0] if not sm.empty else None
    ps, pe, plabel = calc.compare_period(kind, s, e, e_eff, "직전")
    pv = calc.equipment_summary(daily, one, ps, pe, annual, eq)
    prev_util = float(pv.iloc[0]["가동률"] or 0) if not pv.empty else 0.0

    section_bar(label, sub=(f"{e_eff:%m/%d}까지 집계 · " if e_eff < e else "") + f"비교: {plabel}", first=True)
    m = st.columns(5)
    util = float(row["가동률"] or 0) if row is not None else 0.0
    m[0].metric(w("가동률"), f"{util:.1f}%", f"{util - prev_util:+.1f}%p")
    m[1].metric("사용시간", f"{(row['사용시간'] if row is not None else 0):,.0f} h",
                help=f"가용시간 {(row['가용시간'] if row is not None else 0):,.0f} h")
    m[2].metric("수수료", f"{(row['사용료'] if row is not None else 0) / 10000:,.0f} 만원")
    m[3].metric("실적", f"{(row['건수'] if row is not None else 0):,} 건")
    past = logs[logs["start_date"] <= pd.Timestamp(cutoff)]
    last = past["end_date"].max() if not past.empty else None
    m[4].metric("최근 사용일", f"{last:%Y-%m-%d}" if last is not None and pd.notna(last) else "기록 없음")

    if len(family) > 1:
        _sub_breakdown(eq, family, daily, s, e_eff, annual, target, int(eid))

    # 월별 추이 (최근 12개월)
    section_bar("월별 추이", sub="최근 12개월")
    tr = calc.trend(daily, one, "월", e_eff, 12, annual, cutoff, eq)
    if not tr.empty:
        fig = go.Figure()
        fig.add_bar(x=tr["기간"], y=tr["사용시간"], name="사용시간(h)", marker_color=T["accent"], opacity=0.9,
                    hovertemplate="%{x}<br>%{y:,.0f} h<extra></extra>")
        fig.add_scatter(x=tr["기간"], y=tr["가동률"], name=w("가동률(%)"), yaxis="y2", mode="lines+markers",
                        line=dict(color=T["warn"], width=2.5), hovertemplate=w("%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        if target:
            fig.add_scatter(x=tr["기간"], y=[target] * len(tr), name=f"목표 {target:.0f}%", yaxis="y2", mode="lines",
                            line=dict(color=T["warn"], width=1, dash="dot"), hoverinfo="skip")
        top = max([target] + [v for v in tr["가동률"] if pd.notna(v)] + [10]) * 1.15
        fig.update_layout(xaxis=dict(type="category"), yaxis=dict(title="사용시간(h)", rangemode="tozero"),
                          yaxis2=dict(title=w("가동률(%)"), overlaying="y", side="right", range=[0, top],
                                      tickmode="linear", tick0=0, dtick=nice_step(top), ticksuffix="%",
                                      showgrid=False))
        st.plotly_chart(chart_layout(fig, 300), width="stretch", config=CFG)

    c1, c2 = st.columns([1, 1.6])
    with c1:
        section_bar("주요 업체")
        b = calc.breakdown(daily, logs, s, e_eff, "company").head(8)
        if b.empty:
            st.caption("이 기간에 실적이 없습니다.")
        else:
            b = b.iloc[::-1]
            fig = go.Figure(go.Bar(x=b["사용시간"], y=b["company"], orientation="h", marker_color=T["accent"],
                                   hovertemplate="%{y}<br>%{x:,.0f} h<extra></extra>"))
            chart_layout(fig, max(180, 32 * len(b) + 60), legend=False).update_layout(bargap=0.45)
            st.plotly_chart(fig, width="stretch", config=CFG)
    with c2:
        section_bar("이 기간 실적", sub="최근 순")
        rows = logs[(logs["start_date"] <= pd.Timestamp(e_eff)) & (logs["end_date"] >= pd.Timestamp(s))]
        if rows.empty:
            st.caption("이 기간에 실적이 없습니다.")
        else:
            st.dataframe(rows[["start_date", "end_date", "company", "purpose", "hours", "fee", "created_by"]].rename(
                columns={"start_date": "시작일", "end_date": "종료일", "company": "업체", "purpose": "목적",
                         "hours": "시간(h)", "fee": "수수료", "created_by": "담당자"}),
                hide_index=True, width="stretch", height=min(420, 38 + 35 * len(rows)),
                column_config={"시작일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                               "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                               "수수료": st.column_config.NumberColumn(format="%d")})
