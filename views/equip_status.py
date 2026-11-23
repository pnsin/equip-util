"""현황 › 장비 가동 현황 (2026-11-21): 어느 장비가 언제 돌고 있는지 한눈에.

예전 '충방전기 현황'을 넓힘. 구분 전체 / 시험(환경) / 시험(충방전) / 제조 / 분석.
시험(충방전)은 예전 화면 그대로 챔버 · 채널까지, 나머지는 장비마다 한 줄 + 실적 막대.
등록(장비 사용 등록 달력)은 입력만 단순하게, 지금 무엇이 도는지는 여기서 봄.
"""
from __future__ import annotations

import datetime as dt
import html
import re

import pandas as pd
import streamlit as st

from core import calc, db, status
from core.status import CHARGER, GROUP_LABEL, GROUPS
from ui_style import page_header
from views import charger_board
from views.calendar_entry import CATS

# 2026-11-23 사용자: 표처럼 칸이 많고 '일정 없는 장비' 줄이 구분마다 반복돼 보기 안 좋음 → A안 (타임라인 정리형)
# 장비 이름 칸 하나 + 기간 막대 (업체는 막대 안, 날짜는 옆), 기간 1주/1달 + ‹ 오늘 ›, 일정 없는 장비는 맨 아래 한 상자.
SPANS = {"1주": 110, "1달": 30}  # 하루 최소 px
WEEKDAY = "월화수목금토일"
NAME_W = 300

