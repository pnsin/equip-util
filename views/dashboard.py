"""대시보드 — 01 가동률 · 02 장비 수수료 · 03 유지보수 실적 (2026-11-05 사용자 시안).

세 구역 모두 같은 모양: 큰 숫자 3칸 → 한 줄 요약 → 월별 막대 → 아래 작은 칸 2~3개.
"""
import datetime as dt
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db, report
from core.terms import w
from ui_style import CHART_CONFIG, T, chart_layout, empty_state, page_header
from views.common import go_records, period_picker

CFG = CHART_CONFIG
E = html.escape
SHORT_OF = {v: k for k, v in db.CENTER_SHORT.items()}  # 센터 전체 이름 → 문백·제조검증·MV
CENTER_ORDER = ["문백", "제조검증", "MV"]
SHORT: dict[int, str] = {}  # 장비 ID → 짧은 이름 (화면 그릴 때 채움)

# 구역 색: (진한 색, 연한 막대, 바탕)
BLUE = ("#5B6CFF", "rgba(85,102,230,0.16)", "rgba(85,102,230,0.16)")
TEAL = ("#1F9D8B", "rgba(85,230,204,0.3)", "rgba(85,230,199,0.16)")
PURPLE = ("#7E5BC2", "rgba(137,85,230,0.3)", "rgba(138,85,230,0.16)")
GOAL = "#D9822B"
AMBER = ("#D9822B", "rgba(230,160,85,0.3)", "rgba(230,160,85,0.16)")

