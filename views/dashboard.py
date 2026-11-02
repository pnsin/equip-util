import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db
from ui_style import T, chart_layout, empty_state, goal_bar, page_header, section_bar
from views.common import period_picker
from core.terms import w

BLUE = T["accent-hi"]
BAR = T["accent"]
ORANGE = T["warn"]
GRAY = T["bar-off"]
CFG = {"displayModeBar": False}


def _nice_step(top: float) -> float:
    """보조축 눈금 간격: 4~6칸이 되도록 5·10·20·25… 중에서."""
    for step in (2, 5, 10, 20, 25, 50):
        if top / step <= 6:
            return step
    return 100


def _equip_chart(shown: pd.DataFrame, target: float) -> None:
    colors = [BLUE if (v or 0) >= target else GRAY for v in shown["가동률"]]
    names = [f"{n} ({c})" if c else n for n, c in zip(shown["장비명"], shown["장비번호"])]
    fig = go.Figure(go.Bar(
        x=shown["가동률"], y=names, orientation="h", marker_color=colors,
        customdata=shown[["사용시간", "가용시간"]].values,
        hovertemplate=w("%{y}<br>가동률 %{x:.1f}%<br>사용 %{customdata[0]:,.0f}h / 가용 %{customdata[1]:,.0f}h<extra></extra>"),
        text=[f"{v:.1f}%" if pd.notna(v) else "" for v in shown["가동률"]], textposition="outside"))
    if target:
        fig.add_vline(x=target, line_dash="dot", line_color=ORANGE,
                      annotation_text=f"목표 {target:.0f}%", annotation_position="top",
                      annotation_font_color=ORANGE)
    fig.update_layout(xaxis=dict(title=w("가동률(%)")))
    chart_layout(fig, max(320, 26 * len(shown) + 80), legend=False).update_layout(margin_t=34, bargap=0.35)
    st.plotly_chart(fig, width="stretch", config=CFG)


