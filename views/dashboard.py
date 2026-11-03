import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db
from core.terms import w
from ui_style import CHART_CONFIG, T, chart_layout, empty_state, goal_bar, nice_step, page_header, section_bar
from views.common import go_equipment, go_records, period_picker

BLUE = T["accent-hi"]
BAR = T["accent"]
ORANGE = T["warn"]
GRAY = T["bar-off"]
CFG = CHART_CONFIG
BASES = {"hours": "사용시간", "fee": "사용료"}


def _picked(event, idx: int = 0):
    """그래프에서 누른 막대의 customdata[idx]."""
    try:
        pts = event.selection.points if event else []
    except AttributeError:
        pts = (event or {}).get("selection", {}).get("points", [])
    for p in pts:
        cd = p.get("customdata")
        if isinstance(cd, dict):  # 여러 값이면 {"0": .., "1": ..} 모양으로 옴
            cd = [cd[k] for k in sorted(cd, key=lambda x: int(x) if str(x).isdigit() else 0)]
        if cd is not None:
            return cd[idx] if isinstance(cd, (list, tuple)) else cd
    return None


def _equip_chart(shown: pd.DataFrame, target: float) -> None:
    colors = [BLUE if (v or 0) >= target else GRAY for v in shown["가동률"]]
    names = [f"{n} ({c})" if c else n for n, c in zip(shown["장비명"], shown["장비번호"])]
    fig = go.Figure(go.Bar(
        x=shown["가동률"], y=names, orientation="h", marker_color=colors,
        customdata=shown[["equip_id", "사용시간", "가용시간"]].values,
        hovertemplate=w("%{y}<br>가동률 %{x:.1f}%<br>사용 %{customdata[1]:,.0f}h / 가용 %{customdata[2]:,.0f}h"
                        "<br>누르면 장비 상세<extra></extra>"),
        text=[f"{v:.1f}%" if pd.notna(v) else "" for v in shown["가동률"]], textposition="outside"))
    if target:
        fig.add_vline(x=target, line_dash="dot", line_color=ORANGE,
                      annotation_text=f"목표 {target:.0f}%", annotation_position="top",
                      annotation_font_color=ORANGE)
    fig.update_layout(xaxis=dict(title=w("가동률(%)")), clickmode="event+select")
    chart_layout(fig, max(320, 26 * len(shown) + 80), legend=False).update_layout(margin_t=34, bargap=0.35)
    ev = st.plotly_chart(fig, width="stretch", config=CFG, on_select="rerun", selection_mode="points",
                         key="dash_equip_chart")
    eid = _picked(ev)
    if eid is not None:
        go_equipment(int(eid))


def _filters(eq: pd.DataFrame) -> pd.DataFrame:
    """센터·용도·구분으로 장비를 좁힙니다 (대시보드 전체에 적용)."""
    opts = {c: sorted(v for v in eq[c].unique() if v) for c in ("location", "use", "kind")}
    c1, c2, c3 = st.columns([2, 1.2, 1.2])
    loc = c1.multiselect("센터", opts["location"], placeholder="전체 센터", key="dash_loc")
    use = c2.multiselect("장비용도", opts["use"], placeholder="전체 용도", key="dash_use")
    kind = c3.multiselect("장비구분", opts["kind"], placeholder="주장비·부장비 모두", key="dash_kind_eq")
    out = eq
    if loc:
        out = out[out["location"].isin(loc)]
    if use:
        out = out[out["use"].isin(use)]
    if kind:
        out = out[out["kind"].isin(kind)]
    return out