CSS = """<style>
[class*="st-key-dsec_"] {background: var(--panel); border-radius: 24px; box-shadow: 0 4px 16px rgba(30,36,51,.04);
  padding: 24px 28px 22px; margin-bottom: 12px; gap: .55rem; transition: all 0.25s ease; border: 1px solid #52617A;}
[class*="st-key-dsec_"]:hover { transform: translateY(-4px); box-shadow: 0 20px 40px rgba(30,36,51,.08); border-color: #64748B; }
.dh {display: flex; align-items: center; gap: 14px; margin-bottom: 12px;}
.dh .ic {width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  font-size: 21px; font-weight: 700;}
.dh .no {font-size: 14px; font-weight: 700; letter-spacing: .08em; line-height: 1.1;}
.dh .tt {font-size: 21px; font-weight: 700; color: #F8FAFC; line-height: 1.3;}
.dh .per {margin-left: auto; font-size: 14px; color: #E2E8F0; background: #52617A; padding: 5px 12px; border-radius: 99px;}
.dst {border: 1px solid #52617A; border-radius: 20px; padding: 16px 20px; height: 100%; min-height: 134px; transition: all 0.25s ease; background: rgba(85,121,230,0.16);}
.dst:hover {transform: translateY(-2px); box-shadow: 0 8px 24px rgba(30,36,51,.06); border-color: #64748B; background: var(--panel);}
.dst.big {border: 0; background: linear-gradient(135deg, #5B6CFF 0%, #9B6CFF 60%, #D27CE0 100%); box-shadow: 0 8px 22px rgba(91,108,255,.28);}
.dst.big:hover {transform: translateY(-2px); box-shadow: 0 14px 32px rgba(91,108,255,.4);}
.dst .sl {font-size: 16px; color: #E2E8F0; font-weight: 600;}
.dst.big .sl {color: #fff;}
.dst .sv {font-size: 2.05rem; font-weight: 700; letter-spacing: -.02em; margin: 2px 0 6px; color: #F8FAFC;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.dst.big .sv {color: #fff;}
.dst .sv small {font-size: 1rem; margin-left: 3px; font-weight: 600;}
.dst .sv.name {font-size: 1.55rem; padding: 4px 0 3px;}
.dch {font-size: 14px; font-weight: 600; padding: 2px 9px; border-radius: 99px; display: inline-block;}
.dch.g {color: #6EE7B7; background: rgba(85,230,153,0.16);} .dch.r {color: #FF9AAE; background: rgba(230,85,85,0.16);}
.dch.n {color: #E2E8F0; background: #52617A;}
.dst.big .dch {background: rgba(255,255,255,.14); color: #F8FAFC;}
.dst.big .dch.g {color: #9FE3C1;} .dst.big .dch.r {color: #FFD0D8;}
.dlead {border-radius: 12px; padding: 12px 16px; font-size: 15.5px; line-height: 1.6; color: #F8FAFC; margin-top: 12px;}
.dct {font-size: 15px !important; font-weight: 800; color: #F1F5F9 !important; margin: 22px 0 12px; padding-left: 9px;
  border-left: 3px solid #6366F1; line-height: 1.2; letter-spacing: -.01em;}
.dq {display: grid; grid-template-columns: repeat(4, 1fr); gap: 0 16px; margin: -10px 8px 14px;}
.dq div {border-top: 1.5px solid #64748B; text-align: center; font-size: 14px; color: #E2E8F0; padding-top: 6px;}
.dq b {color: #F8FAFC; margin-left: 4px;}
.dbox {border: 1px solid #52617A; border-radius: 16px; padding: 14px 18px; height: 100%;}
.dbox .bh {margin: 0 0 8px; font-size: 16px; font-weight: 700; color: #F8FAFC; display: flex;
  justify-content: space-between;}
.dml {display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) var(--vw, 62px); gap: 10px; align-items: center;
  font-size: 14.5px; margin: 7px 0; color: #F8FAFC;}
.dml span {white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.dml b {text-align: right; white-space: nowrap;}
.dtb {height: 8px; background: #52617A; border-radius: 99px; position: relative;}
.dtb i {position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px;}
.dpills {display: flex; gap: 8px; flex-wrap: wrap;}
.dpills span {font-size: 14.5px; padding: 6px 12px; border-radius: 12px; background: rgba(133,85,230,0.16); color: #F8FAFC;}
.dpills b {margin-left: 5px;}
.drec {display: flex; justify-content: space-between; gap: 10px; font-size: 14.5px; padding: 7px 0;
  border-bottom: 1px dashed #52617A; color: #F8FAFC;}
.drec:last-child {border: 0;}
.drec > span:first-child {white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.drec .tag {font-size: 13px; padding: 2px 8px; border-radius: 99px; margin-right: 6px; font-weight: 600;
  background: rgba(138,85,230,0.16); color: #7E5BC2;}
.dcnt {width: 100%; border-collapse: collapse; font-size: 15.5px; color: #F8FAFC; text-align: center; border: 0 !important;}
.dcnt th, .dcnt td {border: 0 !important; background: transparent !important; white-space: nowrap;}
.dcnt th {font-size: 14px; font-weight: 600; color: #E2E8F0 !important; padding: 9px 8px !important;
  border-bottom: 1.5px solid #64748B !important;}
.dcnt td {padding: 11px 8px !important; border-bottom: 1px solid #52617A !important;}
@media (max-width: 640px) {.dcnt {font-size: 14px;} .dcnt th {font-size: 12.5px;} .dcnt td b {font-size: 17px;}
  .dcnt th, .dcnt td {padding-left: 4px !important; padding-right: 4px !important;}
  .dcnt {table-layout: fixed;} .dcnt th:first-child {width: 40%;}
  .dcnt th, .dcnt td:first-child {white-space: normal; word-break: break-all; font-size: 13px;}}
.dcnt td b {font-size: 19px; font-weight: 700;}
.dcnt tr.sum td {border-bottom: 0 !important; background: rgba(230,160,85,0.14) !important; color: #FBD38D;}
.dcnt tr.sum td:first-child {border-radius: 12px 0 0 12px;} .dcnt tr.sum td:last-child {border-radius: 0 12px 12px 0;}
.dnone {font-size: 14.5px; color: #CBD5E1; padding: 4px 0;}
.dsub {font-size: 13px; font-weight: 600; color: #CBD5E1; margin-left: 10px;}
.drep {width: 100%; border-collapse: collapse; font-size: 15px; color: #F8FAFC; text-align: center; border: 0 !important;
  font-variant-numeric: tabular-nums;}
.drep tr, .drep thead, .drep tbody {border: 0 !important; background: transparent !important;}
.drep th, .drep td {border: 0 !important; background: transparent !important; white-space: nowrap; text-align: center !important;}
.drep th {font-size: 14px; font-weight: 600; color: #E2E8F0 !important; padding: 9px 8px !important;
  border-bottom: 1.5px solid #64748B !important;}
.drep td {padding: 8px 8px !important; border-bottom: 1px solid #52617A !important;}
.drep td:first-child {font-weight: 600;}
.drep td.g {color: #CBD5E1;}
.drep .gl {display: block; font-size: 12px; font-weight: 600; color: #FBD38D;}
.drep td.na {color: #94A3B8;}
.drep td.hit {color: #6EE7B7; font-weight: 700;}
.drep tr.sum td {background: rgba(85,102,230,0.16) !important; font-weight: 700; border-bottom: 0 !important;}
.drep.fee tr.sum td {background: rgba(85,230,204,0.14) !important;}
.drep tr.goal td {color: #FBD38D; font-weight: 600; background: rgba(230,160,85,0.10) !important;}
.drep tr.rate td {font-weight: 700; color: #F8FAFC; border-bottom: 0 !important;}
.drep tr.rate td.hit {color: #6EE7B7;}
.drep tr.sum td:first-child {border-radius: 12px 0 0 12px;}
.drep tr.sum td:last-child {border-radius: 0 12px 12px 0;}
@media (max-width: 640px) {.drep {font-size: 13px; table-layout: fixed;} .drep th {font-size: 12px;}
  .drep th, .drep td {padding-left: 3px !important; padding-right: 3px !important;}
  .drep th:first-child {width: 34%;} .drep td:first-child {white-space: normal; word-break: keep-all; font-size: 12px;}}
</style>"""