CSS = """<style>
.st-key-es_top {align-items: center; margin-bottom: .2rem; row-gap: 8px; flex-wrap: wrap;}
.st-key-es_nav {flex: none; width: auto !important;}
.st-key-es_nav button {min-height: 34px; padding: 0 10px;}
.st-key-es_span {flex: none; width: auto !important;}
.st-key-cb_edit {margin-top: .8rem;}
.tl2 {background: var(--panel); border-radius: 18px; overflow-x: auto; padding: 4px 0 10px; margin-top: .3rem;}
.tl2-in {position: relative; min-width: calc(var(--nw) + var(--n) * var(--md));}
.tl2 .cols {position: absolute; top: 0; bottom: 0; left: var(--nw); right: 0; pointer-events: none;}
.tl2 .cols i {position: absolute; top: 62px; bottom: 0;}
.tl2 .cols i.wl {top: 6px; width: 0; border-left: 1px solid #EAE7DF;}
.tl2 .cols i.off {background: rgba(120,104,72,.06);}
.tl2 .cols i.td {background: rgba(217,119,87,.13); box-shadow: inset 1px 0 0 rgba(217,119,87,.5), inset -1px 0 0 rgba(217,119,87,.5);}
.tl2 .r {display: grid; grid-template-columns: var(--nw) 1fr; position: relative;}
.tl2 .nm {position: sticky; left: 0; z-index: 2; background: var(--panel); padding: 6px 14px 6px 20px; min-width: 0;
  display: flex; flex-direction: column; justify-content: center; text-align: left;}
.tl2 .nm b {font-weight: 650; font-size: .86rem; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.tl2 .nm small {color: #A39F96; font-size: .72rem; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.tl2 .nm .sd {display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; background: #E8E6DF;}
.tl2 .nm .sd.d-now {background: #4A6B5D; box-shadow: 0 0 0 3px rgba(74,107,93,.18);}
.tl2 .nm .sd.d-soon {background: #D4A359;}
.tl2 .hd {height: 62px; border-bottom: 1px solid #EAE7DF;}
.tl2 .hd .dy small {display: block; font-size: .62rem; line-height: 1.15; font-weight: inherit; opacity: .85;}
.tl2 .hd .ln {position: relative;}
.tl2 .hd .wk {position: absolute; top: 9px; font-size: .74rem; color: #6B6860; font-weight: 650; white-space: nowrap; display: flex; justify-content: center;}
.tl2 .hd .wk.r {justify-content: flex-end; padding-right: 4px;}
.tl2 .hd .dy {position: absolute; bottom: 7px; font-size: .68rem; color: #A39F96; text-align: center;}
.tl2 .hd .dy.off {color: #C84B31; font-weight: 650;}
.tl2 .hd .dy.td b {display: block; margin: 0 2px; border-radius: 6px; padding: 1px 0; background: #D97757; color: #fff; font-weight: 700;}
.tl2 .grpw {position: relative; z-index: 3; margin-top: 18px; border-top: 2px solid var(--gc); background: color-mix(in srgb, var(--gc) 5%, #FFFFFF);}
.tl2 .grpw.first {margin-top: 0;}
.tl2 .grpw .grp {padding: 9px 20px;}
.tl2 .grp {display: flex; align-items: center; gap: 10px; padding: 16px 20px 8px; font-size: .84rem; font-weight: 700;
  color: var(--ink); position: sticky; left: 0; width: max-content;}
.tl2 .grp i {width: 8px; height: 8px; border-radius: 50%;}
.tl2 .grpw .grp {font-size: .92rem;}
.tl2 .grpw .grp i {width: 10px; height: 10px;}
.tl2 .grp span {color: #6B6860; font-weight: 500; font-size: .75rem;}
.tl2 .grp span em {font-style: normal; color: var(--ink); font-weight: 650;}
.tl2 .dv {border-top: 1px solid #EAE7DF;}
.tl2 .dv.kid {border-top: 1px dashed #EAE7DF;}
.tl2 .dv.kid .nm {padding-left: calc(38px + var(--dp, 0) * 14px);}
.tl2 .dv.kid .nm b {font-weight: 500; color: #4A4741; font-size: .8rem;}
.tl2 .ln {position: relative; overflow: hidden; min-height: 38px;}
.tl2 .bar {position: absolute; height: 24px; border-radius: 7px; display: flex; align-items: center; padding: 0 9px;
  font-size: .75rem; font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  background: var(--cb); color: var(--c); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 18%, transparent); box-sizing: border-box;}
.tl2 .bar.bdone {background: #F2EFE9; box-shadow: none; color: #8C877C; font-weight: 550;}
.tl2 .bar.cl {border-top-left-radius: 0; border-bottom-left-radius: 0;}
.tl2 .bar.cr {border-top-right-radius: 0; border-bottom-right-radius: 0;}
.tl2 .bar span {position: relative; z-index: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
.tl2 .bar small.pd {font-weight: 600; opacity: .72; margin-left: 6px; font-size: .7rem;}
.tl2 .out {position: absolute; height: 24px; display: block; line-height: 24px; overflow: hidden; text-overflow: ellipsis; font-size: .75rem; font-weight: 650;
  color: #191918; white-space: nowrap;}
.tl2 .out small {font-weight: 500; color: #6B6860; font-size: .7rem;}
.tl2 .out.bdone {opacity: .5;}
.tl2 .chx {display: none;} .tl2.all .chx {display: grid;}
.tl2 .chx .nm b {font-size: .74rem; color: #6B6860; font-weight: 600; padding-left: 22px;}
.tl2 .chx .ln {min-height: 26px;}
.tl2 .chx .nm {padding-top: 2px; padding-bottom: 2px;}
.tl2 .chx .bar {height: 20px; font-size: .7rem;} .tl2 .chx .out {height: 20px;}
.tl2 .dv.cb .nm small {padding-left: 0;}
.tl2 .free {position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: .72rem; color: #A39F96;}
.tl2 label.es-ck {display: flex; align-items: center; gap: 7px; cursor: pointer; min-width: 0;}
.tl2 label.es-ck input {display: none;}
.tl2 label.es-ck i {font-style: normal; flex: none; width: 15px; height: 15px; border-radius: 50%; border: 1.5px solid #D97757;
  color: #C26344; font-size: 12px; line-height: 12px; text-align: center; font-weight: 700;}
.tl2 label.es-ck:has(input:checked) i {background: #D97757; color: #fff; border-color: #D97757;}
.es-idle .chip small {color: #A39F96; font-size: .7rem; margin-left: 2px;}
.es-idle {background: var(--panel); border-radius: 18px; padding: 14px 20px; margin-top: 12px;}
.es-idle summary {list-style: none; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: .86rem; font-weight: 700;
  color: var(--ink);}
.es-idle summary::-webkit-details-marker {display: none;}
.es-idle summary span {color: #6B6860; font-weight: 500; font-size: .76rem;}
.es-idle summary em {margin-left: auto; font-style: normal; font-size: .76rem; color: #C26344; font-weight: 600;}
.es-idle summary em:before {content: "펼치기 ▾";} .es-idle[open] summary em:before {content: "접기 ▴";}
.es-idle .ig {display: grid; grid-template-columns: 110px 1fr; gap: 10px 12px; margin-top: 12px; text-align: left;}
.es-idle .k {font-size: .76rem; color: #6B6860; display: flex; gap: 6px; align-items: center; height: 26px;}
.es-idle .k i {width: 7px; height: 7px; border-radius: 50%;}
.es-idle .chips {display: flex; flex-wrap: wrap; gap: 6px;}
.es-idle .chip {font-size: .76rem; color: #4A4741; background: #F2EFE9; border-radius: 999px; padding: 4px 11px;}
.es-leg {display: flex; flex-wrap: wrap; gap: 8px 16px; justify-content: center; font-size: .74rem; color: #6B6860; margin-top: 12px;}
.es-leg span {display: flex; align-items: center; gap: 6px;}
.es-leg i {width: 16px; height: 10px; border-radius: 3px; display: inline-block;}
@media (max-width: 640px) {
  .st-key-es_top {gap: 6px !important;}
  .st-key-es_top > div:has(.st-key-es_cat), .st-key-es_cat {flex: 1 0 100% !important; width: 100% !important;}
  .st-key-es_cat [data-testid="stButtonGroup"] > div {flex-wrap: nowrap !important; gap: 3px !important;}
  .st-key-es_cat [data-testid="stButtonGroup"] button {padding: 0 8px !important;}
  .st-key-es_cat [data-testid="stButtonGroup"] button p {font-size: .78rem;}
  .st-key-es_span [data-testid="stButtonGroup"] button {padding: 0 9px !important;}
  .st-key-es_top > div:nth-child(2):not([class*="st-key"]) {display: none;}
  .tl2 {--nw: 92px !important; --md: 16px !important;}
  .tl2 .dv:not(.kid) .nm {display: contents;}
  .tl2 .dv:not(.kid) .nm b {grid-column: 1 / -1; grid-row: 1; padding: 9px 14px 2px; white-space: normal; line-height: 1.3;
    position: sticky; left: 0; z-index: 3; background: var(--panel);}
  .tl2 .dv:not(.kid) .nm small {grid-column: 1; grid-row: 2; padding: 0 6px 0 14px; align-self: center; position: sticky; left: 0;
    background: var(--panel); z-index: 2;}
  .tl2 .dv:not(.kid) .ln {grid-column: 2; grid-row: 2; margin: -8px 0 -4px;}
  .tl2 .dv.nob .ln, .tl2 .dv.nob .nm small {display: none;}
  .tl2 .dv.kid .nm {padding-left: 14px;}
  .tl2 .dv.kid .nm b {font-size: .72rem; white-space: normal; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; word-break: break-all;}
  .tl2 .nm {padding-left: 14px;}
  .tl2 .grp {padding-left: 14px;}
  .tl2 .grp span {font-size: .7rem;}
  .tl2 .hd .wk {font-size: .66rem;}
  .tl2 .out small {display: none;}
  .es-idle .ig {grid-template-columns: 1fr;}
  .es-idle .k {height: auto;}
  .es-leg {gap: 6px 12px; font-size: .68rem;}
}
</style>"""

