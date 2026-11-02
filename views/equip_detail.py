"""장비 한 대의 가동 현황: 기본 정보, 기간 지표, 월별 추이, 주요 업체, 실적 목록."""
import datetime as dt
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db
from core.terms import w
from ui_style import CHART_CONFIG, T, chart_layout, nice_step, empty_state, page_header, section_bar
from views.common import go_records, period_picker

CFG = CHART_CONFIG


def _info(r: dict, annual: float) -> None:
    items = [("센터", r["location"]), ("장비용도", r["use"]), ("장비구분", r["kind"]), ("모델명", r["model"]),
             ("ITUBE번호", r["code"]), ("국가연구시설장비번호", r["nfec"]), ("관리자", r["manager"]),
             ("연간기준시간", f"{(r['annual_hours'] if pd.notna(r['annual_hours']) else annual):,.0f} h"),
             (w("가동률 산정"), "대상" if r["in_kpi"] else "제외")]
    cells = "".join(f"<div><span>{html.escape(k)}</span><b>{html.escape(str(v) or '-')}</b></div>"
                    for k, v in items if str(v).strip())
    st.markdown(f"<div class='eq-info'>{cells}</div>", unsafe_allow_html=True)


def render() -> None:
    st.markdown("""<style>
    .eq-info {display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: .5rem .9rem;
      background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: .8rem 1rem; margin: .2rem 0 1rem;}
    .eq-info div {display: flex; flex-direction: column; gap: .1rem; min-width: 0;}
    .eq-info span {font-size: .75rem; color: var(--muted);}
    .eq-info b {font-size: .92rem; font-weight: 600; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
    </style>""", unsafe_allow_html=True)
    page_header("장비 상세", "현황")
    cfg = db.get_settings()
    eq = db.load_equipment()
    logs_all = db.load_logs()
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    if eq.empty:
        empty_state("등록된 장비가 없습니다", "'기준 정보 › 장비'에서 먼저 장비를 추가하세요.")
        return

    ids = list(eq["id"].astype(int))
    label_of = dict(zip(eq["id"].astype(int), eq["label"]))
    want = st.session_state.pop("detail_equip", None)
    if want in label_of:
        st.session_state.detail_sel = int(want)
    st.session_state.setdefault("detail_sel", ids[0])
    eid = st.selectbox("장비", ids, format_func=label_of.get, key="detail_sel", label_visibility="collapsed",
                       placeholder="장비 검색")
    r = eq[eq["id"] == eid].iloc[0].to_dict()
    _info(r, annual)

    years = sorted({d.year for d in logs_all["start_date"].dropna()}) if not logs_all.empty else []
    s, e, label, kind = period_picker("detail", calc.PERIOD_KINDS, "연", years=years)
    cutoff = dt.date.today()
    e_eff = calc.effective_end(s, e, cutoff)
    one = eq[eq["id"] == eid]
    logs = logs_all[logs_all["equip_id"] == eid]
    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"))
    sm = calc.equipment_summary(daily, one, s, e_eff, annual)
    row = sm.iloc[0] if not sm.empty else None
    ps, pe, plabel = calc.compare_period(kind, s, e, e_eff, "직전")
    pv = calc.equipment_summary(daily, one, ps, pe, annual)
    prev_util = float(pv.iloc[0]["가동률"] or 0) if not pv.empty else 0.0

    section_bar(label, sub=(f"{e_eff:%m/%d}까지 집계 · " if e_eff < e else "") + f"비교: {plabel}", first=True)
    m = st.columns(5)
    util = float(row["가동률"] or 0) if row is not None else 0.0
    m[0].metric(w("가동률"), f"{util:.1f}%", f"{util - prev_util:+.1f}%p")
    m[1].metric("사용시간", f"{(row['사용시간'] if row is not None else 0):,.0f} h",
                help=f"가용시간 {(row['가용시간'] if row is not None else 0):,.0f} h")
    m[2].metric("사용료", f"{(row['사용료'] if row is not None else 0) / 10000:,.0f} 만원")
    m[3].metric("실적", f"{(row['건수'] if row is not None else 0):,} 건")
    past = logs[logs["start_date"] <= pd.Timestamp(cutoff)]
    last = past["end_date"].max() if not past.empty else None
    m[4].metric("최근 사용일", f"{last:%Y-%m-%d}" if last is not None and pd.notna(last) else "기록 없음")

    # 월별 추이 (최근 12개월)
    section_bar("월별 추이", sub="최근 12개월")
    tr = calc.trend(daily, one, "월", e_eff, 12, annual, cutoff)
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
        section_bar("주요 업체", sub="사용시간 기준")
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
                         "hours": "시간(h)", "fee": "사용료", "created_by": "담당자"}),
                hide_index=True, width="stretch", height=min(420, 38 + 35 * len(rows)),
                column_config={"시작일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                               "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                               "사용료": st.column_config.NumberColumn(format="%d")})
        if st.button("실적 목록에서 고치기", icon=":material/edit_note:", key="detail_to_records"):
            go_records(equip_label=label_of[eid], start=s, end=e_eff)