def render() -> None:
    page_header("대시보드", "현황")
    cfg = db.get_settings()
    logs = db.load_logs()
    eq = db.load_equipment()
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    years = sorted({d.year for d in logs["start_date"].dropna()}) if not logs.empty else []

    def _toggle():
        st.toggle("진행 중 기간은 오늘까지로 계산", value=True, key="dash_to_today",
                  help="끄면 아직 끝나지 않은 기간도 전체 기간의 가용시간으로 나눕니다.")

    s, e, label, kind = period_picker("dash", calc.PERIOD_KINDS, "월", years=years, extra=_toggle)
    to_today = st.session_state.get("dash_to_today", True)
    cutoff = dt.date.today() if to_today else None

    if logs.empty:
        empty_state("아직 사용실적이 없습니다", "'실적 입력'에서 입력하거나 '가져오기 · 백업'에서 기존 엑셀을 가져오세요.", "◷")

    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"))
    e_eff = calc.effective_end(s, e, cutoff)
    summary = calc.equipment_summary(daily, eq, s, e_eff, annual)
    tot = calc.totals(summary)

    ps, pe, plabel = calc.period_bounds(kind if kind in calc.PERIOD_KINDS else "월", s - dt.timedelta(days=1))
    pe_eff = calc.same_progress_end(s, e_eff, e, ps, pe)
    if pe_eff < pe:  # 진행 중인 기간은 직전 기간도 같은 날짜만큼만 잘라 비교 (11/2까지 ↔ 8/2까지)
        plabel = f"{plabel} 같은 기간({ps:%m/%d}~{pe_eff:%m/%d})"
    prev = calc.totals(calc.equipment_summary(daily, eq, ps, pe_eff, annual))
    win = calc.window(daily, s, e_eff)
    companies = logs[logs["id"].isin(win["log_id"].unique()) & (logs["company"] != "")]["company"].nunique()

    section_bar(label, sub=(f"{e_eff:%m/%d}까지 집계 · " if e_eff < e else "") + f"비교: {plabel}", first=True)
    m = st.columns(5)
    m[0].metric(w("가동률"), f"{tot['util']:.1f}%", f"{tot['util'] - prev['util']:+.1f}%p",
                help=w(f"가동률 산정 대상 장비의 사용시간 합 ÷ 가용시간 합. 아래 숫자는 직전 기간({plabel})과의 차이입니다."))
    m[1].metric("사용시간", f"{tot['used']:,.0f} h", f"{tot['used'] - prev['used']:+,.0f} h")
    m[2].metric("사용료", f"{tot['fee'] / 10000:,.0f} 만원", f"{(tot['fee'] - prev['fee']) / 10000:+,.0f} 만원")
    m[3].metric("지원 업체", f"{companies:,} 곳", help="이 기간에 장비를 쓴 업체 수")
    m[4].metric("미사용 장비", f"{tot['idle_count']} / {tot['equip_count']} 대",
                help=w("이 기간에 사용 기록이 하나도 없는 가동률 산정 대상 장비 수"))
    if target and tot["avail"]:
        need = max(0.0, target / 100 * tot["avail"] - tot["used"])
        ratio = tot["util"] / target
        goal_bar(ratio, w(f"목표 가동률 <b>{target:.0f}%</b> 대비 <b>{ratio * 100:.0f}%</b> 달성"),
                 f"목표까지 <b>{need:,.0f} h</b> 더 필요" if need > 0 else "<b>목표 달성</b>")

    # 추이
    section_bar("기간별 추이", sub=f"최근 {calc.TREND_COUNT.get(kind, 12)}개 {kind}")
    tr = calc.trend(daily, eq, kind, s, calc.TREND_COUNT.get(kind, 12), annual, cutoff)
    if not tr.empty:
        fig = go.Figure()
        fig.add_bar(x=tr["기간"], y=tr["사용시간"], name="사용시간(h)", marker_color=BAR, opacity=0.9,
                    hovertemplate="%{x}<br>사용시간 %{y:,.0f} h<extra></extra>")
        fig.add_scatter(x=tr["기간"], y=tr["가동률"], name=w("가동률(%)"), yaxis="y2", mode="lines+markers",
                        line=dict(color=ORANGE, width=2.5), hovertemplate=w("%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        if target:
            fig.add_scatter(x=tr["기간"], y=[target] * len(tr), name=f"목표 {target:.0f}%", yaxis="y2",
                            mode="lines", line=dict(color=ORANGE, width=1, dash="dot"), hoverinfo="skip")
        top = max([target] + [v for v in tr["가동률"] if pd.notna(v)] + [10]) * 1.15
        step = _nice_step(top)
        fig.update_layout(xaxis=dict(type="category"),
                          yaxis=dict(title="사용시간(h)", rangemode="tozero"),
                          yaxis2=dict(title=w("가동률(%)"), overlaying="y", side="right", range=[0, top],
                                      tickmode="linear", tick0=0, dtick=step, ticksuffix="%",
                                      showgrid=False, tickfont=dict(color=T["muted"]),
                                      title_font=dict(color=T["muted"], size=12)))
        st.plotly_chart(chart_layout(fig, 340), width="stretch", config=CFG)

    # 장비별
    hc1, hc2 = st.columns([3, 1.4], vertical_alignment="bottom")
    with hc1:
        section_bar(w("장비별 가동률"), sub=f"파란 막대 = 목표 {target:.0f}% 이상" if target else "")
    if summary.empty:
        empty_state("이 기간에 보유한 장비가 없습니다")
        return
    only_kpi = hc2.toggle(w("가동률 산정 대상만"), value=True)
    sm = summary[summary["KPI"]] if only_kpi else summary
    sm = sm.sort_values("가동률", ascending=True, na_position="first")
    used_sm = sm[sm["사용시간"] > 0]
    shown = used_sm.tail(25) if len(used_sm) > 25 else used_sm
    n_zero = len(sm) - len(used_sm)
    # 마지막 사용일 (공동장비 정보 입력 시스템의 '저활용·유휴 장비' 관리 참고)
    past = logs[logs["start_date"] <= pd.Timestamp(dt.date.today())] if not logs.empty else logs
    last_used = past.groupby("equip_id")["end_date"].max() if not past.empty else pd.Series(dtype="datetime64[ns]")
    sm = sm.assign(최근사용일=sm["equip_id"].map(last_used).dt.date if not last_used.empty else None)
    idle_days = 90
    cut = dt.date.today() - dt.timedelta(days=idle_days)
    idle = sm[[(d is None or pd.isna(d) or d < cut) for d in sm["최근사용일"]]]
    if not idle.empty:
        with st.expander(f"{idle_days}일 넘게 사용 기록이 없는 장비 {len(idle)}대 (저활용·유휴 후보)",
                         icon=":material/warning:"):
            st.caption(w("국가연구시설장비 표준지침은 장비를 활용·저활용·유휴·불용으로 나눠 관리합니다. "
                         "실제로 쓰지 않는 장비라면 '기준 정보 › 장비'에서 불용일을 넣거나 가동률 산정에서 빼는 것을 검토하세요."))
            st.dataframe(idle[["장비명", "장비번호", "담당자", "최근사용일"]].sort_values("최근사용일", na_position="first"),
                         hide_index=True, width="stretch",
                         column_config={"최근사용일": st.column_config.DateColumn(format="YYYY-MM-DD")})
    tab_chart, tab_table = st.tabs(["그래프", "표"])
    with tab_chart:
        if shown.empty:
            empty_state("이 기간에 사용 기록이 있는 장비가 없습니다")
        else:
            _equip_chart(shown, target)
        notes = []
        if len(used_sm) > 25:
            notes.append(f"사용한 장비 {len(used_sm)}대 중 상위 25대")
        if n_zero:
            notes.append(f"사용 기록이 없는 {n_zero}대는 '표' 탭에서 볼 수 있습니다")
        if notes:
            st.caption(" · ".join(notes))
    with tab_table:
        st.dataframe(
            sm.sort_values("가동률", ascending=False).drop(columns=["equip_id"]),
            hide_index=True, width="stretch",
            column_config={
                "가동률": st.column_config.ProgressColumn(w("가동률(%)"), min_value=0, max_value=100, format="%.1f%%"),
                "사용시간": st.column_config.NumberColumn("사용시간(h)", format="%.1f"),
                "가용시간": st.column_config.NumberColumn("가용시간(h)", format="%.1f"),
                "사용료": st.column_config.NumberColumn("사용료(원)", format="%d"),
                "KPI": st.column_config.CheckboxColumn("산정대상"),
                "최근사용일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
        )

    # 목적·유형·기관
    section_bar("사용 구성", sub="사용시간 기준")
    c1, c2, c3 = st.columns(3)
    for col, by, title in ((c1, "purpose", "사용목적별"), (c2, "usage_type", "활용유형별"), (c3, "company", "업체별 상위 10")):
        b = calc.breakdown(daily, logs, s, e_eff, by).head(10)
        with col:
            st.markdown(f"**{title}**")
            if b.empty:
                st.caption("데이터 없음")
                continue
            b = b.iloc[::-1]
            fig = go.Figure(go.Bar(x=b["사용시간"], y=b[by], orientation="h", marker_color=BAR,
                                   hovertemplate="%{y}<br>%{x:,.0f} h<extra></extra>"))
            fig.update_layout(xaxis=dict(title="사용시간(h)"))
            chart_layout(fig, max(160, 34 * len(b) + 70), legend=False).update_layout(bargap=0.45)
            st.plotly_chart(fig, width="stretch", config=CFG)
