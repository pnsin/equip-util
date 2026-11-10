"""실적 입력 › 충방전기: 챔버마다 누가 언제까지 쓰는지 한눈에 (입력은 달력 카드에서 한 번만)."""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import chargers, db
from ui_style import page_header
from views.calendar_entry import CATS, CHARGER_GROUP, PURPOSE_CAT

CSS = """<style>
.st-key-cb_top {align-items: center; margin-bottom: .4rem;}
.st-key-cb_center [data-testid="stButtonGroup"] {gap: 6px;}
.st-key-cb_center [data-testid="stButtonGroup"] button {border-radius: 999px !important; border: none !important;
  background: var(--panel) !important; box-shadow: 0 1px 2px rgba(17, 28, 46, .08); padding: 0 16px !important;}
.st-key-cb_center [data-testid="stButtonGroup"] button p {font-weight: 700; color: var(--muted);}
.st-key-cb_center [data-testid="stButtonGroup"] button[aria-checked="true"] {background: #334155 !important;}
.st-key-cb_center [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
.cb-kpis {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 4px 0 14px;}
.cb-k {background: var(--panel); border-radius: 16px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(17, 28, 46, .08); text-align: center;}
.cb-k span {display: block; font-size: 1rem; font-weight: 700; color: var(--kc); margin-bottom: 2px;}
.cb-k b {display: block; font-size: 1.45rem; color: var(--ink); line-height: 1.3;}
.cb-box {background: var(--panel); border-radius: 20px; box-shadow: 0 1px 3px rgba(17, 28, 46, .08); padding: 6px 0 8px; overflow-x: auto;}
.cb-t {border-collapse: collapse; width: max-content; margin: 0 auto; font-size: .8rem;}
.cb-t th {font-size: .72rem; color: #94A3B8; font-weight: 600; text-align: center; padding: 8px 8px; border-bottom: 1px solid #52617A;
  white-space: nowrap;}
.cb-t td {padding: 0 8px; height: 31px; border-bottom: 1px solid #52617A; white-space: nowrap;}
.cb-t td {text-align: center;} .cb-t td.tl {text-align: left;}
.cb-t td.u {font-weight: 700; color: var(--ink);}
.cb-t td.c {color: var(--muted);}
.cb-t td.m {color: #94A3B8;}
.cb-dash {color: #94A3B8;}
.cb-t td.co, .cb-t td.pd {font-weight: 700; color: var(--ink); font-size: .8rem;}
.cb-t td.pd {font-size: .88rem; letter-spacing: .01em;}  /* 숫자는 한글보다 작아 보여서 살짝 키움 */
.cb-t td.co {overflow: hidden; text-overflow: ellipsis;}
/* 엑셀 틀 고정처럼: 왼쪽 6칸은 그대로, 오른쪽 타임라인만 옆으로 스크롤 (2026-11-10) */
.cb-t .s0, .cb-t .s1, .cb-t .s2, .cb-t .s3, .cb-t .s4, .cb-t .s5 {position: sticky; z-index: 3; background: var(--panel); box-sizing: border-box;}
.cb-t .s0 {left: 0; width: 330px; min-width: 330px; max-width: 330px;}
.cb-t .s1 {left: 330px; width: 72px; min-width: 72px; max-width: 72px;}
.cb-t .s2 {left: 402px; width: 92px; min-width: 92px; max-width: 92px;}
.cb-t .s3 {left: 494px; width: 150px; min-width: 150px; max-width: 150px;}
.cb-t .s4 {left: 644px; width: 160px; min-width: 160px; max-width: 160px;}
.cb-t .s5 {left: 804px; width: 150px; min-width: 150px; max-width: 150px; box-shadow: inset -1px 0 0 #64748B;}
.cb-t td.s0[colspan] {width: 494px; max-width: 494px;} .cb-t td.s4[colspan] {width: 310px; max-width: 310px; box-shadow: inset -1px 0 0 #64748B;}
.cb-t th.tl {padding: 8px 0;}
@media (max-width: 700px) {.cb-t .s0, .cb-t .s1, .cb-t .s2, .cb-t .s3, .cb-t .s4, .cb-t .s5 {position: static;}}
.cb-t td.tl {position: relative; padding: 0;}
.cb-tl, .cb-mh {width: var(--tlw); min-width: var(--tlw);}  /* 달마다 같은 너비 */
.cb-t tr.grp td {border-top: 1px solid #52617A;}
.cb-tl {position: relative; height: 31px;}
.cb-mh {position: relative; height: 16px;}
.cb-mh span {position: absolute; top: 0; font-size: .7rem; color: #94A3B8; font-weight: 600; text-align: center; box-sizing: border-box;
  border-left: 1px solid #52617A;}
.cb-g {position: absolute; top: 0; bottom: 0; width: 1px; background: #52617A;}
.cb-now {position: absolute; top: -2px; bottom: -2px; width: 2px; background: #E35D78; border-radius: 2px; z-index: 2;}
.cb-bar {position: absolute; top: 5px; height: 21px; border-radius: 8px; font-size: .7rem; font-weight: 700; padding: 0 8px;
  display: flex; align-items: center; overflow: hidden; white-space: nowrap; border-left: 4px solid var(--fg);
  background: var(--bg); color: var(--fg); z-index: 1;}
.cb-bar.soon {border: 1.5px dashed #E8B04B; background: rgba(230,182,85,0.16); color: #B5650B;}
.cb-mini {display: inline-block; width: 34px; height: 6px; border-radius: 3px; background: rgba(85,230,158,0.16); margin: 0 5px 1px 8px;
  vertical-align: middle; overflow: hidden;}
.cb-mini i {display: block; height: 100%; background: #E35D78; border-radius: 3px;}
.cb-n {font-size: .7rem; font-weight: 700; color: #B8435C;}
.cb-free {position: absolute; top: 8px; left: 6px; font-size: .72rem; font-weight: 700; color: #1E8E5A;}
.cb-ch summary, label.cb-ch {cursor: pointer; list-style: none; display: inline-flex; align-items: center; gap: 6px;}
label.cb-ch input {display: none;}
label.cb-ch:has(input:checked) i {background: var(--accent); color: #fff;}
.cb-t tr.chx {visibility: collapse;} .cb-box.all tr.chx {visibility: visible;}
.cb-t tr.chx td {background: linear-gradient(rgba(99,102,241,.05), rgba(99,102,241,.05)), var(--panel); height: 28px;} .cb-t tr.chx td.n {color: #94A3B8; font-weight: 700; text-align: center;}
.cb-t tr.chx td:empty {border-bottom-color: transparent;}
.cb-ch summary::-webkit-details-marker {display: none;}
.cb-ch summary i, label.cb-ch i {font-style: normal; width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid var(--accent);
  color: var(--accent); display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800;
  line-height: 1;}
.cb-ch[open] summary i {background: var(--accent); color: #fff;}
.cb-ch ul {list-style: none; margin: 4px 0 6px; padding: 0; display: grid; grid-template-columns: repeat(4, max-content); gap: 2px 14px;}
.cb-ch li {display: flex; gap: 6px; font-size: .72rem; line-height: 1.5; color: #1E8E5A; white-space: nowrap;}
.cb-t td.u {white-space: nowrap; vertical-align: middle; padding: 0 12px; line-height: 1.35;}
.cb-t td.u .sp {font: inherit; color: inherit;}
.cb-ch li b {color: var(--muted); font-weight: 600; min-width: 38px;}
.cb-ch li.on {color: #E35D78; font-weight: 700;}
.cb-t td:has(details[open]) {white-space: normal; vertical-align: top; padding-top: 6px;}
.cb-sum td {background: linear-gradient(rgba(85,143,230,0.16), rgba(85,143,230,0.16)), var(--panel); font-weight: 700; color: var(--muted);}
.cb-foot {display: flex; flex-wrap: wrap; gap: 14px; font-size: .74rem; color: var(--muted); margin-top: 8px;}
.cb-foot i {display: inline-block; width: 11px; height: 11px; border-radius: 4px; margin-right: 5px; vertical-align: -1px;}
@media (max-width: 600px) {.cb-kpis {grid-template-columns: 1fr;}}
</style>"""


