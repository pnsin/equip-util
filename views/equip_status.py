"""현황 › 장비 가동 현황 (2026-11-21): 어느 장비가 언제 돌고 있는지 한눈에.

예전 '충방전기 현황'을 넓힘. 구분 전체 / 시험(환경) / 시험(충방전) / 제조 / 분석.
시험(충방전)은 예전 화면 그대로 챔버 · 채널까지, 나머지는 장비마다 한 줄 + 실적 막대.
등록(장비 사용 등록 달력)은 입력만 단순하게, 지금 무엇이 도는지는 여기서 봄.
"""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import calc, db, status
from core.status import CHARGER, GROUP_LABEL, GROUPS
from ui_style import page_header
from views import charger_board
from views.calendar_entry import CATS

DAY_PX = 8  # 하루 너비 (이번 달 + 2개월 ≈ 730px)

CSS = """<style>
.st-key-es_top {align-items: center; margin-bottom: .4rem; row-gap: 8px; flex-wrap: wrap;}
.st-key-es_cat [data-testid="stButtonGroup"], .st-key-cb_center [data-testid="stButtonGroup"] {gap: 6px;}
.st-key-es_cat [data-testid="stButtonGroup"] button {border-radius: 999px !important; border: none !important;
  background: var(--panel) !important; box-shadow: 0 1px 2px rgba(17, 28, 46, .08); padding: 0 16px !important;}
.st-key-es_cat [data-testid="stButtonGroup"] button p {font-weight: 700; color: var(--muted);}
.st-key-es_cat [data-testid="stButtonGroup"] button[aria-checked="true"] {background: #6366F1 !important;}
.st-key-es_cat [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
.es-t .ea, .es-t .eb, .es-t .ec {position: sticky; z-index: 3; background: var(--panel); box-sizing: border-box;}
.es-t .ea {left: 0; width: 300px; min-width: 300px; max-width: 300px;}
.es-t .eb {left: 300px; width: 150px; min-width: 150px; max-width: 150px;}
.es-t .ec {left: 450px; width: 130px; min-width: 130px; max-width: 130px; box-shadow: inset -1px 0 0 #64748B;}
.es-t td.ea {font-weight: 700; color: var(--ink); overflow: hidden; text-overflow: ellipsis;}
.es-t td.ea.sub {font-weight: 500; color: #CBD5E1;}
.es-t td.ea .tw {color: #64748B; margin-right: 4px;}
.es-t tr.sec td {height: 34px; background: linear-gradient(rgba(99,102,241,.08), rgba(99,102,241,.08)), var(--panel);}
.es-t tr.sec td.ea {font-size: .82rem; color: var(--fc);}
.es-t tr.sec td.ea i {display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--fc); margin-right: 7px;
  vertical-align: 1px;}
.es-t tr.sec td.ea span {color: #94A3B8; font-weight: 600; margin-left: 8px; font-size: .74rem;}
.es-t .cb-tl {background-image: repeating-linear-gradient(90deg, rgba(148,163,184,.10) 0 16px, transparent 16px 56px);
  background-size: 56px 100%; background-repeat: repeat-x;}
.es-hol {position: absolute; top: 0; bottom: 0; background: rgba(148,163,184,.10);}
.es-dh {position: relative; height: 15px;}
.es-dh span {position: absolute; top: 0; font-size: .62rem; color: #64748B; transform: translateX(-50%);}
.cb-bar .off {position: absolute; top: 0; bottom: 0;
  background: repeating-linear-gradient(135deg, rgba(15,23,42,.55) 0 3px, rgba(15,23,42,.25) 3px 6px);}
.cb-bar b {position: relative; font-weight: 700; overflow: hidden; text-overflow: ellipsis;}
.cb-foot i.wk {background: repeating-linear-gradient(135deg, #475569 0 3px, #1E293B 3px 6px);}
@media (max-width: 640px) {
  .es-t .ea {width: 112px; min-width: 112px; max-width: 112px; white-space: normal !important; word-break: keep-all;
    line-height: 1.25; font-size: .7rem; box-shadow: inset -1px 0 0 #64748B;}
  .es-t .eb {position: static; width: 84px; min-width: 84px; max-width: 84px; box-shadow: none; font-size: .7rem;}
  .es-t .ec {display: none;}  /* 휴대폰: 기간 칸은 빼고 막대가 바로 보이게 (업체 칸 · 막대에 마우스·길게 누르면 기간) */
  .es-t tr.sec td.ea span {display: block; margin: 1px 0 0 15px;}
}
</style>"""

DASH = "<span class='cb-dash'>—</span>"