# ── 작은 그림 조각 ────────────────────────────────────────────

def _head(no: int, title: str, color: tuple, icon: str, period: str) -> None:
    st.markdown(f'<div class="dh"><div class="ic" style="background:{color[2]};color:{color[0]}">{icon}</div>'
                f'<div><div class="no" style="color:{color[0]}">{no:02d}</div><div class="tt">{E(title)}</div></div>'
                f'<div class="per">{E(period)}</div></div>', unsafe_allow_html=True)


def _chip(text: str, kind: str = "g") -> str:
    return f'<span class="dch {kind}">{E(text)}</span>' if text else ""


def _delta(v: float | None, unit: str, what: str, fmt: str = "{:+,.0f}", up_good: bool = True) -> str:
    """'▲ 5.1%p 지난달보다' 같은 비교 알약."""
    if v is None or pd.isna(v):
        return ""
    if abs(v) < 1e-9:
        c = what[-1]
        josa = "과" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else "와"
        return ""  # 2026-11-10 '같아요' 알약은 칸 크기만 다르게 해서 뺌
    good = (v > 0) == up_good
    arrow = "▲" if v > 0 else "▼"
    return _chip(f"{arrow} {fmt.format(abs(v)).lstrip('+')}{unit} {what}보다", "g" if good else "r")


def _stats(tiles: list[tuple[str, str, str, str, bool]]) -> None:
    """tiles: (제목, 값, 단위, 비교 알약 html, 남색 칸?) × 3."""
    cols = st.columns(3)
    for col, (label, val, unit, chip, big) in zip(cols, tiles):
        name = " name" if not unit and not val.replace(",", "").replace(".", "").isdigit() else ""
        col.markdown(f'<div class="dst{" big" if big else ""}"><div class="sl">{E(label)}</div>'
                     f'<div class="sv{name}" title="{E(val)}">{E(val)}<small>{E(unit)}</small></div>{chip}</div>',
                     unsafe_allow_html=True)


def _lead(text_html: str, color: tuple) -> None:
    st.markdown(f'<div class="dlead" style="background:{color[2]}">{text_html}</div>', unsafe_allow_html=True)


def _bars(values: list, labels: list[str], cur: int | None, color: tuple, fmt, key: str,
          target: float | None = None, top: float | None = None, hover: str = "", custom=None):
    """월별 막대. cur 번째 막대만 진하게, 아직 오지 않은 달은 빈 막대. 선택 이벤트를 돌려줌."""
    real = [v for v in values if v is not None and pd.notna(v)]
    top = top or max(real + [target or 0, 1e-9]) * 1.22
    ys = [(v if v is not None and pd.notna(v) else 0) for v in values]
    colors = [color[0] if i == cur else (color[1] if values[i] is not None else "#52617A") for i in range(len(values))]
    texts = [fmt(v) if v is not None and pd.notna(v) and (v > 0 or i <= (cur if cur is not None else 99)) else ""
             for i, v in enumerate(values)]
    fig = go.Figure(go.Bar(
        x=labels, y=ys, marker=dict(color=colors, cornerradius=6), text=texts, textposition="outside",
        textfont=dict(size=12, color=["#F8FAFC" if i == cur else T["muted"] for i in range(len(values))]),
        customdata=custom if custom is not None else labels, hovertemplate=hover or "%{x}<extra></extra>",
        cliponaxis=False))
    if target:
        fig.add_hline(y=target, line_dash="dash", line_color=GOAL, line_width=1.5,
                      annotation_text=f"목표 {target:.0f}%", annotation_position="top right",
                      annotation_font=dict(color=GOAL, size=12))
    fig.update_layout(bargap=0.42, clickmode="event+select",
                      yaxis=dict(visible=False, range=[0, top], fixedrange=True),
                      xaxis=dict(type="category", showgrid=False, fixedrange=True,
                                 tickfont=dict(size=12, color=T["muted"])))
    chart_layout(fig, 230, legend=False).update_layout(margin=dict(l=8, r=8, t=26, b=8))
    return st.plotly_chart(fig, width="stretch", config=CFG, key=key,
                           **({"on_select": "rerun", "selection_mode": "points"} if custom is not None else {}))