DASH = "<span class='cb-dash'>—</span>"


def _book_new() -> None:
    """'충방전기 예약': 달력 화면에서 오늘 입력 카드를 '시험(충방전기)' 장비로 엶."""
    st.session_state.cb_go_input = True
    st.session_state.cal_open = True
    st.session_state.cal_lane = CHARGER_GROUP
    st.session_state.pop("cal_pick", None)
    st.session_state.cal_day = dt.date.today()
    st.session_state.cal_month = dt.date.today().replace(day=1)


def _edit(b: dict) -> None:
    """현황판에서 고른 예약을 달력 입력 카드로 열어 고침 (기간·챔버·업체 등)."""
    d = b["start"]
    st.session_state.cb_go_input = True
    st.session_state.cal_open = True
    st.session_state.pop("cal_lane", None)
    st.session_state.cal_day = d
    st.session_state.cal_month = d.replace(day=1)
    st.session_state.cal_pick = {"day": d, "id": int(b["log_ids"][0]), "rec": {}, "period": True,
                                 "label": b["company"]}


def _short(name: str) -> str:
    """'배터리 완제품 활성화 장비(5V, 50A, 192ch)+챔버12대(…)' → '배터리 완제품 활성화 장비' (전체 이름은 마우스를 올리면)."""
    n = str(name).split("+")[0]
    return (n.split("(")[0].strip() or n.strip()) if n else str(name)