def _bar(b: dict, w0: dt.date, w1: dt.date, today: dt.date, hol: set, lane: int) -> str:
    span = (w1 - w0).days + 1
    a, z = max(b["start"], w0), min(b["end"], w1)
    if z < a:
        return ""
    n = (z - a).days + 1
    left, width = (a - w0).days / span * 100, n / span * 100
    bg, fg = CATS.get(b["cat"], CATS["지원"])
    offs = ""
    if b["skip_off"]:  # 주말·공휴일에도 이어지는 시험: 막대는 잇고 그날만 빗금 (가동률 제외)
        offs = "".join(f"<span class='off' style='left:{k / n * 100:.3f}%;width:{100 / n:.3f}%'></span>"
                       for k in range(n) if status.is_off(a + dt.timedelta(days=k), hol))
    tip = f"{b['company']} · {b['start']:%Y-%m-%d} ~ {b['end']:%Y-%m-%d}" + (f" · {b['staff']}" if b["staff"] else "")
    if offs:
        tip += " · 주말·공휴일은 가동률에서 빠져요"
    label = f"<b>{html.escape(b['company'])}</b>" if n * DAY_PX >= 44 else ""  # 짧은 막대는 글자 없이 (마우스를 올리면 보임)
    return (f"<div class='cb-bar{' cb-soon' if b['start'] > today else ''}' title='{html.escape(tip)}' "
            f"style='left:{left:.3f}%;width:{max(width, .6):.3f}%;top:{5 + lane * 26}px;--bg:{bg};--fg:{fg};padding:0 4px'>"
            f"{offs}{label}</div>")


def _device_board(eq: pd.DataFrame, logs: pd.DataFrame, groups: dict, want: str, center: str, today: dt.date) -> None:
    w0, w1 = status.window(today)
    bk = status.bars(logs, w0, w1)
    rws = status.rows(eq, groups, bk, w0, w1, want, center)
    by_eq: dict[int, list[dict]] = {}
    for b in (bk.to_dict("records") if not bk.empty else []):
        by_eq.setdefault(int(b["equip_id"]), []).append(b)
    units = [r for r in rws if not r["head"] or r["own"]]  # 머리 줄(주장비)은 실적이 직접 붙었을 때만 한 대로 셈
    on_ids = {r["id"] for r in units if status.now_next(by_eq.get(r["id"], []), today)[1]}
    st.markdown(
        "<div class='cb-kpis'>"
        f"<div class='cb-k' style='--kc:#A5B4FC'><span>장비</span><b>{len(units)} 대</b></div>"
        f"<div class='cb-k' style='--kc:#FF8DA1'><span>오늘 가동 중</span><b>{len(on_ids)} 대</b></div>"
        f"<div class='cb-k' style='--kc:#6EE7B7'><span>쉬는 장비</span><b>{len(units) - len(on_ids)} 대</b></div>"
        "</div>", unsafe_allow_html=True)
    if not rws:
        st.markdown("<div class='cb-box' style='padding:28px;text-align:center;color:#94A3B8'>이 구분·센터에 장비가 없어요.</div>",
                    unsafe_allow_html=True)
        return

    hol = calc.kr_holidays({w0.year, w1.year})
    span = (w1 - w0).days + 1
    tlw = span * DAY_PX
    pos = lambda d: (d - w0).days / span * 100  # noqa: E731
    months, m = [w0], (w0 + dt.timedelta(days=32)).replace(day=1)
    while m <= w1:
        months.append(m)
        m = (m + dt.timedelta(days=32)).replace(day=1)
    edges = [pos(x) for x in months] + [100.0]
    mh = "".join(f"<span style='left:{edges[i]:.2f}%;width:{edges[i + 1] - edges[i]:.2f}%'>{x.month}월</span>"
                 for i, x in enumerate(months))
    mondays = [w0 + dt.timedelta(days=k) for k in range(span) if (w0 + dt.timedelta(days=k)).weekday() == 0]
    dh = "".join(f"<span style='left:{pos(d) + 50 / span:.2f}%'>{d.day}</span>" for d in mondays)
    grid = "".join(f"<div class='cb-g' style='left:{pos(x):.2f}%'></div>" for x in months[1:])
    grid += "".join(f"<div class='es-hol' style='left:{pos(d):.2f}%;width:{100 / span:.3f}%'></div>"
                    for d in sorted(hol) if w0 <= d <= w1 and d.weekday() < 5)
    now_line = f"<div class='cb-now' style='left:{pos(today) + 50 / span:.2f}%'></div>" if w0 <= today <= w1 else ""
    sat = (5 - w0.weekday()) % 7  # 첫 토요일까지 날수 → 주말 줄무늬 시작 위치
    wk_style = f"background-position-x:{sat * DAY_PX}px"

    out, cur_g = [], None
    for r in rws:
        if want == "전체" and r["group"] != cur_g:
            cur_g = r["group"]
            gu = [x for x in units if x["group"] == cur_g]
            n_on = sum(1 for x in gu if x["id"] in on_ids)
            fc = CATS[cur_g][1]
            out.append(f"<tr class='sec' style='--fc:{fc}'><td class='ea tl' colspan='1'><i></i>{GROUP_LABEL[cur_g]}"
                       f"<span>오늘 {n_on} / {len(gu)}대</span></td><td class='eb'></td><td class='ec'></td><td></td></tr>")
        bs = sorted(by_eq.get(r["id"], []), key=lambda b: b["start"])
        bars, lanes = "", []
        for b in bs:
            ln = next((j for j, e in enumerate(lanes) if e < b["start"]), len(lanes))
            lanes[ln:ln + 1] = [b["end"]]
            bars += _bar(b, w0, w1, today, hol, ln)
        h = 31 + 26 * max(len(lanes) - 1, 0)
        b, running = status.now_next(bs, today)
        who = (f"<td class='co eb' title='{html.escape(b['company'])}'>{html.escape(b['company'])}</td>" if b
               else f"<td class='m eb'>{DASH}</td>")
        when = (status_span(b, today) + ("" if running else " 예약")) if b else ""
        pad = 12 + 14 * r["depth"]
        tw = "<span class='tw'>└</span>" if r["depth"] else ""
        out.append(f"<tr><td class='ea{' sub' if r['depth'] else ''}' style='text-align:left;padding-left:{pad}px' "
                   f"title='{html.escape(r['full'])}'>{tw}{html.escape(r['name'])}</td>{who}"
                   f"<td class='pd ec'>{html.escape(when)}</td>"
                   f"<td class='tl'><div class='cb-tl' style='height:{h}px;{wk_style}'>{grid}{now_line}{bars}</div></td></tr>")
    st.markdown(
        f"<div class='cb-box'><table class='cb-t es-t' style='--tlw:{tlw}px'><tr><th class='ea'>장비</th><th class='eb'>업체</th>"
        f"<th class='ec'>기간</th><th class='tl'><div class='cb-mh'>{mh}</div><div class='es-dh cb-mh'>{dh}</div></th></tr>"
        + "".join(out) + "</table></div>"
        "<div class='cb-foot'>"
        + "".join(f"<span><i style='background:{CATS[k][1]}'></i>{k}</span>" for k in ("시험", "제조", "분석", "교육", "지원"))
        + "<span><i class='wk'></i>주말·공휴일 (가동률 제외)</span>"
        "<span><i style='border:1.5px dashed #E8B04B;background:rgba(230,182,85,0.16)'></i>아직 시작 전 (예약)</span>"
        "<span style='color:#E35D78'>│ 오늘</span></div>", unsafe_allow_html=True)


