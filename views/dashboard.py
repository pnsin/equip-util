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
from views.common import go_records

CFG = CHART_CONFIG
E = html.escape
SHORT_OF = {v: k for k, v in db.CENTER_SHORT.items()}  # 센터 전체 이름 → 문백·제조검증·MV
CENTER_ORDER = ["문백", "제조검증", "MV"]
SHORT: dict[int, str] = {}  # 장비 ID → 짧은 이름 (화면 그릴 때 채움)

# 구역 색: (진한 색, 연한 막대, 바탕)
# 2026-11-19 리디자인: 01 파랑 · 02 초록 · 03 주황 · 04 보라 (색은 배지 · 막대 · 큰 숫자에만)
BLUE = ("#3B82F6", "rgba(59,130,246,0.35)", "rgba(59,130,246,0.16)")
TEAL = ("#10B981", "rgba(16,185,129,0.35)", "rgba(16,185,129,0.16)")
AMBER = ("#F59E0B", "rgba(245,158,11,0.35)", "rgba(245,158,11,0.16)")
PURPLE = ("#8B5CF6", "rgba(139,92,246,0.35)", "rgba(139,92,246,0.16)")
GOAL = "#F59E0B"

CSS = """<style>
[class*="st-key-dsec_"] {background: var(--panel); border-radius: 20px; padding: 22px 26px 20px; margin-bottom: 14px;
  gap: .55rem; border: 1px solid rgba(255,255,255,0.08);}
.st-key-dsec_util {border-top: 2px solid #3B82F6;} .st-key-dsec_fee {border-top: 2px solid #10B981;}
/* 위 요약 4칸 (2026-11-19 사용자 시안: 가동률·수수료는 좁게, 유지보수·종대수는 넓게) */
.dtop {display: grid; grid-template-columns: .85fr .85fr 1.3fr 1.6fr; gap: 14px; align-items: stretch; margin: 4px 0 16px;}
.dtop .k {background: var(--panel); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 14px 16px 14px;
  text-align: center; display: flex; flex-direction: column; justify-content: center; min-height: 196px;
  font-variant-numeric: tabular-nums;}
.dtop .k.c1 {border-top: 2px solid #3B82F6;} .dtop .k.c2 {border-top: 2px solid #10B981;}
.dtop .k.c3 {border-top: 2px solid #F59E0B;} .dtop .k.c4 {border-top: 2px solid #8B5CF6;}
.dtop .no {font-size: 12px; font-weight: 700; letter-spacing: .08em; text-align: center; margin-bottom: 2px;}
.dtop .tt {font-size: 19px; font-weight: 700; color: #F8FAFC;}
.dtop .big {font-size: 40px; font-weight: 800; letter-spacing: -.02em; line-height: 1.15; margin: 10px 0 8px;}
.dtop .big small {font-size: 30px; font-weight: 800;}
.dtop .sub {font-size: 15px; color: #CBD5E1;} .dtop .sub b {font-weight: 700;}
.dtop .hd {display: flex; align-items: center; gap: 10px; justify-content: center;}
.dtop .hd .bd {width: 32px; height: 32px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 700;}
.dtop .hd .lab {text-align: left;} .dtop .hd .lab .no {margin: 0;}
.dtop .pill {margin-left: auto; font-size: 15px; font-weight: 700; padding: 4px 12px; border-radius: 99px;
  background: rgba(139,92,246,0.16); color: #C4B5FD;}
.dtop .note {font-size: 12.5px; color: #94A3B8; margin-top: 2px;}
.dtop .mm {display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px; margin-top: 12px; font-size: 11.5px;}
.dtop .mm b {display: block; font-weight: 700; color: #E2E8F0;} .dtop .mm b.z {color: #475569;}
.dtop .mm span {color: #94A3B8; font-size: 10.5px;}
.dtop table {width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; border: 0 !important;}
.dtop th, .dtop td {padding: 6px 6px !important; text-align: center !important; border: 0 !important;
  background: transparent !important; white-space: nowrap; color: #E2E8F0;}
.dtop th {color: #94A3B8 !important; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.12) !important;}
.dtop td {border-bottom: 1px solid rgba(255,255,255,0.06) !important;}
.dtop tr, .dtop thead, .dtop tbody {border: 0 !important; background: transparent !important;}
.dtop tr.sum td {background: rgba(245,158,11,0.14) !important; color: #FBD38D; font-weight: 700; border-bottom: 0 !important;}
.dtop tr.sum td:first-child {border-radius: 10px 0 0 10px;} .dtop tr.sum td:last-child {border-radius: 0 10px 10px 0;}
@media (max-width: 1200px) {.dtop {grid-template-columns: 1fr 1fr;}}
@media (max-width: 640px) {.dtop {grid-template-columns: 1fr;} .dtop .k {min-height: 0;}
  .dtop table {font-size: 12px;} .dtop th, .dtop td {padding: 5px 3px !important;}}
.dh {display: flex; align-items: center; gap: 14px; margin-bottom: 12px;}
.dh .ic {width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  font-size: 21px; font-weight: 700;}
.dh .no {font-size: 14px; font-weight: 700; letter-spacing: .08em; line-height: 1.1;}
.dh .tt {font-size: 19px; font-weight: 700; color: #F8FAFC; line-height: 1.3;}
.dper {font-size: 14px; color: #E2E8F0; border: 1px solid #475569; height: 38px; display: flex; align-items: center; padding: 0 16px; border-radius: 99px; white-space: nowrap;}
.st-key-dash_pp > div, .st-key-dash_pp [data-testid="stElementContainer"] {margin: 0 !important;}
.st-key-dash_pp [data-testid="stMarkdownContainer"] p, .st-key-dash_pp [data-testid="stMarkdownContainer"] {margin: 0;}
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
.drep td.na, .drep td.z {color: #475569 !important; font-weight: 400 !important;}
.drep td.hit {color: #6EE7B7; font-weight: 700;}
.drep tr.sum td {background: rgba(59,130,246,0.16) !important; font-weight: 700; font-size: 15px; border-bottom: 0 !important;}
.drep.fee tr.sum td {background: rgba(16,185,129,0.16) !important;}
.drep tr.goal td {color: #FBD38D; font-weight: 700; font-size: 15px; background: rgba(245,158,11,0.10) !important;}
.drep tr.rate td {font-weight: 700; font-size: 15px; color: #F8FAFC; border-bottom: 0 !important;}
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
                '</div>', unsafe_allow_html=True)


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
    colors = [color[0] if values[i] is not None else "#334155" for i in range(len(values))]  # 2026-11-19 모든 달 진하게
    texts = [fmt(v) if v is not None and pd.notna(v) and (v > 0 or i <= (cur if cur is not None else 99)) else ""
             for i, v in enumerate(values)]
    fig = go.Figure(go.Bar(
        x=labels, y=ys, marker=dict(color=colors, cornerradius=6), text=texts, textposition="outside",
        textfont=dict(size=12, color="#F8FAFC", weight=600),
        customdata=custom if custom is not None else labels, hovertemplate=hover or "%{x}<extra></extra>",
        cliponaxis=False))
    if target and target <= top:
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
    """2026-11-19 사용자: 기간 단위(월/연)는 필요 없음 → 연도만 고름."""
    c0, c1 = st.columns([1, 1.5], vertical_alignment="bottom")
    with c0:
        page_header("장비 종합 현황", "현황")
    today = dt.date.today()
    # 2026-11-19 사용자: 기준일 표시는 표마다 말고 연도 칸 앞에 한 번만, '연도' 글자는 없앰
    with c1, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                          gap="medium", key="dash_pp"):
        ys = sorted(set(years) | {today.year}, reverse=True)
        y = st.session_state.get("dash_year", today.year)
        st.markdown(f'<div class="dper">{f"{y}년 · {today:%m/%d} 기준" if y == today.year else f"{y}년"}</div>',
                    unsafe_allow_html=True, width="content")
        year = st.selectbox("연도", ys, index=ys.index(today.year), key="dash_year", label_visibility="collapsed",
                            format_func=lambda v: f"{v}년", width=130)
    return year, None


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

    ref_day = min(today, (pd.Timestamp(year, cm, 1) + pd.offsets.MonthEnd(0)).date())  # 주간·월간 표의 기준일
    _top_row(year, y_tot, kpi, ref_day)
    _util_section(year, cm, cq, period, target, m_of, q_of, m_tot, pm_tot, q_tot, pq_tot, y_tot, py_tot,
                  (m_sum, q_sum, year_sum), cats, kpi)
    _fee_section(year, cm, period, months, ref_day, kpi)


def _year_fee(year: int, upto) -> float:
    """아래 '분류별 발행' 표의 연간 합계와 같은 값 (기준일까지)."""
    from core import fee_ledger
    fl = fee_ledger.load()
    return float(sum(v for d, v in zip(fl["tax_date"], fl["supply"])
                     if d and d.year == year and d <= upto and pd.notna(v))) if not fl.empty else 0.0


def _won_short(v: float) -> str:
    """756,331,036 → '7.56억 원', 12,340,000 → '1,234만 원'."""
    if v >= 1e8:
        return f"{v / 1e8:.2f}<small>억 원</small>"
    return f"{v / 1e4:,.0f}<small>만 원</small>" if v else "0<small>원</small>"


def _top_row(year: int, y_tot: dict, kpi: dict, ref_day) -> None:
    """2026-11-19 사용자 시안: 맨 위 한 줄 요약 4칸 (01 연간 가동률 · 02 연간 수수료 · 03 유지보수 · 04 종·대수)."""
    from views.equipment import count_summary
    goal_u, goal_f = float(kpi["util_total"] or 0), float(kpi["fee"] or 0)
    fee = _year_fee(year, ref_day)
    c1 = (f'<div class="k c1"><div class="no" style="color:{BLUE[0]}">01</div><div class="tt">{E(w("연간 가동률"))}</div>'
          f'<div class="big" style="color:{BLUE[0]}">{y_tot["util"]:.1f}<small>%</small></div>'
          f'<div class="sub">목표 {goal_u:.1f}%</div></div>')
    rate = f'달성률 <b style="color:{TEAL[0]}">{fee / goal_f * 100:.1f}%</b>' if goal_f else "&nbsp;"
    c2 = (f'<div class="k c2"><div class="no" style="color:{TEAL[0]}">02</div><div class="tt">연간 수수료</div>'
          f'<div class="big" style="color:{TEAL[0]}">{_won_short(fee)}</div><div class="sub">{rate}</div></div>')
    # 03 유지보수: 올해 건수 + 달마다 작은 숫자
    mt = db.load_maint()
    mt = mt[mt["date"].map(lambda d: bool(d) and d.year == year)] if not mt.empty else mt
    by_m = mt.groupby(mt["date"].map(lambda d: d.month)).size().to_dict() if not mt.empty else {}
    mini = "".join(f'<div><b class="{"" if by_m.get(m) else "z"}">{by_m.get(m, 0)}</b><span>{m}월</span></div>'
                   for m in range(1, 13))
    note = "" if len(mt) else '<div class="note">선택한 해에 유지보수 기록이 없어요</div>'
    c3 = (f'<div class="k c3"><div class="hd"><div class="bd" style="background:{AMBER[2]};color:{AMBER[0]}">⚙</div>'
          f'<div class="lab"><div class="no" style="color:{AMBER[0]}">03</div><div class="tt">유지보수 실적</div></div></div>'
          f'<div class="big" style="color:{AMBER[0]}">{len(mt)}<small>건</small></div>{note}'
          f'<div class="mm">{mini}</div></div>')
    # 04 종·대수 (센터별 + 합계)
    blocks, _ = count_summary(db.load_equipment(full=True))
    df = dict(blocks)["센터별"]
    tot = df.iloc[-1]
    rows = "".join(
        f'<tr{" class=sum" if r["센터"] == "합계" else ""}><td>{E(r["센터"])}</td><td>{r["종"]}종</td>'
        f'<td>{r["대수"]}대</td><td>{r["i-Tube 등록"]}</td></tr>' for r in df.to_dict("records"))
    c4 = (f'<div class="k c4"><div class="hd"><div class="bd" style="background:{PURPLE[2]};color:{PURPLE[0]}">▦</div>'
          f'<div class="lab"><div class="no" style="color:{PURPLE[0]}">04</div><div class="tt">장비 종·대수</div></div>'
          f'<span class="pill">{tot["종"]}종 / {tot["대수"]}대</span></div>'
          f'<table><thead><tr><th>센터</th><th>종</th><th>대수</th><th>i-Tube 등록</th></tr></thead><tbody>{rows}</tbody>'
          f'</table></div>')
    st.markdown(f'<div class="dtop">{c1}{c2}{c3}{c4}</div>', unsafe_allow_html=True)


def _util_section(year, cm, cq, period, target, m_of, q_of, m_tot, pm_tot, q_tot, pq_tot, y_tot, py_tot,
                  sums, cats, kpi) -> None:
    with st.container(key="dsec_util"):
        _head(1, w("가동률"), BLUE, "%", period)
        # 2026-11-19 사용자 요청: 큰 숫자 3칸 · 한 줄 요약은 뺌 (그래프 · 분류별 표만)

        st.markdown(f'<div class="dct">{E(w("월별 가동률"))}</div>', unsafe_allow_html=True)
        # 2026-11-19 사용자: 실적 확대 스위치 없앰 → 늘 실적에 맞춰 확대 (목표선은 화면 안에 들 때만)
        vals = [m_of[m]["가동률"] if m in m_of else None for m in range(1, 13)]
        real = [v for v in vals if v is not None and pd.notna(v)]
        top = max(real + [1]) * 1.3
        _bars(vals, [f"{m}월" for m in range(1, 13)], cm - 1, BLUE, lambda v: f"{v:.1f}%", "dash_util_m",
              target=target or None, top=top, hover=w("%{x} 가동률 %{y:.1f}%<extra></extra>"))

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
    if round(v, 1) == 0:
        return '<td class="z">0.0%</td>'
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
        fees = cur.groupby(mo[yr == year])["supply"].sum().to_dict() if not cur.empty else {}
        goal = float(kpi["fee"] or 0)
        # 2026-11-19 사용자 요청: 큰 숫자 3칸 · 한 줄 요약은 뺌 (그래프 · 분류별 표만)

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
            f'<td class="{"v" if sums[k].get(c) else "z"}">{_won_k(sums[k].get(c, 0))}</td>' for _, k, _ in cols) + "</tr>"
    tot = {k: sum(sums[k].values()) for _, k, _ in cols}
    rows += '<tr class="sum"><td>합계</td>' + "".join(f"<td>{_won_k(tot[k])}</td>" if tot[k] else '<td class="z">0</td>' for _, k, _ in cols) + "</tr>"
    rows += '<tr class="rate"><td>달성률</td>' + "".join(
        (f'<td class="{"hit" if tot[k] >= g else ""}">{tot[k] / g * 100:.1f}%</td>' if tot[k] else '<td class="z">0.0%</td>')
        if g else '<td class="z">–</td>'
        for _, k, g in cols) + "</tr>"
    return f'<table class="drep fee"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'