INNER = ("#EAE8E3", "#3F3D38")  # 내부 사용 막대 색 (배경, 글자)


def window(today: dt.date) -> tuple[dt.date, dt.date, int]:
    """보는 기간: 1주 = 이번 주 월~일, 1달 = 이번 달 1일~말일 (기본). ‹ › 는 한 주 / 한 달씩."""
    span = st.session_state.get("es_span") or "1달"
    k = int(st.session_state.get("es_shift", 0))
    if span == "1주":
        w0 = today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=k)
        return w0, w0 + dt.timedelta(days=6), SPANS[span]
    m = today.year * 12 + today.month - 1 + k
    w0 = dt.date(m // 12, m % 12 + 1, 1)
    w1 = dt.date((m + 1) // 12, (m + 1) % 12 + 1, 1) - dt.timedelta(days=1)
    return w0, w1, SPANS["1달"]


def _move(step: int) -> None:
    st.session_state.es_shift = 0 if step == 0 else int(st.session_state.get("es_shift", 0)) + step


def _state(b: dict, today: dt.date) -> str:
    return "done" if b["end"] < today else ("soon" if b["start"] > today else "now")


def _tw(txt: str, small: bool = False) -> float:
    """글자 너비 (대략 px): 한글 12.5, 그 밖 6.8 (작은 글씨는 조금 좁게)."""
    w = sum(12.5 if ord(c) > 0x2E80 else 6.8 for c in txt)
    return w * (0.88 if small else 1)


def _label_plan(b: dict, w0: dt.date, w1: dt.date, today: dt.date, ppd: float, repeat: bool, day_px: float = 0) -> dict:
    """막대 글자 자리 정하기 (2026-11-23 겹침 해결): 막대 안에 들어가면 안, 아니면 막대 바로 오른쪽.
    오른쪽 글자 자리만큼 막대가 '차지하는 칸'을 늘려서 같은 줄 다음 막대와 절대 안 겹치게 줄을 나눔."""
    a, z = max(b["start"], w0), min(b["end"], w1)
    n = (z - a).days + 1
    comp = short_comp(b["company"])
    when = status_span(b, today).replace(" ", "") + (f" · {b['note']}" if b.get("note") else "")
    bar_px = n * max(day_px, ppd)  # 막대 안에 넣을지는 보통 너비로 (좁은 화면은 … 로 잘림)
    w_comp, w_when = _tw(comp) + 20, _tw(when, True) + 8
    if bar_px >= w_comp + w_when:
        mode, out_px = "both", 0.0  # 업체 + 기간 모두 막대 안
    elif bar_px >= w_comp:
        mode, out_px = "comp", w_when + 6  # 업체는 안, 기간은 오른쪽
    else:
        mode, out_px = "out", (0 if repeat else _tw(comp) + 5) + w_when + 6  # 모두 오른쪽 (같은 업체가 이어지면 기간만)
    reach = z + dt.timedelta(days=int(-(-out_px // ppd)) if out_px else 0)  # 글자까지 차지하는 마지막 날
    return {"mode": mode, "when": when, "repeat": repeat, "reach": reach}


def _bar(b: dict, w0: dt.date, w1: dt.date, today: dt.date, hol: set, lane: int, y0: int, plan: dict,
         limit: dt.date) -> str:
    """막대 하나. 바깥 글자는 같은 줄 다음 막대(limit) 앞에서 잘림 (… 표시) → 어떤 화면 너비에서도 안 겹침."""
    span = (w1 - w0).days + 1
    a, z = max(b["start"], w0), min(b["end"], w1)
    if z < a:
        return ""
    n = (z - a).days + 1
    left, width = (a - w0).days / span * 100, n / span * 100
    stt = _state(b, today)
    comp = b["company"]
    cbg, color = INNER if comp == "내부" else CATS.get(b["cat"], CATS["지원"])
    cls = "bar " + {"now": "", "soon": "", "done": "bdone"}[stt] + (" cl" if b["start"] < w0 else "") + (" cr" if b["end"] > w1 else "")
    tip = f"{comp} · {b['start']:%Y-%m-%d} ~ {b['end']:%Y-%m-%d}" + (f" · {b['staff']}" if b.get("staff") else "")
    if b.get("merged", 1) > 1:
        tip += f" · 실적 {b['merged']}건 이어짐"
    if b.get("note"):
        tip += f" · {b['note']}"
    if b.get("skip_off") and any(status.is_off(a + dt.timedelta(days=k), hol) for k in range(n)):
        tip += " · 주말·공휴일은 가동률에서 빠져요"
    top = f"top:{y0 + lane * 30}px"
    mode, when = plan["mode"], html.escape(plan["when"])
    comp = short_comp(comp)
    inner = ""
    if mode == "both":
        inner = f"<span>{html.escape(comp)} <small class='pd'>{when}</small></span>"
    elif mode == "comp":
        inner = f"<span>{html.escape(comp)}</span>"
    out_html = ""
    if mode != "both":
        txt = f"<small>{when}</small>" if (mode == "comp" or plan["repeat"]) else f"{html.escape(comp)} <small>{when}</small>"
        room = (min(limit, w1 + dt.timedelta(days=1)) - z).days - 1  # 다음 막대까지 빈 날
        mx = max(room, 0) / span * 100
        out_html = (f"<div class='out b{stt}' title='{html.escape(tip)}' "
                    f"style='left:calc({left + width:.3f}% + 5px);max-width:calc({mx:.3f}% - 8px);{top}'>{txt}</div>")
    return (f"<div class='{cls}' title='{html.escape(tip)}' style='--c:{color};--cb:{cbg};left:{left:.3f}%;width:{width:.3f}%;{top}'>"
            f"{inner}</div>{out_html}")


def _merge(bs: list[dict], hol: set) -> list[dict]:
    """같은 업체가 이어서 쓴 실적(사이가 비지 않거나 주말·공휴일만 끼면)은 막대 하나로 (2026-11-23: 하루짜리가 촘촘해 글자가 겹침)."""
    out: list[dict] = []
    for b in sorted(bs, key=lambda x: (x["start"], x["end"])):
        p = out[-1] if out else None
        gap = [p["end"] + dt.timedelta(days=k) for k in range(1, (b["start"] - p["end"]).days)] if p else []
        if p and p["company"] == b["company"] and p.get("cat") == b.get("cat") and len(gap) <= 7 \
                and all(status.is_off(d, hol) for d in gap):
            out[-1] = {**p, "end": max(p["end"], b["end"]), "merged": p.get("merged", 1) + 1,
                       "skip_off": (bool(p.get("skip_off")) and bool(b.get("skip_off"))) or bool(gap),
                       "note": p.get("note") if p.get("note") == b.get("note") else ""}
        else:
            out.append(dict(b))
    return out


def _lanes(bs: list[dict], w0: dt.date, w1: dt.date, today: dt.date, hol: set, day_px: float, y0: int = 7) -> tuple[str, int]:
    """막대들 → 겹치면 아래 줄로. 막대 + 오른쪽 글자 자리까지 '차지하는 칸'으로 줄을 나눠서 글자끼리 안 겹침."""
    ppd = day_px * 0.72  # 좁은 화면 기준으로 넉넉하게 (실제 하루 너비가 이보다 크면 글자 자리가 남을 뿐)
    lanes: list[list[tuple[dict, dict]]] = []
    last_comp, last_end = None, None
    for b in _merge(bs, hol):
        a, z = max(b["start"], w0), min(b["end"], w1)
        if z < a:
            continue
        repeat = False  # 업체명은 항상 보이게 (2026-11-23 사용자: 이름 빠진 막대가 헷갈림)
        plan = _label_plan(b, w0, w1, today, ppd, repeat, day_px)
        last_comp, last_end = b["company"], b["end"]
        ln = next((j for j, xs in enumerate(lanes) if xs[-1][1]["reach"] < a), None)
        if ln is None:
            lanes.append([(b, plan)])
        else:
            lanes[ln].append((b, plan))
    html_ = ""
    for ln, xs in enumerate(lanes):
        for k, (b, plan) in enumerate(xs):
            limit = max(xs[k + 1][0]["start"], w0) if k + 1 < len(xs) else w1 + dt.timedelta(days=1)
            html_ += _bar(b, w0, w1, today, hol, ln, y0, plan, limit)
    return html_, 2 * y0 + 24 + 30 * max(len(lanes) - 1, 0)


def _frame(w0: dt.date, w1: dt.date, md: int, today: dt.date) -> tuple[set, float, list[str], list[str]]:
    """타임라인 바탕: 주말·공휴일 · 오늘 열 색, 위쪽 날짜 줄."""
    span = (w1 - w0).days + 1
    hol = calc.kr_holidays({w0.year, w1.year})
    day_px = max(md, 980 / span)  # 하루 너비 (대략, 좁은 화면 기준으로 조금 작게)
    pc = lambda d: (d - w0).days / span * 100  # noqa: E731
    days = [w0 + dt.timedelta(days=k) for k in range(span)]
    cols, hd = [], []
    for d in days:
        off = status.is_off(d, hol)
        if off:
            cols.append(f"<i class='off' style='left:{pc(d):.3f}%;width:{100 / span:.3f}%'></i>")
        if d == today:
            cols.append(f"<i class='td' style='left:{pc(d):.3f}%;width:{100 / span:.3f}%'></i>")
        if d.weekday() == 0 and d > w0:  # 주 구분 선
            cols.append(f"<i class='wl' style='left:{pc(d):.3f}%'></i>")
        if d.weekday() == 0:  # 주 이름: 그 주 (보는 기간 안 부분) 가운데. 끝에 걸린 짧은 주는 오른쪽 끝에 붙임
            e = min(d + dt.timedelta(days=6), w1)
            n = (e - d).days + 1
            pos = "c" if n >= 3 else "r"
            hd.append(f"<div class='wk {pos}' style='left:{pc(d):.3f}%;width:{n / span * 100:.3f}%'>{d.month}월 {d.day}일 주</div>")
        if span <= 35:  # 날짜 줄 (1주는 요일도)
            lab = f"{d.day} {WEEKDAY[d.weekday()]}" if span <= 7 else f"{d.day}<small>{WEEKDAY[d.weekday()]}</small>"
            lab = f"<b>{lab}</b>" if d == today else lab
            hd.append(f"<div class='dy{' off' if off else ''}{' td' if d == today else ''}' "
                      f"style='left:{pc(d):.3f}%;width:{100 / span:.3f}%'>{lab}</div>")

    return hol, day_px, cols, hd


def _device_board(eq: pd.DataFrame, logs: pd.DataFrame, groups: dict, want: str, center: str, today: dt.date) -> None:
    w0, w1, md = window(today)
    span = (w1 - w0).days + 1
    bk = status.bars(logs, w0, w1)
    rws = status.rows(eq, groups, bk, w0, w1, want, center)
    if not rws:
        st.markdown("<div class='tl2' style='padding:28px;text-align:center;color:#6B6860'>이 구분·센터에 장비가 없어요.</div>",
                    unsafe_allow_html=True)
        return
    by_eq: dict[int, list[dict]] = {}
    for b in (bk.to_dict("records") if not bk.empty else []):
        by_eq.setdefault(int(b["equip_id"]), []).append(b)
    fam: dict[int, list[dict]] = {}  # 주장비 → 묶음 줄 (자신 먼저)
    for r in rws:
        fam.setdefault(r["root"], []).append(r)
    fam_bars = {rt: [b for x in xs for b in by_eq.get(x["id"], [])] for rt, xs in fam.items()}
    n_kids = {}
    for i, p in zip(eq["id"], eq["parent_id"]):
        if pd.notna(p):
            n_kids[int(p)] = n_kids.get(int(p), 0) + 1

    hol, day_px, cols, hd = _frame(w0, w1, md, today)

    def lane_html(bs: list[dict], y0: int = 7) -> tuple[str, int]:
        return _lanes(bs, w0, w1, today, hol, day_px, y0)

    def dot(bs: list[dict]) -> str:
        ss = {_state(b, today) for b in bs}
        return "now" if "now" in ss else ("soon" if "soon" in ss else "")

    out, idle = [], {}
    secs = GROUPS if want == "전체" else [want]
    for sec in secs:
        roots = [rt for rt, xs in fam.items() if xs[0]["group"] == sec]
        if not roots:
            continue
        busy = [rt for rt in roots if fam_bars[rt]]
        idle[sec] = [fam[rt][0] for rt in roots if not fam_bars[rt]]
        if not busy:  # 이 기간에 쓰는 장비가 없는 구분은 제목도 없이 아래 '일정 없는 장비'에만
            continue
        n_now = sum(1 for rt in roots if dot(fam_bars[rt]) == "now")
        n_soon = sum(1 for rt in roots if dot(fam_bars[rt]) == "soon")
        out.append(f"<div class='grpw{'' if out else ' first'}' style='--gc:{CATS[sec][1]}'><div class='grp'><i style='background:{CATS[sec][1]}'></i>{GROUP_LABEL[sec]}"
                   f"<span>오늘 <em>{n_now}</em> · 예정 <em>{n_soon}</em> · 전체 {len(roots)}대</span></div></div>")
        for rt in busy:
            xs = fam[rt]
            head = xs[0]
            own = by_eq.get(rt, [])
            nk = n_kids.get(rt, 0)
            sub = " · ".join(x for x in (db.center_short(head["center"]), f"세부 {nk}" if nk else "") if x)
            bars, h = lane_html(own, 14)
            out.append(f"<div class='r dv{'' if own else ' nob'}'><div class='nm' title='{html.escape(head['full'])}'>"
                       f"<b><span class='sd d-{dot(fam_bars[rt])}'></span>{html.escape(head['name'])}</b><small>{html.escape(sub)}</small></div>"
                       f"<div class='ln' style='height:{h}px'>{bars}</div></div>")
            for x in xs[1:]:
                bs = by_eq.get(x["id"], [])
                if not bs:  # 이 기간에 실적이 없는 세부장비는 줄을 만들지 않음 (세부 n 으로만)
                    continue
                bars, h = lane_html(bs)
                out.append(f"<div class='r dv kid' style='--dp:{max(x['depth'] - 1, 0)}'><div class='nm' title='{html.escape(x['full'])}'>"
                           f"<b>{html.escape(x['name'])}</b></div><div class='ln' style='height:{h}px'>{bars}</div></div>")
    st.markdown(
        f"<div class='tl2' style='--nw:{NAME_W}px;--n:{span};--md:{md}px'><div class='tl2-in'>"
        f"<div class='cols'>{''.join(cols)}</div>"
        f"<div class='r hd'><div class='nm'></div><div class='ln'>{''.join(hd)}</div></div>"
        + "".join(out) + "</div></div>", unsafe_allow_html=True)

    n_idle = sum(len(v) for v in idle.values())
    if n_idle:
        ig = "".join(f"<div class='k'><i style='background:{CATS[g][1]}'></i>{GROUP_LABEL[g]}</div><div class='chips'>"
                     + "".join(f"<span class='chip' title='{html.escape(r['full'])}'>{html.escape(r['name'])}</span>" for r in rs)
                     + "</div>" for g, rs in idle.items() if rs)
        st.markdown(f"<details class='es-idle'><summary>이 기간 일정 없는 장비 <span>{n_idle}대</span><em></em></summary>"
                    f"<div class='ig'>{ig}</div></details>", unsafe_allow_html=True)
    _legend()


def _legend(cats: tuple = ("시험", "제조", "분석", "교육", "지원")) -> None:
    leg = "".join(f"<span><i style='background:{CATS[k][0]};box-shadow:inset 0 0 0 1.5px {CATS[k][1]}'></i>{k}</span>" for k in cats)
    leg += (f"<span><i style='background:{INNER[0]};box-shadow:inset 0 0 0 1.5px {INNER[1]}'></i>내부</span>"
            "<span style='margin-left:10px'><i style='background:#F2EFE9'></i>끝남 (흐린 색)</span>"
            "<span><b style='color:#C84B31;font-weight:650'>빨간 날짜</b> = 주말·공휴일 (가동률 제외)</span>")
    st.markdown(f"<div class='es-leg'>{leg}</div>", unsafe_allow_html=True)


def _charger_board(center: str, all_open: bool, today: dt.date) -> None:
    """시험(충방전) (2026-11-23 사용자: 충방전도 새 디자인으로): 충방전기 → 챔버 줄 + 기간 막대, ⊕ 로 채널 줄.
    센터마다 제목 줄에 오늘 사용 채널 (예전 큰 숫자 상자 대신). 이 기간 예약이 없는 충방전기는 맨 아래 한 상자."""
    from core import chargers
    ch = db.load_channels()
    if ch.empty:
        st.info("챔버 구성이 아직 없어요. 챔버 구성은 관리자에게 문의해 주세요.")
        charger_board._config_editor(ch, db.load_equipment())
        return
    w0, w1, md = window(today)
    span = (w1 - w0).days + 1
    bk = chargers.bookings(db.load_logs())
    stt = chargers.status(ch, bk, today)
    if center != "전체":
        stt = stt[stt["center"] == center]
    if stt.empty:
        st.markdown("<div class='tl2' style='padding:28px;text-align:center;color:#6B6860'>이 센터에 충방전기가 없어요.</div>",
                    unsafe_allow_html=True)
        return
    hol, day_px, cols, hd = _frame(w0, w1, md, today)
    by_ch: dict[int, list[dict]] = {}
    for b in (bk.to_dict("records") if not bk.empty else []):
        if b["end"] >= w0 and b["start"] <= w1:
            by_ch.setdefault(int(b["chamber_id"]), []).append(b)

    def as_bar(b: dict, chs: list[int]) -> dict:
        n_used, n_all = len(chargers.used_of(b["ch_part"], chs)), len(chs)
        return {**b, "cat": status.PURPOSE_CAT.get(b["purpose"], "시험"),
                "note": f"{n_used}/{n_all}ch" if 0 < n_used < n_all else ""}

    def lane_html(bs: list[dict], y0: int = 7) -> tuple[str, int]:
        return _lanes(bs, w0, w1, today, hol, day_px, y0)

    recs = stt.to_dict("records")
    out, show_css, idle = [], [], []
    for cen in dict.fromkeys(r["center"] for r in recs):
        rs = [r for r in recs if r["center"] == cen]
        units = list(dict.fromkeys(r["unit"] for r in rs))
        busy = [u for u in units if any(by_ch.get(int(r["id"])) for r in rs if r["unit"] == u)]
        idle += [(cen, u, [r for r in rs if r["unit"] == u]) for u in units if u not in busy]
        if not busy:
            continue
        total = int(sum(int(r["ch_count"] or 0) for r in rs))
        used = int(sum(int(r["used"] or 0) for r in rs))
        pct = f" · {used / total:.0%}" if total else ""
        out.append(f"<div class='grpw{'' if out else ' first'}' style='--gc:{CATS[CHARGER][1]}'><div class='grp'><i style='background:{CATS[CHARGER][1]}'></i>{html.escape(db.center_short(cen))}"
                   f"<span>오늘 사용 <em>{used}</em> / {total} ch{pct}</span></div></div>")
        for u in busy:
            urs = [r for r in rs if r["unit"] == u]
            spec = charger_board._spec(urs[0].get("unit_sheet", "")) or charger_board._spec(u) or f"{sum(int(r['ch_count'] or 0) for r in urs)}ch"
            u_used = sum(int(r["used"] or 0) for r in urs)
            u_all = sum(int(r["ch_count"] or 0) for r in urs)
            on = any(r["now"] for r in urs)
            soon = any(r["next"] for r in urs)
            sd = "now" if on else ("soon" if soon else "")
            sub = spec + (f" · 오늘 {u_used}/{u_all}ch" if on else "")
            out.append(f"<div class='r dv nob'><div class='nm' title='{html.escape(u)}'><b><span class='sd d-{sd}'></span>"
                       f"{html.escape(charger_board._short(u))}</b><small>{html.escape(sub)}</small></div>"
                       f"<div class='ln' style='height:38px'></div></div>")
            for r in urs:
                cid = int(r["id"])
                chs = chargers.chamber_chs(r["channels"], r["ch_count"])
                bs = [as_bar(b, chs) for b in by_ch.get(cid, [])]
                bars, h = lane_html(bs, 14)
                name = r["chamber"] or r["cycler"] or "전체"
                rng = html.escape(str(r["channels"]).replace("-", "~"))
                cyc = html.escape(r["cycler"]) + " · " if r["chamber"] and r["cycler"] else ""
                if len(chs) > 1:
                    tog = (f"<label class='es-ck'><input type='checkbox' id='ck{cid}'><i>+</i>"
                           f"<b>{html.escape(name)}</b></label>")
                    show_css.append(f".tl2-in:has(#ck{cid}:checked) .g{cid}{{display:grid;}}")
                else:
                    tog = f"<b>{html.escape(name)}</b>"
                out.append(f"<div class='r dv kid cb'><div class='nm'>{tog}<small>{cyc}ch {rng}</small></div>"
                           f"<div class='ln' style='height:{h}px'>{bars or '<span class=free>비어 있음</span>'}</div></div>")
                if len(chs) > 1:  # ⊕ 를 누르면 채널마다 한 줄
                    for n in chs:
                        mine = [as_bar({**b, "ch_part": ""}, [n]) for b in by_ch.get(cid, [])
                                if n in chargers.used_of(b["ch_part"], chs)]
                        cb, chh = lane_html(mine, 3)
                        out.append(f"<div class='r dv kid chx g{cid}'><div class='nm'><b>ch {n}</b></div>"
                                   f"<div class='ln' style='height:{chh}px'>{cb}</div></div>")
    if out:
        st.markdown(
            "<style>" + "".join(show_css) + "</style>"
            f"<div class='tl2{' all' if all_open else ''}' style='--nw:{NAME_W}px;--n:{span};--md:{md}px'><div class='tl2-in'>"
            f"<div class='cols'>{''.join(cols)}</div>"
            f"<div class='r hd'><div class='nm'></div><div class='ln'>{''.join(hd)}</div></div>"
            + "".join(out) + "</div></div>", unsafe_allow_html=True)
    if idle:
        n_ch = sum(int(r["ch_count"] or 0) for _, _, urs in idle for r in urs)
        by_cen: dict[str, list[str]] = {}
        for cen, u, urs in idle:
            spec = charger_board._spec(urs[0].get("unit_sheet", "")) or charger_board._spec(u)
            by_cen.setdefault(cen, []).append(
                f"<span class='chip' title='{html.escape(u)}'>{html.escape(charger_board._short(u))}"
                + (f" <small>{html.escape(spec)}</small>" if spec else "") + "</span>")
        ig = "".join(f"<div class='k'><i style='background:{CATS[CHARGER][1]}'></i>{html.escape(db.center_short(c))}</div>"
                     f"<div class='chips'>{''.join(v)}</div>" for c, v in by_cen.items())
        st.markdown(f"<details class='es-idle'><summary>이 기간 예약 없는 충방전기 <span>{len(idle)}대 · {n_ch} ch</span><em></em>"
                    f"</summary><div class='ig'>{ig}</div></details>", unsafe_allow_html=True)
    _legend(("시험", "제조", "분석", "지원"))

    mine = bk[bk["chamber_id"].isin(set(stt["id"].astype(int)))] if not bk.empty else bk
    if not mine.empty:  # 예약 고치기 (달력 입력 카드로 엶)
        name_of = dict(zip(stt["id"].astype(int), stt["chamber"]))
        opts = mine.sort_values("start").drop_duplicates("key").to_dict("records")
        with st.container(key="cb_edit", horizontal=True, gap="small", vertical_alignment="center"):
            pick = st.selectbox(
                "예약 고치기", range(len(opts)), index=None, placeholder="고칠 예약 고르기 (기간 · 챔버 · 업체)",
                label_visibility="collapsed", key="cb_pick", width=420,
                format_func=lambda i: " · ".join([
                    ", ".join(name_of.get(int(c), "?") for c in mine.loc[mine["key"] == opts[i]["key"], "chamber_id"]),
                    opts[i]["company"], chargers.span_text(opts[i]["start"], opts[i]["end"], today)]))
            st.button("고치기", icon=":material/edit:", key="cb_edit_go", disabled=pick is None,
                      on_click=charger_board._edit, args=(opts[pick] if pick is not None else {},))


def status_span(b: dict, today: dt.date) -> str:
    from core import chargers
    if b["start"] == b["end"]:  # 하루짜리는 날짜 하나만
        return f"{b['start']:%m.%d}" if b["start"].year == today.year else f"'{b['start']:%y.%m.%d}"
    return chargers.span_text(b["start"], b["end"], today)


def short_comp(c: str) -> str:
    """막대에 쓸 짧은 업체 이름: 주식회사·(주)·(재) 같은 말은 뺌 (말풍선엔 전체 이름)."""
    t = re.sub(r"\(주\)|\(재\)|㈜|주식회사", "", str(c)).strip()
    return re.sub(r"\s+", " ", t) or str(c)


def _excel(want: str, center: str) -> bytes:
    """시험파트 '참고_시험평가장비 가동률' 파일과 같은 형식: 총괄 + 장비마다 하루 한 줄 (올해 1/1 ~ 12/31)."""
    today = dt.date.today()
    ys, ye = dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
    eq, logs = db.load_equipment(), db.load_logs()
    groups = status.device_group(eq, db.load_channels())
    rws = status.rows(eq, groups, status.bars(logs, ys, ye), ys, ye, want, center, busy_first=False)
    title = "장비 가동 현황 · " + GROUP_LABEL.get(want, "전체") + (f" · {db.center_short(center)}" if center != "전체" else "")
    extra = charger_board.excel_bytes(center) if want in ("전체", CHARGER) else None
    return status.to_excel(rws, logs, eq, today.year, today, db.get_settings(), title, extra)


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

    # 2026-11-21 사용자: 버튼 두 줄이 복잡 → 한 줄 (센터는 작은 선택 칸, 엑셀은 아이콘)
    # 2026-11-23 사용자: 구분 버튼은 시험(환경) / 시험(충방전) / 제조 / 분석 그대로
    with st.container(key="es_top", horizontal=True, gap="small", vertical_alignment="center"):
        want = st.segmented_control("구분", ["전체"] + GROUPS, key="es_cat",
                                    default=None if "es_cat" in st.session_state else "전체",
                                    format_func=lambda g: GROUP_LABEL.get(g, g), label_visibility="collapsed") or "전체"
        st.space("stretch")
        # 기간 고르기 · 넘기기 (충방전기도 같은 타임라인, 2026-11-23)
        if st.session_state.get("es_span") not in (None, *SPANS):
            st.session_state.pop("es_span")
        st.segmented_control("기간", list(SPANS), key="es_span", default=None if "es_span" in st.session_state else "1달",
                             label_visibility="collapsed", on_change=lambda: st.session_state.update(es_shift=0))
        with st.container(key="es_nav", horizontal=True, gap="xsmall"):
            st.button("", icon=":material/chevron_left:", key="es_prev", on_click=_move, args=(-1,), help="앞 기간")
            st.button("오늘", key="es_today", on_click=_move, args=(0,))
            st.button("", icon=":material/chevron_right:", key="es_next", on_click=_move, args=(1,), help="다음 기간")
        center = st.selectbox("센터", ["전체"] + order, key="cb_center", format_func=db.center_short,
                              label_visibility="collapsed", width=110) or "전체"
        tag = GROUP_LABEL.get(want, "전체").replace("(", "_").replace(")", "")
        st.download_button("", lambda want=want, center=center: _excel(want, center),
                           icon=":material/download:", key="es_dl", help="엑셀 내려받기 (시험파트 가동률 파일 형식)",
                           file_name=f"{today.year}_장비 가동률_{tag}_{today:%y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if want == CHARGER:
        with st.container(key="es_chg", horizontal=True, gap="small", vertical_alignment="center"):
            all_open = st.toggle("채널 모두 펼치기", key="cb_all")
            st.space("stretch")
            st.button("충방전기 예약", icon=":material/add:", key="cb_new", on_click=charger_board._book_new, type="primary")
        _charger_board(center, all_open, today)
    else:
        _device_board(eq, logs, groups, want, center, today)


def render_chargers() -> None:
    """예전 주소 /chargers: 장비 가동 현황의 시험(충방전)으로."""
    from views import common
    st.session_state.es_cat = CHARGER
    if "status" in common.PAGES:
        st.switch_page(common.PAGES["status"])
    render()