# 충방전기 현황표(박해철님 메일 26.11.04)에서 전압이 빠진 이름 → 전압 (이름 뒤 괄호에 전압이 없을 때만 앞에 붙임)
VOLT_FALLBACK = {"활성화 충방전기": "5V", "셀 평가 충방전기": "5V"}


def _spec(name: str) -> str:
    n = str(name).split("+")[0]
    sp = n[n.find("(") + 1:n.find(")")] if "(" in n and ")" in n else ""
    if sp and "V" not in sp.upper().replace("CH", ""):
        v = VOLT_FALLBACK.get(_short(name))
        sp = f"{v}, {sp}" if v else sp
    return sp


def _bar(b: dict, w0: dt.date, w1: dt.date, soon: bool, lane: int = 0) -> str:
    span = (w1 - w0).days + 1
    a, z = max(b["start"], w0), min(b["end"], w1)
    if z < a:
        return ""
    left = (a - w0).days / span * 100
    width = max(((z - a).days + 1) / span * 100, 1.2)
    bg, fg = CATS.get(PURPOSE_CAT.get(b["purpose"], "시험"), CATS["시험"])
    # 2026-11-10 막대 안에는 진행일/전체일만 (업체·기간은 옆 칸에)
    total = (b["end"] - b["start"]).days + 1
    done = min(max((dt.date.today() - b["start"]).days + 1, 0), total)
    text = f"{done}/{total}"
    tip = f"{b['company']} · {b['start']:%Y-%m-%d} ~ {b['end']:%Y-%m-%d}" + (f" · {b['staff']}" if b["staff"] else "")
    return (f"<div class='cb-bar{' soon' if soon else ''}' title='{html.escape(tip)}' "
            f"style='left:{left:.2f}%;width:{width:.2f}%;top:{5 + lane * 26}px;--bg:{bg};--fg:{fg}'>{html.escape(text)}</div>")


def _ch_label(r: dict, mini: str) -> str:
    """채널 칸: ⊕ 를 누르면 아래에 채널별 줄이 펼쳐짐 (체크박스 + CSS)."""
    if (int(r["ch_count"] or 0) or len(chargers.chamber_chs(r["channels"], 0))) <= 1:
        return html.escape(r["channels"]) + mini  # 채널이 1개면 펼칠 것이 없음
    return (f"<label class='cb-ch'><input type='checkbox' id='ck{int(r['id'])}'><i>+</i>"
            f"{html.escape(r['channels'])}{mini}</label>")