def _mini_list(rows: list[tuple[str, float, str]], color: str, top: float | None = None) -> str:
    """이름 · 가는 막대 · 값 줄들. rows: (이름, 막대값, 표시 글)."""
    if not rows:
        return '<div class="dnone">기록 없음</div>'
    top = top or max([v for _, v, _ in rows] + [1e-9])
    # 값 칸은 가장 긴 값에 맞춰 넓힘 (모든 줄 같은 폭이라 막대가 나란함, 숫자는 한 줄)
    vw = f"max(62px, {max(len(t) for _, _, t in rows) * 0.62 + 0.4:.1f}em)"
    return "".join(f'<div class="dml" style="--vw:{vw}"><span title="{E(n)}">{E(n)}</span><div class="dtb"><i style="width:'
                   f'{max(0.0, min(v / top, 1)) * 100:.1f}%;background:{color}"></i></div><b>{E(t)}</b></div>'
                   for n, v, t in rows)


def _box(col, title: str, body: str, right: str = "", right_color: str = "") -> None:
    r = f'<span style="color:{right_color}">{E(right)}</span>' if right else ""
    col.markdown(f'<div class="dbox"><div class="bh"><span>{E(title)}</span>{r}</div>{body}</div>', unsafe_allow_html=True)


def _man(won: float) -> str:
    """원 → '1,234,000' (원 단위 전체, 단위 글자는 따로)."""
    return f"{round(won):,}"


def _pick(event):
    try:
        pts = event.selection.points if event else []
    except AttributeError:
        pts = (event or {}).get("selection", {}).get("points", [])
    for p in pts:
        if p.get("customdata") is not None:
            return p["customdata"]
    return None


# ── 필터 ─────────────────────────────────────────────────────

def _filters(years: list[int]) -> tuple[int, int | None]:
    """2026-11-10: 센터·용도 필터는 없애고 장비별 가동률과 같은 기간 고르기 (연 / 월)."""
    c0, c1 = st.columns([1, 1.5], vertical_alignment="bottom")
    with c0:
        page_header("장비 종합 현황", "현황")
    with c1:
        s, _, _, kind = period_picker("dash", ["월", "연"], "연", years=years, align="right")
    return s.year, (s.month if kind == "월" else None)


# ── 화면 ─────────────────────────────────────────────────────