def status_span(b: dict, today: dt.date) -> str:
    from core import chargers
    return chargers.span_text(b["start"], b["end"], today)


def _excel(want: str, center: str) -> bytes:
    today = dt.date.today()
    w0, w1 = status.window(today)
    eq, logs = db.load_equipment(), db.load_logs()
    groups = status.device_group(eq, db.load_channels())
    bk = status.bars(logs, w0, w1)
    rws = status.rows(eq, groups, bk, w0, w1, want, center)
    hours = status.kpi_hours(logs, w0, w1, db.get_settings().get("alloc_mode", "spread"))
    title = "장비 가동 현황 · " + (GROUP_LABEL.get(want, "전체")) + (f" · {db.center_short(center)}" if center != "전체" else "")
    extra = charger_board.excel_bytes(center) if want in ("전체", CHARGER) else None
    return status.to_excel(rws, bk, hours, w0, w1, today, title, extra)


def render() -> None:
    from views import common
    if st.session_state.pop("cb_go_input", False) and "input" in common.PAGES:
        st.switch_page(common.PAGES["input"])  # 예약·고치기는 장비 사용 등록 달력 카드에서
    page_header("장비 가동 현황", "현황")
    st.markdown(charger_board.CSS + CSS, unsafe_allow_html=True)
    today = dt.date.today()
    eq = db.load_equipment()
    logs = db.load_logs()
    groups = status.device_group(eq, db.load_channels())
    cens = set(db.equip_centers(eq).values())
    order = [c for c in db.CENTER_SHORT.values() if c in cens]

    with st.container(key="es_top", horizontal=True, gap="small", vertical_alignment="center"):
        want = st.segmented_control("구분", ["전체"] + GROUPS, key="es_cat",
                                    default=None if "es_cat" in st.session_state else "전체",
                                    format_func=lambda g: GROUP_LABEL.get(g, g), label_visibility="collapsed") or "전체"
        center = st.segmented_control("센터", ["전체"] + order, default="전체", key="cb_center",
                                      format_func=db.center_short, label_visibility="collapsed") or "전체"
        all_open = st.toggle("채널 모두 펼치기", key="cb_all") if want == CHARGER else False
        st.space("stretch")
        tag = GROUP_LABEL.get(want, "전체").replace("(", "_").replace(")", "")
        st.download_button("엑셀 내려받기", lambda want=want, center=center: _excel(want, center),
                           icon=":material/download:", key="es_dl",
                           file_name=f"장비가동현황_{tag}_{today:%y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if want == CHARGER:
            st.button("충방전기 예약", icon=":material/add:", key="cb_new", on_click=charger_board._book_new, type="primary")

    if want == CHARGER:
        charger_board.body(center, all_open)
    else:
        _device_board(eq, logs, groups, want, center, today)


def render_chargers() -> None:
    """예전 주소 /chargers: 장비 가동 현황의 시험(충방전)으로."""
    from views import common
    st.session_state.es_cat = CHARGER
    if "status" in common.PAGES:
        st.switch_page(common.PAGES["status"])
    render()