def _ch_list(r: dict, mini: str) -> str:
    """채널 칸: ⊕ 를 누르면 채널마다 오늘 쓰는 중인지 · 어느 업체가 쓰는지 펼쳐 봄 (2026-11-10)."""
    chs = chargers.chamber_chs(r["channels"], r["ch_count"])
    if not chs:
        return html.escape(r["channels"]) + mini
    who: dict[int, str] = {}
    for b in r["nows"]:
        for n in chargers.used_of(b["ch_part"], chs):
            who.setdefault(n, b["company"] or "내부")
    items = "".join(f"<li class='{'on' if n in who else ''}'><b>ch {n}</b><span>{html.escape(who[n]) if n in who else '비어 있음'}</span></li>"
                    for n in chs)
    return (f"<details class='cb-ch'><summary><i>+</i>{html.escape(r['channels'])}{mini}</summary>"
            f"<ul>{items}</ul></details>")


def _chan_rows(r: dict, bks: list[dict], w0, w1, today, grid: str, now_line: str, tlw: int) -> str:
    """⊕ 를 누르면 챔버 아래로 펼쳐지는 채널별 줄: 채널 · 업체 · 기간 · 타임라인 (2026-11-10)."""
    cid = int(r["id"])
    chs = chargers.chamber_chs(r["channels"], r["ch_count"])
    if len(chs) <= 1:
        return ""
    out = []
    for n in chs:
        mine = sorted((b for b in bks if n in chargers.used_of(b["ch_part"], chs)), key=lambda x: x["start"])
        bars, lanes = "", []
        for bb in mine:
            ln = next((j for j, e in enumerate(lanes) if e < bb["start"]), len(lanes))
            lanes[ln:ln + 1] = [bb["end"]]
            bars += _bar(bb, w0, w1, soon=bb["start"] > today, lane=ln)
        if not bars:
            bars = "<div class='cb-free'>비어 있음</div>"
        cur = next((b for b in mine if b["start"] <= today <= b["end"]), None)
        b = cur or next((b for b in mine if b["start"] > today), None)
        who = f"<td class='co s4' title='{html.escape(b['company'])}'>{html.escape(b['company'])}</td>" if b else "<td class='m s4'>—</td>"
        when = chargers.span_text(b["start"], b["end"], today) + ("" if cur else " 예약") if b else ""
        h = 28 + 26 * max(len(lanes) - 1, 0)
        out.append(f"<tr class='chx g{cid}'><td class='s1'></td><td class='s2'></td><td class='n s3'>ch {n}</td>{who}"
                   f"<td class='pd s5'>{html.escape(when)}</td>"
                   f"<td class='tl'><div class='cb-tl' style='height:{h}px'>{grid}{now_line}{bars}</div></td></tr>")
    return "".join(out)


