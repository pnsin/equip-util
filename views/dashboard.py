"""대시보드 — 01 가동률 · 02 장비 수수료 · 03 유지보수 실적 (2026-11-05 사용자 시안).

세 구역 모두 같은 모양: 큰 숫자 3칸 → 한 줄 요약 → 월별 막대 → 아래 작은 칸 2~3개.
"""
import datetime as dt
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import calc, db
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

CSS = """<style>
[class*="st-key-dsec_"] {background: var(--panel); border-radius: 24px; box-shadow: 0 4px 16px rgba(30,36,51,.04);
  padding: 24px 28px 22px; margin-bottom: 12px; gap: .55rem; transition: all 0.25s ease; border: 1px solid #26334D;}
[class*="st-key-dsec_"]:hover { transform: translateY(-4px); box-shadow: 0 20px 40px rgba(30,36,51,.08); border-color: #64748B; }
.dh {display: flex; align-items: center; gap: 14px; margin-bottom: 12px;}
.dh .ic {width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  font-size: 21px; font-weight: 700;}
.dh .no {font-size: 12px; font-weight: 700; letter-spacing: .08em; line-height: 1.1;}
.dh .tt {font-size: 21px; font-weight: 700; color: #F8FAFC; line-height: 1.3;}
.dh .per {margin-left: auto; font-size: 12px; color: #94A3B8; background: #26334D; padding: 5px 12px; border-radius: 99px;}
.dst {border: 1px solid #26334D; border-radius: 20px; padding: 16px 20px; height: 100%; min-height: 134px; transition: all 0.25s ease; background: rgba(85,121,230,0.16);}
.dst:hover {transform: translateY(-2px); box-shadow: 0 8px 24px rgba(30,36,51,.06); border-color: #64748B; background: var(--panel);}
.dst.big {border: 0; background: linear-gradient(135deg, #5B6CFF 0%, #9B6CFF 60%, #D27CE0 100%); box-shadow: 0 8px 22px rgba(91,108,255,.28);}
.dst.big:hover {transform: translateY(-2px); box-shadow: 0 14px 32px rgba(91,108,255,.4);}
.dst .sl {font-size: 13px; color: #94A3B8; font-weight: 600;}
.dst.big .sl {color: #94A3B8;}
.dst .sv {font-size: 2.05rem; font-weight: 700; letter-spacing: -.02em; margin: 2px 0 6px; color: #F8FAFC;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.dst.big .sv {color: #fff;}
.dst .sv small {font-size: 1rem; margin-left: 3px; font-weight: 600;}
.dst .sv.name {font-size: 1.55rem; padding: 4px 0 3px;}
.dch {font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 99px; display: inline-block;}
.dch.g {color: #2E9E6B; background: rgba(85,230,153,0.16);} .dch.r {color: #D25B5B; background: rgba(230,85,85,0.16);}
.dch.n {color: #94A3B8; background: #26334D;}
.dst.big .dch {background: rgba(255,255,255,.14); color: #F8FAFC;}
.dst.big .dch.g {color: #9FE3C1;} .dst.big .dch.r {color: rgba(230,85,85,0.3);}
.dlead {border-radius: 12px; padding: 11px 16px; font-size: 14px; line-height: 1.6; color: #F8FAFC; margin-top: 12px;}
.dct {font-size: 15px !important; font-weight: 800; color: #F1F5F9 !important; margin: 16px 0 -4px; padding-left: 9px;
  border-left: 3px solid #6366F1; line-height: 1.2; letter-spacing: -.01em;}
.dq {display: grid; grid-template-columns: repeat(4, 1fr); gap: 0 16px; margin: -10px 8px 4px;}
.dq div {border-top: 1.5px solid #64748B; text-align: center; font-size: 12px; color: #94A3B8; padding-top: 6px;}
.dq b {color: #F8FAFC; margin-left: 4px;}
.dbox {border: 1px solid #26334D; border-radius: 16px; padding: 14px 18px; height: 100%;}
.dbox .bh {margin: 0 0 8px; font-size: 14px; font-weight: 700; color: #F8FAFC; display: flex;
  justify-content: space-between;}
.dml {display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) 62px; gap: 10px; align-items: center;
  font-size: 12.5px; margin: 6px 0; color: #F8FAFC;}
.dml span {white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.dml b {text-align: right;}
.dtb {height: 8px; background: #26334D; border-radius: 99px; position: relative;}
.dtb i {position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px;}
.dpills {display: flex; gap: 8px; flex-wrap: wrap;}
.dpills span {font-size: 13px; padding: 6px 12px; border-radius: 12px; background: rgba(133,85,230,0.16); color: #F8FAFC;}
.dpills b {margin-left: 5px;}
.drec {display: flex; justify-content: space-between; gap: 10px; font-size: 13px; padding: 7px 0;
  border-bottom: 1px dashed #26334D; color: #F8FAFC;}
.drec:last-child {border: 0;}
.drec > span:first-child {white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.drec .tag {font-size: 11px; padding: 2px 8px; border-radius: 99px; margin-right: 6px; font-weight: 600;
  background: rgba(138,85,230,0.16); color: #7E5BC2;}
.dnone {font-size: 13px; color: #94A3B8; padding: 4px 0;}
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
    colors = [color[0] if i == cur else (color[1] if values[i] is not None else "#26334D") for i in range(len(values))]
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
    return "".join(f'<div class="dml"><span title="{E(n)}">{E(n)}</span><div class="dtb"><i style="width:'
                   f'{max(0.0, min(v / top, 1)) * 100:.1f}%;background:{color}"></i></div><b>{E(t)}</b></div>'
                   for n, v, t in rows)


def _box(col, title: str, body: str, right: str = "", right_color: str = "") -> None:
    r = f'<span style="color:{right_color}">{E(right)}</span>' if right else ""
    col.markdown(f'<div class="dbox"><div class="bh"><span>{E(title)}</span>{r}</div>{body}</div>', unsafe_allow_html=True)


def _man(won: float) -> str:
    """원 → '1억 2,350' / '1,840' (만원 단위, 단위 글자는 따로)."""
    m = round(won / 10000)
    if m >= 10000:
        return f"{m // 10000}억 {m % 10000:,}" if m % 10000 else f"{m // 10000}억"
    return f"{m:,}"


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
        page_header("대시보드", "현황")
    with c1:
        s, _, _, kind = period_picker("dash", ["월", "연"], "연", years=years)
    return s.year, (s.month if kind == "월" else None)


# ── 화면 ─────────────────────────────────────────────────────

def render() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    cfg = db.get_settings()
    logs_all = db.load_logs()
    eq_all = db.load_equipment()
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    today = dt.date.today()
    years = sorted({d.year for d in logs_all["start_date"].dropna()} | {today.year}) if not logs_all.empty else [today.year]
    centers = {i: SHORT_OF.get(c, "") for i, c in db.equip_centers(eq_all).items()}

    year, pick_m = _filters(years)
    eq, logs = eq_all, logs_all
    SHORT.clear()
    SHORT.update(zip(eq_all["id"].astype(int), eq_all["short"]))  # 같은 이름 장비는 'n호기'로
    if logs_all.empty:
        empty_state("아직 사용실적이 없습니다", "'실적 입력'에서 입력하거나 '가져오기 · 백업'에서 기존 엑셀을 가져오세요.", "◷")

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
        return calc.totals(summ(s, e_eff)), calc.totals(summ(ps, pe))

    m_ref = dt.date(year, cm, 1)
    m_tot, pm_tot = cur_and_prev("월", m_ref)
    q_tot, pq_tot = cur_and_prev("분기", m_ref)

    _util_section(year, cm, cq, period, target, m_of, q_of, m_tot, pm_tot, q_tot, pq_tot, y_tot, py_tot,
                  year_sum, centers)
    _fee_section(year, cm, period, months, m_of, m_tot, pm_tot, y_tot, py_tot, year_sum, logs, ys, ye_eff, today,
                 centers)
    _maint_section(year, cm, period, months, eq, eq_all, len(eq) < len(eq_all), today)


def _util_section(year, cm, cq, period, target, m_of, q_of, m_tot, pm_tot, q_tot, pq_tot, y_tot, py_tot,
                  year_sum, centers) -> None:
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
            else f'<div>{q}분기<b style="color:#94A3B8">–</b></div>' for q in range(1, 5)) + '</div>',
            unsafe_allow_html=True)

        # 센터별 주장비 (올해 누적, 산정 대상 장비 = 세부장비 시간 합산)
        st.markdown('<div class="dct" style="margin-bottom:2px">센터별 주장비 · 올해 누적</div>', unsafe_allow_html=True)
        k = year_sum[year_sum["KPI"]].copy() if not year_sum.empty else year_sum
        if k.empty:
            st.markdown('<div class="dnone">산정 대상 장비가 없어요</div>', unsafe_allow_html=True)
            return
        k["c"] = [centers.get(int(i), "") or "기타(본원)" for i in k["equip_id"]]
        groups = [c for c in CENTER_ORDER if c in set(k["c"])] + sorted(set(k["c"]) - set(CENTER_ORDER))
        cols = st.columns(min(3, len(groups)) or 1)
        for i, c in enumerate(groups):
            g = k[k["c"] == c].sort_values("가동률", ascending=False, na_position="last")
            used, avail = g["사용시간"].sum(), g["가용시간"].sum()
            rows = [(SHORT.get(int(i), n), v if pd.notna(v) else 0, f"{v:.0f}%" if pd.notna(v) else "–")
                    for i, n, v in zip(g["equip_id"], g["장비명"], g["가동률"])]
            _box(cols[i % len(cols)], c, _mini_list(rows, BLUE[0], 100),
                 f"{used / avail * 100:.0f}%" if avail else "–", BLUE[0])


def _fee_section(year, cm, period, months, m_of, m_tot, pm_tot, y_tot, py_tot, year_sum, logs, ys, ye_eff,
                 today, centers) -> None:
    """2026-11-05: 장비 수수료는 재무팀 매출장(세금일자 · 공급가) 기준. 실적별 수수료는 늦게·안 넣는 경우가 많아서."""
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
        _stats([
            (f"{cm}월", _man(m_fee), "만원", _delta((m_fee - pm_fee) / 10000, "만원", "지난달"), False),
            (f"{year}년 누적", _man(y_fee), "만원",
             _delta((y_fee / py_fee - 1) * 100, "%", "작년") if py_fee else "", True),
            ("미수금 · 올해", _man(unpaid.sum()), "만원",
             _chip(f"{int((unpaid > 0).sum())}건 남았어요", "r") if unpaid.sum() > 0 else _chip("모두 받았어요", "g"), False),
        ])
        done = {m: v for m, v in fees.items() if m <= cm}
        if fl.empty:
            _lead("수수료 입력 › 재무팀 매출장에서 엑셀을 올리면 여기에 나와요.", TEAL)
        elif done and sum(done.values()) > 0:
            best = max(done, key=done.get)
            _lead(f"올해 한 달 평균 <b>{_man(sum(done.values()) / cm)}만원</b>이 발행됐어요. "
                  f"{best}월이 <b>{_man(done[best])}만원</b>으로 가장 많았어요.", TEAL)
        else:
            _lead("올해는 아직 발행된 수수료가 없어요.", TEAL)

        st.markdown('<div class="dct">월별 수수료 (만원, 세금일자 · 공급가 기준)</div>', unsafe_allow_html=True)
        vals = [fees.get(m, 0) / 10000 if m <= cm or m in fees else None for m in range(1, 13)]
        _bars(vals, months, cm - 1, TEAL, lambda v: f"{v:,.0f}", "dash_fee_m",
              hover="%{x} 수수료 %{y:,.0f}만원<extra></extra>", custom=list(range(1, 13)))

        c1, c2 = st.columns(2)
        if cur.empty or cur["supply"].sum() <= 0:
            _box(c1, "업체별 · 올해", '<div class="dnone">기록 없음</div>')
            _box(c2, "발행내역별 · 올해", '<div class="dnone">기록 없음</div>')
            return
        by_c = cur.groupby("company")["supply"].sum().sort_values(ascending=False).head(5)
        _box(c1, "업체별 · 올해", _mini_list([(c, v, f"{_man(v)}만") for c, v in by_c.items()], TEAL[0]))
        by_i = cur.groupby("item")["supply"].sum().sort_values(ascending=False).head(5)
        _box(c2, "발행내역별 · 올해", _mini_list([(c, v, f"{_man(v)}만") for c, v in by_i.items()], TEAL[0]))


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
            f'<span style="color:#94A3B8;flex:none">{r.date:%m/%d}</span></div>' for r in recent.itertuples())
        _box(c2, "최근 기록", rec or '<div class="dnone">기록 없음</div>')