def render() -> None:
    page_header("대시보드", "현황")
    cfg = db.get_settings()
    logs_all = db.load_logs()
    eq_all = db.load_equipment()
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    years = sorted({d.year for d in logs_all["start_date"].dropna()}) if not logs_all.empty else []

    def _toggle():
        st.toggle("진행 중 기간은 오늘까지로 계산", value=True, key="dash_to_today",
                  help="끄면 아직 끝나지 않은 기간도 전체 기간의 가용시간으로 나눕니다.")

    default_kind = cfg.get("default_period") if cfg.get("default_period") in calc.PERIOD_KINDS else "월"
    top_n = int(cfg.get("chart_top") or 25)
    s, e, label, kind = period_picker("dash", calc.PERIOD_KINDS, default_kind, years=years, extra=_toggle)
    to_today = st.session_state.get("dash_to_today", True)
    cutoff = dt.date.today() if to_today else None
    eq = _filters(eq_all)
    logs = logs_all[logs_all["equip_id"].isin(eq["id"])] if len(eq) < len(eq_all) else logs_all

    if logs_all.empty:
        empty_state("아직 사용실적이 없습니다", "'실적 입력'에서 입력하거나 '가져오기 · 백업'에서 기존 엑셀을 가져오세요.", "◷")

    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"))
    e_eff = calc.effective_end(s, e, cutoff)
    summary = calc.equipment_summary(daily, eq, s, e_eff, annual)
    tot = calc.totals(summary)

    # ── 핵심 지표 ─────────────────────────────────────────
    hc1, hc2 = st.columns([3, 1.3], vertical_alignment="bottom")
    cmp_mode = hc2.segmented_control("비교 기준", ["직전", "전년"], default="직전", key="dash_cmp",
                                     format_func=lambda v: "직전 기간" if v == "직전" else "전년 같은 기간",
                                     label_visibility="collapsed") or "직전"
    ps, pe, plabel = calc.compare_period(kind, s, e, e_eff, cmp_mode)
    prev = calc.totals(calc.equipment_summary(daily, eq, ps, pe, annual))
    win = calc.window(daily, s, e_eff)
    companies = logs[logs["id"].isin(win["log_id"].unique()) & (logs["company"] != "")]["company"].nunique()
    with hc1:
        section_bar(label, sub=(f"{e_eff:%m/%d}까지 집계 · " if e_eff < e else "") + f"비교: {plabel}", first=True)
    m = st.columns(5)
    m[0].metric(w("가동률"), f"{tot['util']:.1f}%", f"{tot['util'] - prev['util']:+.1f}%p",
                help=w(f"가동률 산정 대상 장비의 사용시간 합 ÷ 가용시간 합. 아래 숫자는 {plabel}과의 차이입니다."))
    m[1].metric("사용시간", f"{tot['used']:,.0f} h", f"{tot['used'] - prev['used']:+,.0f} h")
    m[2].metric("사용료", f"{tot['fee'] / 10000:,.0f} 만원", f"{(tot['fee'] - prev['fee']) / 10000:+,.0f} 만원")
    m[3].metric("지원 업체", f"{companies:,} 곳", help="이 기간에 장비를 쓴 업체 수")
    m[4].metric("미사용 장비", f"{tot['idle_count']} / {tot['equip_count']} 대",
                help=w("이 기간에 사용 기록이 하나도 없는 가동률 산정 대상 장비 수. 목록은 아래 '장비별' 표에 있습니다."))
    if target and tot["avail"]:
        need = max(0.0, target / 100 * tot["avail"] - tot["used"])
        ratio = tot["util"] / target
        goal_bar(ratio, w(f"목표 가동률 <b>{target:.0f}%</b> 대비 <b>{ratio * 100:.0f}%</b> 달성"),
                 f"목표까지 <b>{need:,.0f} h</b> 더 필요" if need > 0 else "<b>목표 달성</b>")

    # ── 추이 ─────────────────────────────────────────────
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
        step = nice_step(top)
        fig.update_layout(xaxis=dict(type="category"),
                          yaxis=dict(title="사용시간(h)", rangemode="tozero"),
                          yaxis2=dict(title=w("가동률(%)"), overlaying="y", side="right", range=[0, top],
                                      tickmode="linear", tick0=0, dtick=step, ticksuffix="%",
                                      showgrid=False, tickfont=dict(color=T["muted"]),
                                      title_font=dict(color=T["muted"], size=12)))
        st.plotly_chart(chart_layout(fig, 340), width="stretch", config=CFG)

    # ── 센터·용도별 ───────────────────────────────────────
    section_bar(w("센터 · 용도별 가동률"), sub="산정 대상 장비 기준")
    c1, c2 = st.columns(2)
    for col, by in ((c1, "센터"), (c2, "용도")):
        g = calc.group_util(summary, by)
        with col:
            st.markdown(f"**{by}별**")
            if g.empty:
                st.caption("데이터 없음")
                continue
            g = g.iloc[::-1]
            fig = go.Figure(go.Bar(
                x=g["가동률"], y=g[by], orientation="h",
                marker_color=[BLUE if (v or 0) >= target else GRAY for v in g["가동률"]],
                customdata=g[["사용시간", "가용시간", "대수"]].values,
                text=[f"{v:.1f}%" if pd.notna(v) else "" for v in g["가동률"]], textposition="outside",
                hovertemplate=w("%{y}<br>가동률 %{x:.1f}% · %{customdata[2]}대<br>"
                                "사용 %{customdata[0]:,.0f}h / 가용 %{customdata[1]:,.0f}h<extra></extra>")))
            if target:
                fig.add_vline(x=target, line_dash="dot", line_color=ORANGE)
            fig.update_layout(xaxis=dict(title=w("가동률(%)")))
            chart_layout(fig, max(180, 40 * len(g) + 70), legend=False).update_layout(bargap=0.4)
            st.plotly_chart(fig, width="stretch", config=CFG, key=f"dash_grp_{by}")

    # ── 장비별 ───────────────────────────────────────────
    hc1, hc2 = st.columns([3, 1.4], vertical_alignment="bottom")
    with hc1:
        section_bar(w("장비별 가동률"), sub="막대를 누르면 장비 상세")
    if summary.empty:
        empty_state("이 기간에 보유한 장비가 없습니다")
        return
    only_kpi = hc2.toggle(w("가동률 산정 대상만"), value=True, key="dash_only_kpi")
    sm = summary[summary["KPI"]] if only_kpi else summary
    sm = sm.sort_values("가동률", ascending=True, na_position="first")
    used_sm = sm[sm["사용시간"] > 0]
    shown = used_sm.tail(top_n) if len(used_sm) > top_n else used_sm
    n_zero = len(sm) - len(used_sm)
    # 마지막 사용일 (공동장비 정보 입력 시스템의 '저활용·유휴 장비' 관리 참고)
    past = logs[logs["start_date"] <= pd.Timestamp(dt.date.today())] if not logs.empty else logs
    last_used = past.groupby("equip_id")["end_date"].max() if not past.empty else pd.Series(dtype="datetime64[ns]")
    sm = sm.assign(최근사용일=sm["equip_id"].map(last_used).dt.date if not last_used.empty else None)
    idle_days = int(cfg.get("idle_days") or 90)
    cut = dt.date.today() - dt.timedelta(days=idle_days)
    idle = sm[[(d is None or pd.isna(d) or d < cut) for d in sm["최근사용일"]]]
    tab_chart, tab_heat, tab_table = st.tabs(["그래프", "월별 색칠표", "표"])
    with tab_chart:
        if shown.empty:
            empty_state("이 기간에 사용 기록이 있는 장비가 없습니다")
        else:
            _equip_chart(shown, target)
        notes = []
        if len(used_sm) > top_n:
            notes.append(f"사용한 장비 {len(used_sm)}대 중 상위 {top_n}대 ('설정'에서 바꿀 수 있음)")
        if n_zero:
            notes.append(f"사용 기록이 없는 {n_zero}대는 '표' 탭에서 볼 수 있습니다")
        if notes:
            st.caption(" · ".join(notes))
    with tab_heat:
        _heatmap(daily, eq[eq["in_kpi"]] if only_kpi else eq, e_eff, annual, cutoff, target)
    with tab_table:
        table = sm.sort_values("가동률", ascending=False)
        ev = st.dataframe(
            table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            key="dash_equip_tbl",
            column_order=["장비명", "장비번호", "센터", "용도", "구분", "담당자", "가동률", "사용시간", "가용시간",
                          "사용료", "건수", "최근사용일", "KPI"],
            column_config={
                "가동률": st.column_config.ProgressColumn(w("가동률(%)"), min_value=0, max_value=100, format="%.1f%%"),
                "사용시간": st.column_config.NumberColumn("사용시간(h)", format="%.1f"),
                "가용시간": st.column_config.NumberColumn("가용시간(h)", format="%.1f"),
                "사용료": st.column_config.NumberColumn("사용료(원)", format="%d"),
                "KPI": st.column_config.CheckboxColumn("산정대상"),
                "최근사용일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
        )
        rows = ev.selection.rows if ev else []
        if rows:
            go_equipment(int(table.iloc[rows[0]]["equip_id"]))
        st.caption("행을 누르면 장비 상세로 갑니다. 표 오른쪽 위 버튼으로 CSV를 내려받을 수 있습니다.")
    if not idle.empty:
        with st.expander(f"{idle_days}일 넘게 사용 기록이 없는 장비 {len(idle)}대 (저활용·유휴 후보)",
                         icon=":material/warning:"):
            st.caption(w("국가연구시설장비 표준지침은 장비를 활용·저활용·유휴·불용으로 나눠 관리합니다. "
                         "실제로 쓰지 않는 장비라면 '기준 정보 › 장비'에서 불용일을 넣거나 가동률 산정에서 빼는 것을 검토하세요."))
            st.dataframe(idle[["장비명", "장비번호", "센터", "담당자", "최근사용일"]].sort_values("최근사용일", na_position="first"),
                         hide_index=True, width="stretch",
                         column_config={"최근사용일": st.column_config.DateColumn(format="YYYY-MM-DD")})

    # ── 사용 구성 ─────────────────────────────────────────
    hc1, hc2 = st.columns([3, 1.3], vertical_alignment="bottom")
    base = hc2.segmented_control("기준", list(BASES), format_func=BASES.get, default="hours", key="dash_base",
                                 label_visibility="collapsed") or "hours"
    col_name = BASES[base]
    unit = "h" if base == "hours" else "원"
    with hc1:
        section_bar("사용 구성", sub=f"{col_name} 기준 · 업체 막대를 누르면 그 업체 실적 목록")
    c1, c2, c3 = st.columns(3)
    for col, by, title in ((c1, "purpose", "사용목적별"), (c2, "usage_type", "활용유형별"), (c3, "company", "업체별 상위 10")):
        b = calc.breakdown(daily, logs, s, e_eff, by)
        b = b.sort_values(col_name, ascending=False).head(10) if not b.empty else b
        with col:
            st.markdown(f"**{title}**")
            if b.empty or b[col_name].sum() <= 0:
                st.caption("데이터 없음")
                continue
            b = b.iloc[::-1]
            fig = go.Figure(go.Bar(x=b[col_name], y=b[by], orientation="h", marker_color=BAR, customdata=b[by],
                                   hovertemplate=f"%{{y}}<br>%{{x:,.0f}} {unit}<extra></extra>"))
            fig.update_layout(xaxis=dict(title=f"{col_name}({unit})"), clickmode="event+select")
            chart_layout(fig, max(160, 34 * len(b) + 70), legend=False).update_layout(bargap=0.45)
            if by == "company":
                ev = st.plotly_chart(fig, width="stretch", config=CFG, on_select="rerun", selection_mode="points",
                                     key="dash_comp_chart")
                name = _picked(ev)
                if name and name != "(미입력)":
                    go_records(company=name, start=s, end=e_eff)
            else:
                st.plotly_chart(fig, width="stretch", config=CFG, key=f"dash_top_{by}")


def _heatmap(daily: pd.DataFrame, eq: pd.DataFrame, end: dt.date, annual: float, cutoff, target: float) -> None:
    mat = calc.monthly_matrix(daily, eq, end, 12, annual, cutoff)
    if mat.empty:
        empty_state("표시할 장비가 없습니다")
        return
    names = dict(zip(eq["id"], eq["name"] + eq["code"].map(lambda c: f" ({c})" if c else "")))
    mat = mat.loc[[i for i in mat.index if i in names]]
    mat = mat.assign(_avg=mat.mean(axis=1)).sort_values("_avg", ascending=True).drop(columns="_avg")
    z = mat.values
    top = max(target * 1.5 if target else 0, 40)
    fig = go.Figure(go.Heatmap(
        z=z, x=list(mat.columns), y=[names[i] for i in mat.index], customdata=[[i] * z.shape[1] for i in mat.index],
        colorscale=[[0, "#F4F6FA"], [0.02, "#DCE6F5"], [0.5, "#7FA6E0"], [1, T["accent"]]], zmin=0, zmax=top,
        xgap=2, ygap=2, colorbar=dict(title=dict(text="%", side="top"), thickness=10, len=0.6),
        hovertemplate=w("%{y}<br>%{x} · 가동률 %{z:.1f}%<extra></extra>")))
    fig.update_layout(xaxis=dict(side="top", showgrid=False, type="category"), yaxis=dict(showgrid=False))
    chart_layout(fig, max(320, 22 * len(mat) + 90), legend=False)
    ev = st.plotly_chart(fig, width="stretch", config=CFG, on_select="rerun", selection_mode="points",
                         key="dash_heat")
    eid = _picked(ev)
    if eid is not None:
        go_equipment(int(eid))
    st.caption(w("최근 12개월 장비별 가동률입니다. 흐린 칸일수록 덜 쓴 달입니다. 칸을 누르면 장비 상세로 갑니다."))