def render() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    cfg = db.get_settings()
    logs_all = db.load_logs()
    eq_all = db.load_equipment()
    annual = float(cfg.get("annual_hours") or 2000)
    today = dt.date.today()
    years = sorted({d.year for d in logs_all["start_date"].dropna()} | {today.year}) if not logs_all.empty else [today.year]

    year, pick_m = _filters(years)
    kpi = report.kpi(cfg, year)  # 2026-11-19 설정 › KPI 목표 (연도별)
    target = float(kpi["util_total"] or 0)
    cats = report.equip_cats(eq_all)
    eq, logs = eq_all, logs_all
    SHORT.clear()
    SHORT.update(zip(eq_all["id"].astype(int), eq_all["short"]))  # 같은 이름 장비는 'n호기'로
    if logs_all.empty:
        empty_state("아직 사용실적이 없습니다", "'장비 일정 등록'에서 입력하거나 '가져오기 · 백업'에서 기존 엑셀을 가져오세요.", "◷")

    this_year = year == today.year
    cutoff = today if this_year else None
    ys, ye = dt.date(year, 1, 1), dt.date(year, 12, 31)
    ye_eff = calc.effective_end(ys, ye, cutoff) if this_year else ye
    cm = pick_m or (today.month if this_year else 12)  # '이번 달' (월을 고르면 그 달)
    cq = (cm - 1) // 3 + 1                              # '이번 분기'
    period = f"{year}년 · {today:%m/%d} 기준" if this_year else f"{year}년"
    if pick_m:
        period = f"{year}년 {pick_m}월"
    months = [f"{m}월" for m in range(1, 13)]

    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"), db.charger_caps())
    ref = dt.date(year, 12, 31)
    tr_m = calc.trend(daily, eq, "월", ref, 12, annual, cutoff, eq_all)
    tr_q = calc.trend(daily, eq, "분기", ref, 4, annual, cutoff, eq_all)
    m_of = {r["시작"].month: r for r in tr_m.to_dict("records")} if not tr_m.empty else {}
    q_of = {(r["시작"].month - 1) // 3 + 1: r for r in tr_q.to_dict("records")} if not tr_q.empty else {}

    def summ(s, e):
        return calc.equipment_summary(daily, eq, s, e, annual, eq_all)

    year_sum = summ(ys, ye_eff)
    y_tot = calc.totals(year_sum)
    py_tot = calc.totals(summ(calc.shift_year(ys, -1), calc.shift_year(ye_eff, -1)))

    # 이번 달 · 이번 분기와 그 직전 (진행 중이면 같은 만큼만 잘라 비교)
    def cur_and_prev(kind: str, ref_day: dt.date):
        s, e, _ = calc.period_bounds(kind, ref_day)
        e_eff = calc.effective_end(s, e, cutoff)
        ps, pe, _ = calc.compare_period(kind, s, e, e_eff, "직전")
        cur = summ(s, e_eff)
        return cur, calc.totals(cur), calc.totals(summ(ps, pe))

    m_ref = dt.date(year, cm, 1)
    m_sum, m_tot, pm_tot = cur_and_prev("월", m_ref)
    q_sum, q_tot, pq_tot = cur_and_prev("분기", m_ref)

    _util_section(year, cm, cq, period, target, m_of, q_of, m_tot, pm_tot, q_tot, pq_tot, y_tot, py_tot,
                  (m_sum, q_sum, year_sum), cats, kpi)
    ref_day = min(today, (pd.Timestamp(year, cm, 1) + pd.offsets.MonthEnd(0)).date())  # 주간·월간 표의 기준일
    _fee_section(year, cm, period, months, ref_day, kpi)
    _maint_section(year, cm, period, months, eq, eq_all, len(eq) < len(eq_all), today)
    _count_section(today)


def _count_section(today) -> None:
    """2026-11-19: 장비 종·대수 (센터별 표). 세는 법은 장비 목록 엑셀의 '종·대수 요약'과 같음."""
    from views.equipment import count_summary
    with st.container(key="dsec_count"):
        _head(4, "장비 종·대수", AMBER, "▦", f"{today:%Y-%m-%d} 기준")
        blocks, _ = count_summary(db.load_equipment(full=True))
        df = dict(blocks)["센터별"]
        rows = ""
        for r in df.to_dict("records"):
            name = r["센터"]
            cls = ' class="sum"' if name == "합계" else ""
            rows += (f'<tr{cls}><td>{E(name)}</td><td><b>{r["종"]}</b> 종</td><td><b>{r["대수"]}</b> 대</td>'
                     f'<td>{r["i-Tube 등록"]}</td></tr>')
        st.markdown(f'<table class="dcnt"><thead><tr><th>센터</th><th>종</th><th>대수</th><th>i-Tube 등록</th></tr>'
                    f'</thead><tbody>{rows}</tbody></table>', unsafe_allow_html=True)


def _util_section(year, cm, cq, period, target, m_of, q_of, m_tot, pm_tot, q_tot, pq_tot, y_tot, py_tot,
                  sums, cats, kpi) -> None:
    with st.container(key="dsec_util"):
        _head(1, w("가동률"), BLUE, "%", period)
        _stats([
            (f"{cm}월", f"{m_tot['util']:.1f}", "%",
             _delta(m_tot["util"] - pm_tot["util"], "%p", "지난달", "{:.1f}") if pm_tot["avail"] else "", False),
            (f"{cq}분기", f"{q_tot['util']:.1f}", "%",
             _delta(q_tot["util"] - pq_tot["util"], "%p", f"{cq - 1 if cq > 1 else 4}분기", "{:.1f}")
             if pq_tot["avail"] else "", False),
            (f"{year}년 누적", f"{y_tot['util']:.1f}", "%",
             _delta(y_tot["util"] - py_tot["util"], "%p", "작년", "{:.1f}") if py_tot["avail"] else "", True),
        ])
        # 한 줄 요약
        done = {m: r["가동률"] for m, r in m_of.items() if pd.notna(r["가동률"])}
        parts = [w(f"올해 가동률은 <b>{y_tot['util']:.1f}%</b>")]
        if target:
            parts[0] += f"로 목표 {target:.0f}%의 <b>{y_tot['util'] / target * 100:.0f}%</b>를 채웠어요."
        else:
            parts[0] += "예요."
        if len(done) >= 2 and any(v > 0 for v in done.values()):
            best = max(done, key=done.get)
            rank = sorted(done.values(), reverse=True).index(done.get(cm, -1)) + 1 if cm in done else 0
            if best == cm:
                parts.append(f"{cm}월이 올해 가장 높은 달이에요.")
            elif rank == 2:
                parts.append(f"{cm}월이 올해 두 번째로 높은 달이에요.")
            else:
                parts.append(f"올해 가장 높은 달은 <b>{best}월({done[best]:.1f}%)</b>이에요.")
        if target and y_tot["avail"]:
            need = target / 100 * y_tot["avail"] - y_tot["used"]
            if need > 0:
                parts.append(f"목표를 채우려면 지금까지 기준으로 <b>{need:,.0f}시간</b>을 더 써야 해요.")
        _lead(" ".join(parts), BLUE)

        st.markdown(f'<div class="dct">{E(w("월별 가동률"))}</div>', unsafe_allow_html=True)
        vals = [m_of[m]["가동률"] if m in m_of else None for m in range(1, 13)]
        top = max([v for v in vals if v is not None and pd.notna(v)] + [target, 10]) * 1.25
        _bars(vals, [f"{m}월" for m in range(1, 13)], cm - 1, BLUE, lambda v: f"{v:.1f}%", "dash_util_m",
              target=target or None, top=top, hover=w("%{x} 가동률 %{y:.1f}%<extra></extra>"))
        st.markdown('<div class="dq">' + "".join(
            f'<div>{q}분기<b>{q_of[q]["가동률"]:.1f}%</b></div>' if q in q_of and pd.notna(q_of[q]["가동률"])
            else f'<div>{q}분기<b style="color:#E2E8F0">–</b></div>' for q in range(1, 5)) + '</div>',
            unsafe_allow_html=True)

        # 2026-11-19 주간업무보고와 같은 분류별 표 (예전 '센터별 주장비' 목록 자리)
        st.markdown(f'<div class="dct" style="margin:26px 0 12px">{E(w("분류별 가동률"))}</div>', unsafe_allow_html=True)
        st.markdown(_util_table(sums, cats, kpi, (f"{cm}월", f"{cq}분기", f"{year}년"),
                                (m_tot, q_tot, y_tot)), unsafe_allow_html=True)


def _cat_util(summary: pd.DataFrame, cats: dict[int, str]) -> dict[str, float]:
    """보고 분류 → 가동률(%). 산정 대상(KPI) 장비만, 세부장비 시간은 이미 주장비에 더해져 있음."""
    if summary.empty:
        return {}
    k = summary[summary["KPI"]]
    if k.empty:
        return {}
    g = k.assign(c=[cats.get(int(i), report.OTHER) for i in k["equip_id"]]).groupby("c")[["사용시간", "가용시간"]].sum()
    return {c: r["사용시간"] / r["가용시간"] * 100 for c, r in g.iterrows() if r["가용시간"] > 0}


def _pct(v, goal) -> str:
    if v is None:
        return '<td class="na">–</td>'
    hit = " hit" if goal and v >= goal else ""
    return f'<td class="v{hit}">{v:.1f}%</td>'


def _util_table(sums, cats, kpi, labels, tots) -> str:
    per = [_cat_util(sm, cats) for sm in sums]
    shown = [c for c in report.CATS if c != report.OTHER or any(report.OTHER in p for p in per)]
    head = "".join(f"<th>{E(x)}</th>" for x in ("구분",) + labels)
    goal = float(kpi["util_total"] or 0)  # 목표는 전체 하나 (설정 › KPI 목표)
    rows = (f'<tr class="sum"><td>전체 <span class="gl">목표 {goal:.0f}%</span></td>'
            + "".join(_pct(t["util"] if t["avail"] else None, goal) for t in tots) + "</tr>")
    for c in shown:
        rows += f'<tr><td>{E(c)}</td>' + "".join(_pct(p.get(c), None) for p in per) + "</tr>"
    return f'<table class="drep"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'


def _eok(v: float) -> str:
    """500000000 → '5억 원', 그 밖에는 '123,456,000원'."""
    return f"{v / 1e8:g}억 원" if v and v % 1e7 == 0 else f"{round(v):,}원"


def _won_k(v: float) -> str:
    return f"{round(v / 1000):,}" if v else "–"


def _fee_section(year, cm, period, months, ref_day, kpi) -> None:
    """2026-11-05: 장비 수수료는 재무팀 매출장(세금일자 · 공급가) 기준. 실적별 수수료는 늦게·안 넣는 경우가 많아서.
    2026-11-19: 아래 표는 주간업무보고와 같은 분류별 발행 (주간 · 월간 · 연간, 천 원) + 목표 대비 달성률."""
    from core import fee_ledger
    with st.container(key="dsec_fee"):
        _head(2, "장비 수수료", TEAL, "₩", period)
        fl = fee_ledger.load()
        fl = fl[fl["tax_date"].map(bool)] if not fl.empty else fl
        yr = fl["tax_date"].map(lambda d: d.year) if not fl.empty else pd.Series(dtype=int)
        mo = fl["tax_date"].map(lambda d: d.month) if not fl.empty else pd.Series(dtype=int)
        cur = fl[yr == year] if not fl.empty else fl
        prev = fl[(yr == year - 1) & (mo <= cm)] if not fl.empty else fl  # 작년 같은 기간
        fees = cur.groupby(mo[yr == year])["supply"].sum().to_dict() if not cur.empty else {}
        pm = (year, cm - 1) if cm > 1 else (year - 1, 12)
        pm_fee = fl[(yr == pm[0]) & (mo == pm[1])]["supply"].sum() if not fl.empty else 0
        m_fee, y_fee, py_fee = fees.get(cm, 0), sum(fees.values()), prev["supply"].sum() if not prev.empty else 0
        unpaid = cur["unpaid"].fillna(0) if not cur.empty else pd.Series(dtype=float)
        goal = float(kpi["fee"] or 0)
        _stats([
            (f"{cm}월", _man(m_fee), "원", _delta(m_fee - pm_fee, "원", "지난달"), False),
            (f"{year}년 누적", _man(y_fee), "원",
             _delta((y_fee / py_fee - 1) * 100, "%", "작년") if py_fee else "", True),
            ("미수금 · 올해", _man(unpaid.sum()), "원",
             _chip(f"{int((unpaid > 0).sum())}건 남았어요", "r") if unpaid.sum() > 0 else _chip("모두 받았어요", "g"), False),
        ])
        done = {m: v for m, v in fees.items() if m <= cm}
        if fl.empty:
            _lead("수수료 입력 › 재무팀 매출장에서 엑셀을 올리면 여기에 나와요.", TEAL)
        elif done and sum(done.values()) > 0:
            best = max(done, key=done.get)
            goal_txt = (f"연 목표 {_eok(goal)}의 <b>{y_fee / goal * 100:.1f}%</b>를 채웠어요. " if goal else "")
            _lead(goal_txt + f"한 달 평균 <b>{_man(sum(done.values()) / cm)}원</b>이 발행됐고, "
                  f"{best}월이 <b>{_man(done[best])}원</b>으로 가장 많았어요.", TEAL)
        else:
            _lead("올해는 아직 발행된 수수료가 없어요.", TEAL)

        st.markdown('<div class="dct">월별 수수료 (원, 세금일자 · 공급가 기준)</div>', unsafe_allow_html=True)
        vals = [fees.get(m, 0) if m <= cm or m in fees else None for m in range(1, 13)]
        _bars(vals, months, cm - 1, TEAL, lambda v: f"{v:,.0f}", "dash_fee_m",
              hover="%{x} 수수료 %{y:,.0f}원<extra></extra>", custom=list(range(1, 13)))

        # 분류별 발행 (주간업무보고 'I. 수수료현황'과 같은 모양)
        wk_s = ref_day - dt.timedelta(days=ref_day.weekday())
        wk_e = wk_s + dt.timedelta(days=6)
        st.markdown(f'<div class="dct" style="margin:26px 0 12px">분류별 발행 (천 원)'
                    f'<span class="dsub">주간 {wk_s:%m/%d}~{wk_e:%m/%d}</span></div>', unsafe_allow_html=True)
        st.markdown(_fee_table(cur, year, cm, wk_s, wk_e, ref_day, goal), unsafe_allow_html=True)


def _fee_table(cur: pd.DataFrame, year, cm, wk_s, wk_e, ref_day, goal) -> str:
    if cur.empty:
        d = cur.assign(c=[], w=[], m=[], y=[])
    else:
        d = cur.assign(c=report.ledger_cats(cur),
                       w=[wk_s <= x <= wk_e for x in cur["tax_date"]],
                       m=[x.month == cm for x in cur["tax_date"]],
                       y=[x <= ref_day for x in cur["tax_date"]])
    cols = [("주간", "w", goal / 52), ("월간", "m", goal / 12), ("연간", "y", goal)]
    sums = {k: (d[d[k]].groupby("c")["supply"].sum().to_dict() if len(d) else {}) for _, k, _ in cols}
    head = "".join(f"<th>{x}</th>" for x in ["구분"] + [c for c, _, _ in cols])
    rows = '<tr class="goal"><td>목표</td>' + "".join(f"<td>{_won_k(g)}</td>" for _, _, g in cols) + "</tr>"
    for c in report.CATS:
        rows += f"<tr><td>{E(c)}</td>" + "".join(
            f'<td class="v">{_won_k(sums[k].get(c, 0))}</td>' for _, k, _ in cols) + "</tr>"
    tot = {k: sum(sums[k].values()) for _, k, _ in cols}
    rows += '<tr class="sum"><td>합계</td>' + "".join(f"<td>{_won_k(tot[k]) if tot[k] else 0}</td>" for _, k, _ in cols) + "</tr>"
    rows += '<tr class="rate"><td>달성률</td>' + "".join(
        f'<td class="{"hit" if g and tot[k] >= g else ""}">{tot[k] / g * 100:.1f}%</td>' if g else "<td>–</td>"
        for _, k, g in cols) + "</tr>"
    return f'<table class="drep fee"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'


def _maint_section(year, cm, period, months, eq, eq_all, filtered: bool, today) -> None:
    with st.container(key="dsec_maint"):
        _head(3, "유지보수 실적", PURPLE, "⚙", period)
        df = db.load_maint()
        df = df[df["date"].map(lambda d: bool(d) and d.year == year)] if not df.empty else df
        if filtered and not df.empty:
            df = df[df["equip_id"].isin(set(eq["id"].astype(int)))]
        name = dict(zip(eq_all["id"].astype(int), eq_all["name"]))
        root = dict(zip(eq_all["id"].astype(int), eq_all["root_id"]))
        df = df.assign(m=[d.month for d in df["date"]],
                       eqn=[name.get(int(root.get(int(i), i)), r) if pd.notna(i) else r
                            for i, r in zip(df["equip_id"], df["equip_ref"])]) if not df.empty else df.assign(m=[], eqn=[])
        by_m = df.groupby("m").size().to_dict() if not df.empty else {}
        n_cur, n_prev = by_m.get(cm, 0), by_m.get(cm - 1, 0) if cm > 1 else None
        top_eq = df[df["eqn"] != ""]["eqn"].value_counts() if not df.empty else pd.Series(dtype=int)
        _stats([
            (f"{cm}월", f"{n_cur}", "건",
             _delta(n_cur - n_prev, "건", "지난달", up_good=False) if n_prev is not None else "", False),
            (f"{year}년 누적", f"{len(df)}", "건", "", True),
            ("가장 많은 장비", top_eq.index[0] if len(top_eq) else "–", "",
             _chip(f"올해 {top_eq.iloc[0]}건", "n") if len(top_eq) else "", False),
        ])
        kinds = df[df["kind"] != ""]["kind"].value_counts() if not df.empty else pd.Series(dtype=int)
        if len(df):
            _lead(f"올해 유지보수 <b>{len(df)}건</b>" + (f" 중 <b>{E(kinds.index[0])} {kinds.iloc[0]}건</b>이 가장 많아요."
                                                     if len(kinds) else "을 기록했어요."), PURPLE)
        else:
            _lead("올해는 아직 유지보수 기록이 없어요.", PURPLE)

        st.markdown('<div class="dct">월별 유지보수 건수</div>', unsafe_allow_html=True)
        last = cm if year == today.year else 12
        vals = [by_m.get(m, 0) if m <= last else None for m in range(1, 13)]
        _bars(vals, months, cm - 1, PURPLE, lambda v: f"{v:.0f}건", "dash_maint_m",
              top=max([v or 0 for v in vals] + [3]) * 1.3, hover="%{x} 유지보수 %{y}건<extra></extra>")

        c1, c2 = st.columns(2)
        order = [k for k in db.MAINT_KINDS if k in kinds.index] + [k for k in kinds.index if k not in db.MAINT_KINDS]
        pills = "".join(f"<span>{E(k)}<b>{kinds[k]}</b></span>" for k in order)
        _box(c1, "종류별 · 올해", f'<div class="dpills">{pills}</div>' if pills else '<div class="dnone">기록 없음</div>')
        recent = df.head(4) if not df.empty else df
        rec = "".join(
            f'<div class="drec"><span>{f"<span class=tag>{E(r.kind)}</span>" if r.kind else ""}'
            f'{E(r.eqn)}{" · " + E(r.content) if r.content else ""}</span>'
            f'<span style="color:#E2E8F0;flex:none">{r.date:%m/%d}</span></div>' for r in recent.itertuples())
        _box(c2, "최근 기록", rec or '<div class="dnone">기록 없음</div>')
