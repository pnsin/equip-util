import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db
from views.common import period_picker

BLUE = "#2F6DB5"
ORANGE = "#E07B39"
GRAY = "#B8C0CC"
FONT = dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif")


def _layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), font=FONT,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def render() -> None:
    st.title("📊 장비 가동률 대시보드")
    cfg = db.get_settings()
    logs = db.load_logs()
    eq = db.load_equipment()
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    years = sorted({d.year for d in logs["start_date"].dropna()}) if not logs.empty else []

    c1, c2 = st.columns([3, 1])
    with c1:
        s, e, label, kind = period_picker("dash", calc.PERIOD_KINDS, "월", years=years)
    with c2:
        to_today = st.toggle("진행 중 기간은 오늘까지로 계산", value=True,
                             help="끄면 아직 끝나지 않은 기간도 전체 기간의 가용시간으로 나눕니다.")
    cutoff = dt.date.today() if to_today else None

    if logs.empty:
        st.info("아직 사용실적이 없습니다. '실적 입력'에서 입력하거나, '설정 → 기존 엑셀 실적 가져오기'로 기존 파일을 올리세요.")

    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"))
    e_eff = calc.effective_end(s, e, cutoff)
    summary = calc.equipment_summary(daily, eq, s, e_eff, annual)
    tot = calc.totals(summary)

    ps, pe, plabel = calc.period_bounds(kind if kind in calc.PERIOD_KINDS else "월", s - dt.timedelta(days=1))
    prev = calc.totals(calc.equipment_summary(daily, eq, ps, pe, annual))
    win = calc.window(daily, s, e_eff)
    companies = logs[logs["id"].isin(win["log_id"].unique()) & (logs["company"] != "")]["company"].nunique()

    st.markdown(f"#### {label}" + (f" · {e_eff:%m/%d}까지" if e_eff < e else ""))
    m = st.columns(5)
    m[0].metric("가동률", f"{tot['util']:.1f}%", f"{tot['util'] - prev['util']:+.1f}%p (전기 대비)",
                help=f"KPI 대상 장비 사용시간 합 ÷ 가용시간 합. 목표 {target:.0f}%")
    m[1].metric("사용시간", f"{tot['used']:,.0f} h", f"{tot['used'] - prev['used']:+,.0f} h")
    m[2].metric("사용료", f"{tot['fee'] / 10000:,.0f} 만원", f"{(tot['fee'] - prev['fee']) / 10000:+,.0f} 만원")
    m[3].metric("지원 기관", f"{companies:,} 곳")
    m[4].metric("미사용 장비", f"{tot['idle_count']} / {tot['equip_count']} 대", delta_color="off")
    if target and tot["avail"]:
        need = max(0.0, target / 100 * tot["avail"] - tot["used"])
        st.progress(min(tot["util"] / target, 1.0),
                    text=f"목표 {target:.0f}% 대비 {tot['util'] / target * 100:.0f}% 달성"
                         + (f" · 목표까지 {need:,.0f} h 더 필요" if need > 0 else " · 목표 달성 🎉"))

    # 추이
    st.markdown("##### 기간별 추이")
    tr = calc.trend(daily, eq, kind, s, calc.TREND_COUNT.get(kind, 12), annual, cutoff)
    if not tr.empty:
        fig = go.Figure()
        fig.add_bar(x=tr["기간"], y=tr["사용시간"], name="사용시간(h)", marker_color=BLUE, opacity=0.85,
                    hovertemplate="%{x}<br>사용시간 %{y:,.0f} h<extra></extra>")
        fig.add_scatter(x=tr["기간"], y=tr["가동률"], name="가동률(%)", yaxis="y2", mode="lines+markers",
                        line=dict(color=ORANGE, width=2.5), hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>")
        if target:
            fig.add_scatter(x=tr["기간"], y=[target] * len(tr), name=f"목표 {target:.0f}%", yaxis="y2",
                            mode="lines", line=dict(color=ORANGE, width=1, dash="dot"), hoverinfo="skip")
        fig.update_layout(xaxis=dict(type="category"),
                          yaxis=dict(title="사용시간(h)", gridcolor="rgba(128,128,128,0.15)"),
                          yaxis2=dict(title="가동률(%)", overlaying="y", side="right", rangemode="tozero",
                                      showgrid=False))
        st.plotly_chart(_layout(fig, 340), width="stretch")

    # 장비별
    st.markdown("##### 장비별 가동률")
    if summary.empty:
        st.caption("이 기간에 보유한 장비가 없습니다.")
        return
    only_kpi = st.toggle("가동률 산정 대상 장비만 보기", value=True)
    sm = summary[summary["KPI"]] if only_kpi else summary
    sm = sm.sort_values("가동률", ascending=True, na_position="first")
    shown = sm.tail(25) if len(sm) > 25 else sm
    # 마지막 사용일 (공동장비 관리 시스템의 '저활용·유휴 장비' 관리 참고)
    past = logs[logs["start_date"] <= pd.Timestamp(dt.date.today())] if not logs.empty else logs
    last_used = past.groupby("equip_id")["end_date"].max() if not past.empty else pd.Series(dtype="datetime64[ns]")
    sm = sm.assign(최근사용일=sm["equip_id"].map(last_used).dt.date if not last_used.empty else None)
    idle_days = 90
    cut = dt.date.today() - dt.timedelta(days=idle_days)
    idle = sm[[(d is None or pd.isna(d) or d < cut) for d in sm["최근사용일"]]]
    if not idle.empty:
        with st.expander(f"⚠️ {idle_days}일 넘게 사용 기록이 없는 장비 {len(idle)}대 (저활용·유휴 후보)"):
            st.caption("국가연구시설장비 표준지침은 장비를 활용·저활용·유휴·불용으로 나눠 관리합니다. "
                       "실제로 쓰지 않는 장비라면 '장비 관리'에서 불용일을 넣거나 가동률 산정에서 빼는 것을 검토하세요.")
            st.dataframe(idle[["장비명", "장비번호", "담당자", "최근사용일"]].sort_values("최근사용일", na_position="first"),
                         hide_index=True, width="stretch",
                         column_config={"최근사용일": st.column_config.DateColumn(format="YYYY-MM-DD")})
    tab_chart, tab_table = st.tabs(["그래프", "표"])
    with tab_chart:
        colors = [BLUE if (v or 0) >= target else GRAY for v in shown["가동률"]]
        names = [f"{n} ({c})" if c else n for n, c in zip(shown["장비명"], shown["장비번호"])]
        fig = go.Figure(go.Bar(
            x=shown["가동률"], y=names, orientation="h", marker_color=colors,
            customdata=shown[["사용시간", "가용시간"]].values,
            hovertemplate="%{y}<br>가동률 %{x:.1f}%<br>사용 %{customdata[0]:,.0f}h / 가용 %{customdata[1]:,.0f}h<extra></extra>",
            text=[f"{v:.1f}%" if pd.notna(v) else "" for v in shown["가동률"]], textposition="outside"))
        if target:
            fig.add_vline(x=target, line_dash="dot", line_color=ORANGE,
                          annotation_text=f"목표 {target:.0f}%", annotation_position="top")
        fig.update_layout(xaxis=dict(title="가동률(%)", gridcolor="rgba(128,128,128,0.15)"), showlegend=False)
        st.plotly_chart(_layout(fig, max(320, 26 * len(shown) + 80)), width="stretch")
        if len(sm) > 25:
            st.caption(f"가동률 상위 25대만 표시했습니다. 전체 {len(sm)}대는 '표' 탭에서 보세요.")
    with tab_table:
        st.dataframe(
            sm.sort_values("가동률", ascending=False).drop(columns=["equip_id"]),
            hide_index=True, width="stretch",
            column_config={
                "가동률": st.column_config.ProgressColumn("가동률(%)", min_value=0, max_value=100, format="%.1f%%"),
                "사용시간": st.column_config.NumberColumn("사용시간(h)", format="%.1f"),
                "가용시간": st.column_config.NumberColumn("가용시간(h)", format="%.1f"),
                "사용료": st.column_config.NumberColumn("사용료(원)", format="%d"),
                "KPI": st.column_config.CheckboxColumn("산정대상"),
                "최근사용일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
        )

    # 목적·유형·기관
    st.markdown("##### 사용 구성")
    c1, c2, c3 = st.columns(3)
    for col, by, title in ((c1, "purpose", "사용목적별"), (c2, "usage_type", "활용유형별"), (c3, "company", "기관별 상위 10")):
        b = calc.breakdown(daily, logs, s, e_eff, by).head(10)
        with col:
            st.caption(title)
            if b.empty:
                st.caption("데이터 없음")
                continue
            b = b.iloc[::-1]
            fig = go.Figure(go.Bar(x=b["사용시간"], y=b[by], orientation="h", marker_color=BLUE,
                                   hovertemplate="%{y}<br>%{x:,.0f} h<extra></extra>"))
            fig.update_layout(xaxis=dict(title="사용시간(h)", gridcolor="rgba(128,128,128,0.15)"))
            st.plotly_chart(_layout(fig, max(200, 30 * len(b) + 60)), width="stretch")