def render() -> None:
    from views import common
    if st.session_state.pop("cb_go_input", False) and "input" in common.PAGES:
        st.switch_page(common.PAGES["input"])  # 예약·고치기는 실적 입력 달력 카드에서
    page_header("충방전기 현황", "현황")
    st.markdown(CSS, unsafe_allow_html=True)
    ch = db.load_channels()
    logs = db.load_logs()
    eq = db.load_equipment()
    today = dt.date.today()

    centers = list(dict.fromkeys(c for c in ch["center"] if c)) if not ch.empty else []
    bk = chargers.bookings(logs)
    stt = chargers.status(ch, bk, today) if not ch.empty else ch
    with st.container(key="cb_top", horizontal=True, gap="small", vertical_alignment="center"):
        center = None
        if centers:
            order = [k for k in db.CENTER_SHORT if k in centers] + [c for c in centers if c not in db.CENTER_SHORT]
            center = st.segmented_control("건물", ["전체"] + order, default="전체", key="cb_center",
                                          format_func=lambda c: db.CENTER_SHORT.get(c, c),
                                          label_visibility="collapsed") or "전체"
        d0 = today.replace(day=1)
        d1 = ((d0 + dt.timedelta(days=95)).replace(day=1)) - dt.timedelta(days=1)  # 이번 달 + 2개월
        rng = (d0, d1)  # 조회 기간은 이번 달 + 2개월 고정 (2026-11-10 기간 고르기 없앰)
        all_open = st.toggle("채널 모두 펼치기", key="cb_all")
        st.space("stretch")
        if centers:
            st.download_button("현황표 엑셀로", chargers.to_excel(stt, today), icon=":material/download:",
                               file_name=f"충방전기_현황표_{today:%y%m%d}.xlsx", key="cb_dl",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.button("충방전기 예약", icon=":material/add:", key="cb_new", on_click=_book_new, type="primary")

    if not centers:
        st.info("챔버 구성이 아직 없어요. 챔버 구성은 관리자에게 문의해 주세요.")
    else:
        g = stt if center == "전체" else stt[stt["center"] == center]
        total = int(g["ch_count"].sum())
        used = int(g["used"].sum())
        pct = f" · {used / total:.0%}" if total else ""
        st.markdown(
            "<div class='cb-kpis'>"
            f"<div class='cb-k' style='--kc:#A5B4FC'><span>전체 채널</span><b>{total} ch</b></div>"
            f"<div class='cb-k' style='--kc:#FF8DA1'><span>사용 중 채널</span><b>{used} ch{pct}</b></div>"
            f"<div class='cb-k' style='--kc:#6EE7B7'><span>미사용 채널</span><b>{total - used} ch</b></div>"
            "</div>", unsafe_allow_html=True)

        # 타임라인: 고른 기간 (기본 = 이번 달 + 2개월)
        w0, w1 = (rng if isinstance(rng, (list, tuple)) and len(rng) == 2 else (d0, d1))
        # 달마다 칸 너비가 같도록 고른 기간을 달 단위로 맞춤 (시작 달 1일 ~ 끝 달 말일)
        w0 = w0.replace(day=1)
        w1 = (w1.replace(day=1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        months, m = [w0], (w0.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        while m <= w1:
            months.append(m)
            m = (m + dt.timedelta(days=32)).replace(day=1)
        span = (w1 - w0).days + 1
        tlw = int(span / 30.4 * 130)  # 한 달 약 130px
        pos = lambda d: (d - w0).days / span * 100  # noqa: E731
        grid = "".join(f"<div class='cb-g' style='left:{pos(x):.2f}%'></div>" for x in months[1:])
        now_line = f"<div class='cb-now' style='left:{pos(today):.2f}%'></div>" if w0 <= today <= w1 else ""
        edges = [pos(x) for x in months] + [100.0]  # 월 글자는 그 달 칸의 가운데에
        mh = "".join(f"<span style='left:{edges[i]:.2f}%;width:{edges[i + 1] - edges[i]:.2f}%'>{x.month}월</span>"
                     for i, x in enumerate(months))
        rows, prev_u, prev_c, show_css = [], None, None, []
        recs = g.to_dict("records")
        span_u = {}  # 같은 충방전기 줄 수 (장비 칸 셀 병합)
        start = 0
        for i, r in enumerate(recs):
            if i and r["unit"] != recs[i - 1]["unit"]:
                start = i
            span_u.setdefault(start, 0)
            span_u[start] = span_u.get(start, 0) + 1 + (len(chs_) if len(chs_ := chargers.chamber_chs(r["channels"], r["ch_count"])) > 1 else 0)
        unit_ch = {}
        for x in recs:
            unit_ch[x["unit"]] = unit_ch.get(x["unit"], 0) + int(x["ch_count"] or 0)
        shorts = {u: _short(u) for u in dict.fromkeys(x["unit"] for x in recs)}
        all_bk = {cid: b for cid, b in bk.groupby("chamber_id")} if not bk.empty else {}
        for ri, r in enumerate(recs):
            b = r["now"] or r["next"]
            new_u = r["unit"] != prev_u
            nm = shorts[r["unit"]]
            spec = (_spec(r.get("unit_sheet", "")) or _spec(r["unit"])  # 사양(V·A·ch)은 챔버 구성에 적은 이름에서
                    or f"{int(unit_ch.get(r['unit'], 0))}ch")  # 어디에도 없으면 채널 수라도
            u_td = (f"<td class='u s0' rowspan='{span_u.get(ri, 1)}' title='{html.escape(r['unit'])}'>{html.escape(nm)}"
                    + (f" <span class='sp'>({html.escape(spec)})</span>" if spec else "") + "</td>") if new_u else ""
            c = html.escape(r["cycler"]) if (new_u or r["cycler"] != prev_c) else ""
            prev_u, prev_c = r["unit"], r["cycler"]
            bars, lanes = "", []  # 기간이 겹치는 예약(채널 일부씩)은 줄을 나눠 그림
            for bb in sorted(all_bk.get(int(r["id"]), pd.DataFrame()).to_dict("records"), key=lambda x: x["start"]):
                ln = next((j for j, e in enumerate(lanes) if e < bb["start"]), len(lanes))
                lanes[ln:ln + 1] = [bb["end"]]
                bars += _bar(bb, w0, w1, soon=bb["start"] > today, lane=ln)
            if not bars:
                bars = "<div class='cb-free'>비어 있음</div>"
            h = 31 + 26 * max(len(lanes) - 1, 0)
            cos = list(dict.fromkeys(x["company"] for x in r["nows"])) or ([b["company"]] if b else [])
            who = (f"<td class='co s4' title='{html.escape(', '.join(cos))}'>{html.escape(cos[0])}" + (f" <span class='m'>외 {len(cos) - 1}</span>" if len(cos) > 1 else "")
                   + "</td>" if cos else "<td class='m s4'>—</td>")
            n_all = int(r["ch_count"]) or len(chargers.chamber_chs(r["channels"], 0))
            mini = (f"<span class='cb-mini' title='오늘 {r['used']}/{n_all}ch 사용'><i style='width:{r['used'] / n_all * 100:.0f}%'></i></span>"
                    f"<span class='cb-n'>{r['used']}/{n_all}</span>") if r["used"] and n_all and r["used"] < n_all else ""
            when = chargers.span_text(b["start"], b["end"], today) + ("" if r["now"] else " 예약") if b else ""
            rows.append(f"<tr class='cbr {'grp' if new_u and rows else ''}'>{u_td}<td class='c s1'>{c}</td>"
                        f"<td class='s2'>{html.escape(r['chamber']) or DASH}</td><td class='m s3'>{_ch_label(r, mini)}</td>{who}"
                        f"<td class='pd s5'>{html.escape(when)}</td>"
                        f"<td class='tl'><div class='cb-tl' style='height:{h}px'>{grid}{now_line}{bars}</div></td></tr>")
            rows.append(_chan_rows(r, list(all_bk.get(int(r["id"]), pd.DataFrame()).to_dict("records")), w0, w1, today,
                                   grid, now_line, tlw))
            show_css.append(f"tr.cbr:has(#ck{int(r['id'])}:checked) ~ tr.g{int(r['id'])}{{visibility:visible;}}")
        rows.append(f"<tr class='cb-sum'><td colspan='3' class='s0'>{html.escape(db.CENTER_SHORT.get(center, center))} 합계</td><td class='s3'>{total} ch</td>"
                    f"<td colspan='2' class='s4'>사용 중 {used} · 비어 있음 {total - used}</td><td></td></tr>")
        st.markdown(
            "<style>" + "".join(show_css) + "</style>"
            f"<div class='cb-box{' all' if all_open else ''}'><table class='cb-t' style='--tlw:{tlw}px'><tr><th class='s0'>장비</th><th class='s1'>싸이클러</th><th class='s2'>챔버</th><th class='s3'>채널</th>"
            f"<th class='s4'>업체</th><th class='s5'>기간</th><th class='tl'><div class='cb-mh'>{mh}</div></th></tr>"
            + "".join(rows) + "</table></div>"
            "<div class='cb-foot'>"
            + "".join(f"<span><i style='background:{CATS[k][1]}'></i>{k}</span>" for k in ("시험", "제조", "분석", "지원"))
            + "<span><i style='border:1.5px dashed #E8B04B;background:rgba(230,182,85,0.16)'></i>아직 시작 전 (예약)</span>"
            "<span style='color:#E35D78'>│ 오늘</span></div>", unsafe_allow_html=True)

        mine = bk[bk["chamber_id"].isin(set(g["id"].astype(int)))] if not bk.empty else bk
        if not mine.empty:
            name_of = dict(zip(g["id"].astype(int), g["chamber"]))
            uniq = mine.sort_values("start").drop_duplicates("key")
            opts = uniq.to_dict("records")
            with st.container(key="cb_edit", horizontal=True, gap="small", vertical_alignment="center"):
                pick = st.selectbox(
                    "예약 고치기", range(len(opts)), index=None, placeholder="고칠 예약 고르기 (기간 · 챔버 · 업체)",
                    label_visibility="collapsed", key="cb_pick", width=420,
                    format_func=lambda i: " · ".join([
                        ", ".join(name_of.get(int(c), "?") for c in mine.loc[mine["key"] == opts[i]["key"], "chamber_id"]),
                        opts[i]["company"], chargers.span_text(opts[i]["start"], opts[i]["end"], today)]))
                st.button("고치기", icon=":material/edit:", key="cb_edit_go", disabled=pick is None,
                          on_click=_edit, args=(opts[pick] if pick is not None else {},))

    # 2026-11-10 '챔버 구성 고치기'는 화면에서 숨김 (필요하면 아래 줄 주석을 풀면 다시 나옴). 챔버 구성이 비어 있을 때만 보임
    if ch.empty:
        _config_editor(ch, eq)


def _config_editor(ch: pd.DataFrame, eq: pd.DataFrame) -> None:
    with st.expander("챔버 구성 고치기", icon=":material/tune:", expanded=ch.empty):
        names = {int(i): s for i, s in zip(eq["id"], eq["short"])}
        cands = sorted(db.charger_ids(eq, ch) | set(names), key=lambda i: (i not in db.charger_ids(eq, ch), names.get(i, "")))
        opts = [names[i] for i in cands if i in names]
        by_name = {names[i]: i for i in cands if i in names}
        view = pd.DataFrame({
            "id": ch["id"] if not ch.empty else pd.Series(dtype="int64"),
            "건물": ch["center"] if not ch.empty else pd.Series(dtype=str),
            "장비명": ch["unit"] if not ch.empty else pd.Series(dtype=str),
            "싸이클러": ch["cycler"] if not ch.empty else pd.Series(dtype=str),
            "챔버": ch["chamber"] if not ch.empty else pd.Series(dtype=str),
            "채널 no.": ch["channels"] if not ch.empty else pd.Series(dtype=str),
            "채널수": ch["ch_count"] if not ch.empty else pd.Series(dtype="int64"),
            "연결 장비": [names.get(int(e)) if pd.notna(e) else None for e in ch["equip_id"]] if not ch.empty else pd.Series(dtype=str),
        })
        ed = st.data_editor(view, num_rows="dynamic", hide_index=True, width="stretch", key="cb_cfg",
                            column_config={
                                "id": None,
                                "채널수": st.column_config.NumberColumn(min_value=0, step=1, help="비우면 채널 no.로 셈"),
                                "연결 장비": st.column_config.SelectboxColumn(
                                    options=opts, width="large",
                                    help="입력 카드에서 이 장비를 고르면 이 챔버가 나와요"),
                            })
        if st.button("저장", icon=":material/save:", type="primary", key="cb_cfg_save"):
            out = ed.rename(columns={"건물": "center", "장비명": "unit", "싸이클러": "cycler", "챔버": "chamber",
                                     "채널 no.": "channels", "채널수": "ch_count"})
            out["equip_id"] = out["연결 장비"].map(lambda v: by_name.get(v) if isinstance(v, str) else None)
            db.save_channels(out)
            st.toast("챔버 구성을 저장했어요.")
            st.rerun()
