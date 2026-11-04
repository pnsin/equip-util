"""달력으로 하루 단위 실적을 입력하고, 하루치 입력을 다른 날로 복사하는 화면."""
from __future__ import annotations

import calendar
import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import db, rules, seed
from core.calc import expand_daily, kr_holidays
from ui_style import T, page_header
from views.common import new_company_dialog

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
DEFAULT_INDUSTRY = ("전기전자", "이차전지_에너지", "이차전지")

# 표 열 이름 → 내부 키
FIELDS = {
    "장비": "equip_label", "업체": "company", "담당자": "created_by", "활용유형": "usage_type", "사용목적": "purpose",
    "사용시간": "hours", "시료수": "samples", "사용료": "fee",
    "지원개요": "overview", "지원내용": "content", "기타": "etc",
}


CELL_LINES = 3  # 구역(시험/제조/분석)마다 바로 보여 줄 실적 수 (나머지는 "+N건")
CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@700;800&display=swap');
.block-container {padding-top: 2.5rem;}
.st-key-calgrid [data-testid="stHorizontalBlock"] {gap: 0.4rem;}
/* 달 이동 줄 */
.st-key-calnav {margin-bottom: .8rem; align-items: center;}
.st-key-calnav .cal-title {font-family: 'Nunito', 'IBM Plex Sans KR', sans-serif; font-size: 1.45rem; font-weight: 800;
  color: var(--ink); min-width: 8.5rem; text-align: center;
  line-height: 2.25rem;}
.st-key-calnav [data-testid="stElementContainer"]:has(.cal-title) {width: auto !important; flex: none;}
.st-key-calnav [data-testid="stMarkdownContainer"] {margin: 0;}
.st-key-calnav div[class*="st-key-cal_prev"] button, .st-key-calnav div[class*="st-key-cal_next"] button {
  width: 2.25rem; height: 2.25rem; min-height: 0; padding: 0; border-radius: 6px;}
.st-key-calnav div[class*="st-key-cal_today"] {margin-left: auto;}
/* 날짜 칸 */
.st-key-calgrid div[class*="st-key-cell_"] {min-height: 230px; padding: 32px 6px 8px; overflow: visible; gap: 5px; border-radius: 10px;
  position: relative; cursor: pointer;}
/* 날짜 버튼을 칸 전체에 깔아서 칸 어디를 눌러도 되게 함 (실적 줄은 그 위에 올라옴) */
.st-key-calgrid div[class*="st-key-day_"] {position: absolute !important; inset: 0; z-index: 0; width: auto !important;}
.st-key-calgrid div[class*="st-key-day_"] div:has(button),
.st-key-calgrid div[class*="st-key-day_"] span:has(button),
.st-key-calgrid div[class*="st-key-day_"] button {width: 100% !important; height: 100% !important;}
.st-key-calgrid div[class*="st-key-day_"] button {align-items: flex-start !important; padding: 6px 8px !important;
  border-radius: 10px;}
.st-key-calgrid div[class*="st-key-day_"] button:hover {background: rgba(45, 143, 213, 0.05);}
.st-key-calgrid div[class*="st-key-er_"], .st-key-calgrid div[class*="st-key-more_"] {position: relative; z-index: 1;}
.st-key-calgrid div[class*="st-key-er_"] {gap: 0;}
/* 실적 줄에 마우스를 올리면 오른쪽 위에 ✕ (누르면 삭제 확인) */
.st-key-calgrid div[class*="st-key-x_"] {position: absolute !important; top: 2px; right: 2px; width: auto !important;
  z-index: 2; opacity: 0; transition: opacity .12s;}
.st-key-calgrid div[class*="st-key-er_"]:hover div[class*="st-key-x_"] {opacity: 1;}
.st-key-calgrid div[class*="st-key-x_"] button {min-height: 0; height: 20px; width: 20px; padding: 0; border-radius: 4px;
  background: var(--panel, #fff); border: 1px solid var(--line2, #ccd); color: var(--muted, #667);}
.st-key-calgrid div[class*="st-key-x_"] button:hover {background: #d9534f; border-color: #d9534f; color: #fff;}
.st-key-calgrid div[class*="st-key-x_"] button span {font-size: 14px !important;}
/* 드래그 선택 */
.st-key-calgrid {user-select: none; -webkit-user-select: none;}
.st-key-calgrid div[class*="st-key-cell_"].cal-drag {background: rgba(45, 143, 213, 0.14) !important;
  border-color: var(--accent) !important;}
.st-key-cal_cmd {display: none !important;}
@keyframes calAnts {0% {outline-color: var(--accent);} 50% {outline-color: rgba(45, 143, 213, .35);} 100% {outline-color: var(--accent);}}
[data-testid="stElementContainer"]:has(iframe[height="0"]) {position: absolute !important; width: 0; height: 0;}
/* 날짜 칸에 마우스를 올리면 뜨는 카드 */
.st-key-calgrid div[class*="st-key-card"] {position: absolute !important; top: auto; bottom: calc(100% + 8px); left: -2px;
  width: 320px !important; min-width: 320px !important; max-width: none !important; z-index: 60; pointer-events: none; opacity: 0; visibility: hidden;
  transform: translateY(4px); transition: opacity .15s ease .35s, transform .15s ease .35s, visibility 0s linear .5s;}
.st-key-calgrid div[class*="st-key-cardr_"] {left: auto; right: -2px;}
.st-key-calgrid div[class*="st-key-cell_"]:hover div[class*="st-key-card"] {opacity: 1; visibility: visible;
  transform: none; transition-delay: .35s, .35s, 0s;}
.st-key-calgrid div[class*="st-key-cell_"]:hover {z-index: 40;}
.cal-card {background: #26324A; border: 1px solid #3A4866; border-radius: 14px;
  box-shadow: 0 14px 32px rgba(15, 30, 60, .32); padding: 13px 15px; color: #F3F6FB;}
.cal-card::after {content: ''; position: absolute; bottom: -7px; left: 26px; width: 12px; height: 12px;
  background: #26324A; transform: rotate(45deg); border-radius: 2px;}
div[class*="st-key-cardr_"] .cal-card::after {left: auto; right: 26px;}
.cal-card .cc-h {display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;
  padding-bottom: 8px; border-bottom: 1px solid rgba(255, 255, 255, .14);}
.cal-card .cc-d {font-size: 1.05rem; font-weight: 700; color: #fff;}
.cal-card .cc-sum {font-size: .85rem; color: #9CCBFF; font-weight: 700;}
.cal-card .cc-e {padding: 7px 10px; border-left: 3px solid var(--accent, #2D8FD5); margin: 6px 0;
  background: rgba(255, 255, 255, .06); border-radius: 0 8px 8px 0;}
.cal-card .cc-n {font-size: .95rem; font-weight: 700; line-height: 1.35; margin-bottom: 4px; word-break: keep-all; color: #fff;}
.cal-card .cc-r {display: grid; grid-template-columns: 3.2em 1fr; gap: 2px 8px; font-size: .88rem; line-height: 1.5;}
.cal-card .cc-r span:nth-child(odd) {color: #A9B5CA;}
.cal-card .cc-h2 {font-weight: 700;}
.cal-card .cc-tag {display: inline-block; font-size: .72rem; font-weight: 700; padding: 1px 7px; border-radius: 999px;
  margin-right: 6px; vertical-align: 1px;}
/* 칸 안의 구역 (시험 / 제조 / 분석): 비어 있어도 항상 보임 */
.st-key-calgrid div[class*="st-key-sec_"] {position: relative; z-index: 1; pointer-events: none; gap: 4px !important;
  border-radius: 9px; padding: 3px 4px 4px; background: var(--sec-bg); border: 1px solid var(--sec-line);}
.st-key-calgrid div[class*="st-key-sec_"] div[class*="st-key-er_"],
.st-key-calgrid div[class*="st-key-sec_"] div[class*="st-key-more_"] {pointer-events: auto;}
.st-key-calgrid div[class*="st-key-sec_"] [data-testid="stMarkdownContainer"]:has(.cal-sec-h) {margin-bottom: 0 !important;}
.cal-sec-h {display: flex; align-items: center; gap: 5px; font-size: .68rem; font-weight: 800; line-height: 1.5;
  color: var(--sec-fg); padding: 0 2px; letter-spacing: .02em;}
.cal-sec-h::before {content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--sec-fg);}
.cal-sec-h b {margin-left: auto; font-weight: 700; opacity: .8;}
.cal-sec-h.none {opacity: .5;}
.st-key-calgrid div[class*="st-key-sec_"]:not(:has(div[class*="st-key-er_"])):not(:has(div[class*="st-key-cf_"])) {
  background: transparent; border-style: dashed; padding: 2px 4px;}
.st-key-calgrid div[class*="st-key-cf_"] [data-testid="stMarkdownContainer"]:has(.cal-cf-q),
.st-key-calgrid div[class*="st-key-sec_"] [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
/* ✕ 누른 뒤 '삭제할까요?' */
.st-key-calgrid div[class*="st-key-cf_"] {pointer-events: auto; position: relative; z-index: 3; gap: 4px !important;
  background: #FFF1F1; border: 1px solid #F3B4B4; border-radius: 8px; padding: 5px 6px;}
.cal-cf-q {font-size: .7rem; line-height: 1.35; color: #8A2C2C; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.st-key-calgrid div[class*="st-key-cf_"] button {min-height: 0; height: 24px; padding: 0 4px; border-radius: 6px;}
.st-key-calgrid div[class*="st-key-cf_"] button p {font-size: .72rem !important; font-weight: 700;}
.st-key-calgrid div[class*="st-key-cfy_"] button {background: #E5484D !important; border-color: #E5484D !important; color: #fff !important;}
.st-key-calgrid div[class*="st-key-sec_test_"] {--sec-bg: #FDECEF99; --sec-line: #E35D7833; --sec-fg: #E35D78; --chip-fg: #E35D78;}
.st-key-calgrid div[class*="st-key-sec_make_"] {--sec-bg: #E5F6EC99; --sec-line: #1FA97133; --sec-fg: #1FA971; --chip-fg: #1FA971;}
.st-key-calgrid div[class*="st-key-sec_anal_"] {--sec-bg: #EEE9FD99; --sec-line: #7C5CE033; --sec-fg: #7C5CE0; --chip-fg: #7C5CE0;}
.st-key-calgrid div[class*="st-key-sec_etc_"] {--sec-bg: #EEF1F599; --sec-line: #8A97A833; --sec-fg: #8A97A8; --chip-fg: #8A97A8;}
/* 구분 필터 */
div[class*="st-key-cal_cats"] {margin: .1rem 0 .4rem;}
div[class*="st-key-cal_cats"] button {border-radius: 999px !important; font-weight: 600;}
/* 마우스를 올리면 뜨는 작은 설명 */
div[data-baseweb="tooltip"] [data-testid="stTooltipContent"] {max-width: 340px; padding: .55rem .75rem;
  font-size: .82rem; line-height: 1.65;}
div[data-baseweb="tooltip"] [data-testid="stTooltipContent"] hr {margin: .45rem 0; opacity: .5;}
div[data-baseweb="tooltip"] [data-testid="stTooltipContent"] p {margin: 0;}
/* 아래쪽에 떠 있는 작은 도구 막대 (선택·복사 상태) */
.st-key-cal_selbar, .st-key-cal_delbar {position: fixed !important; left: 50%; bottom: 26px; transform: translateX(-50%);
  z-index: 1000; width: auto !important; max-width: min(760px, calc(100vw - 32px)); flex-wrap: nowrap !important;
  padding: 6px 8px 6px 18px; border-radius: 999px; background: #26324A; color: #fff;
  box-shadow: 0 12px 30px rgba(15, 30, 60, .30); animation: calPop .18s ease-out;}
.st-key-cal_delbar {bottom: 84px; background: #fff; border: 1px solid #F3B4B4; box-shadow: 0 12px 30px rgba(180, 40, 40, .18);}
@keyframes calPop {from {opacity: 0; transform: translate(-50%, 8px);} to {opacity: 1; transform: translate(-50%, 0);}}
.st-key-cal_selbar [data-testid="stMarkdownContainer"], .st-key-cal_delbar [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
.st-key-cal_selbar p, .st-key-cal_delbar p {margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: .88rem;}
.st-key-cal_selbar p {color: #fff;} .st-key-cal_selbar p span {color: #9CCBFF !important;}
.st-key-cal_delbar p {color: #8A2C2C;}
.st-key-cal_selbar [data-testid="stElementContainer"]:has(button) {width: auto !important;}
.st-key-cal_selbar button {background: rgba(255, 255, 255, .08) !important; border: none !important; color: #fff !important;
  border-radius: 999px !important; min-height: 0; height: 34px; padding: 0 14px;}
.st-key-cal_selbar button:hover {background: rgba(255, 255, 255, .18) !important;}
.st-key-cal_selbar button p {font-size: .85rem;}
.st-key-cal_delbar button {border-radius: 999px !important; min-height: 0; height: 34px; padding: 0 16px;}
.st-key-cal_sel_clear button {padding: 0 10px !important;}
.st-key-cal_del_yes button {background: #E5484D !important; border-color: #E5484D !important; color: #fff !important;}
.st-key-calgrid div[class*="st-key-cell_"]:hover {border-color: var(--accent);}
.st-key-calgrid div[class*="st-key-cell_"] [data-testid="stVerticalBlock"] {gap: 3px;}
.st-key-calgrid button div[data-testid="stMarkdownContainer"] {width: 100%; min-width: 0; text-align: left;}
.st-key-calgrid button div[data-testid="stMarkdownContainer"] p {
  display: block; text-align: left; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
/* 날짜 머리 (누르면 그날 선택) */
.st-key-calgrid div[class*="st-key-day_"] button,
.st-key-calgrid div[class*="st-key-ent_"] button {justify-content: flex-start; text-align: left;}
.st-key-calgrid div[class*="st-key-day_"] button > div,
.st-key-calgrid div[class*="st-key-ent_"] button > div {width: 100%; min-width: 0; justify-content: flex-start;}
.st-key-calgrid div[class*="st-key-day_"] button p {font-size: 0.76rem; color: #6B7790;}
.st-key-calgrid div[class*="st-key-day_"] button strong {font-family: 'Nunito', 'IBM Plex Sans KR', sans-serif;
  font-size: 1.12rem; font-weight: 800; letter-spacing: -.01em; display: inline-flex; align-items: center;
  justify-content: center; min-width: 1.75em; height: 1.75em; border-radius: 999px; margin-right: 2px;}
.st-key-calgrid div[class*="st-key-day_"] button:hover strong {background: rgba(45, 143, 213, 0.12);}
/* 실적 한 줄 (누르면 이 실적 선택) */
.st-key-calgrid div[class*="st-key-ent_"] button {
  justify-content: flex-start; min-height: 0; padding: 4px 8px; border: none; border-radius: 8px;
  background: #fff; border-left: 3px solid var(--chip-fg, #3B82F6);
  box-shadow: 0 1px 2px rgba(20, 40, 80, .08);
  transition: transform .1s ease, box-shadow .1s ease;}
.st-key-calgrid div[class*="st-key-ent_"] button:hover {transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(20, 40, 80, .12); filter: saturate(1.15);}
.st-key-calgrid div[class*="st-key-ent_"] button p {font-size: 0.72rem; line-height: 1.38; color: #243042;}
.st-key-calgrid div[class*="st-key-ent_"] button p:first-child {font-weight: 600;}
/* 달력 모양: 둥근 흰 칸, 은은한 그림자, 주말은 옅은 색 */
.st-key-calgrid div[class*="st-key-cell_"] {background: #fff; border: 1px solid #E6EBF2 !important; border-radius: 14px !important;
  box-shadow: 0 1px 2px rgba(20, 40, 80, .04); transition: box-shadow .15s ease, border-color .15s ease;}
.st-key-calgrid div[class*="st-key-cell_"]:hover {box-shadow: 0 6px 16px rgba(20, 40, 80, .10);
  border-color: #C9D8EC !important;}
.st-key-calgrid .cal-wk {text-align: center; font-size: 1.02rem; font-weight: 800; letter-spacing: .04em;
  color: #4A5670; background: #EAEFF7; border-radius: 999px; padding: 6px 0; margin: 0 6px 4px;}
.st-key-calgrid .cal-wk.sat {color: #3D7BE0; background: #E3EEFD;}
.st-key-calgrid .cal-wk.sun {color: #E0566A; background: #FDE7EB;}
.st-key-calgrid .cal-out {min-height: 230px; border-radius: 14px; border: 1px dashed #E6EBF2; padding: 8px 10px;
  font-family: 'Nunito', sans-serif; font-weight: 800; font-size: 1.05rem; color: #C3CBD6; background: rgba(255,255,255,.4);}
.st-key-calgrid div[class*="st-key-more_"] p {font-size: 0.7rem; color: #777; margin: 0 0 0 4px;}
/* 휴대폰: 7칸을 한 줄에 유지한 작은 달력 (날짜·건수만, 누르면 아래에 그날 실적) */
.cal-mobile-hint {display: none;}
@media (max-width: 640px) {
  .st-key-calgrid div[class*="st-key-card"] {display: none !important;}
  .st-key-calgrid [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 3px !important;}
  .st-key-calgrid [data-testid="stColumn"] {min-width: 0 !important; width: auto !important; flex: 1 1 0 !important;}
  .st-key-calgrid div[class*="st-key-cell_"] {min-height: 54px; padding: 3px 2px; border-radius: 8px;}
  .st-key-calgrid div[class*="st-key-sec_"] {display: none !important;}
  .st-key-calgrid div[class*="st-key-day_"] button {padding: 4px 1px !important; justify-content: center !important;}
  .st-key-calgrid div[class*="st-key-day_"] button > div {justify-content: center !important;}
  .st-key-calgrid div[class*="st-key-day_"] button p {white-space: normal !important; font-size: .62rem; line-height: 1.25;
    text-align: center !important; overflow: visible;}
  .st-key-calgrid div[class*="st-key-day_"] button strong {display: block; font-size: .9rem;}
  .st-key-calgrid div[class*="st-key-day_"] button span {background: none !important; padding: 0 !important;}
  .st-key-calgrid div[class*="st-key-day_"] button div[data-testid="stMarkdownContainer"] {text-align: center;}
  .st-key-calnav .cal-title {min-width: 0; font-size: 1.05rem;}
  .cal-mobile-hint {display: block; font-size: .8rem; color: var(--muted); margin: .2rem 0 .4rem;}
}
</style>"""


def _cut(text: str, n: int) -> str:
    """n글자보다 길면 잘라서 … 를 붙임."""
    text = str(text).strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _md(text: str) -> str:
    """버튼 글자·툴팁이 마크다운으로 해석되지 않게."""
    for ch in "\\*_[]()#`~<>|":
        text = text.replace(ch, "\\" + ch)
    return text


def _hours(h: float) -> str:
    return f"{h:,.1f}".rstrip("0").rstrip(".") + "h"


def _shift_month(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1)


def _pick_day(day: dt.date) -> None:
    st.session_state.cal_day = day
    st.session_state.cal_month = day.replace(day=1)


def _day_rows(logs: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    """그날 하루짜리 실적 (사용시작일 = 사용종료일 = day)."""
    if logs.empty:
        return logs
    ts = pd.Timestamp(day)
    return logs[(logs["start_date"] == ts) & (logs["end_date"] == ts)]


def _paste_plan(src: list[dict], targets: list[dt.date], logs: pd.DataFrame) -> tuple[list[dict], int]:
    """src 실적을 targets 날짜에 붙여 넣을 목록. 그날 같은 장비·업체가 이미 있으면 건너뜀."""
    plan, skipped = [], 0
    for d in targets:
        there = _day_rows(logs, d)
        have = set(zip(there["equip_id"].astype(int), there["company"]))
        for r in src:
            if (int(r["equip_id"]), r["company"]) in have:
                skipped += 1
                continue
            rec = {k: r.get(k) for k in db.LOG_FIELDS}
            rec.update(start_date=d, end_date=d)
            plan.append(rec)
    return plan, skipped


def _record(row: dict, base: dict, comp_by_name: dict, eq_id: dict, cfg: dict) -> dict:
    """표 한 행 + (수정이면) 원래 실적 → 저장할 실적."""
    company = db.to_str(row.get("업체"))
    master = comp_by_name.get(company)
    rec = dict(base)
    rec.update(
        equip_id=eq_id.get(row.get("장비")),
        company=company,
        usage_type=db.to_str(row.get("활용유형")),
        purpose=db.to_str(row.get("사용목적")),
        hours=db.to_num(row.get("사용시간"), 0),
        samples=db.to_num(row.get("시료수"), 0),
        fee=db.to_num(row.get("사용료"), 0),
        etc=db.to_str(row.get("기타")),
        created_by=db.to_str(row.get("담당자")),
    )
    if master is not None:  # 사업자번호·업종은 항상 업체 목록 기준
        rec["brn"] = master["brn"]
        for k in ("industry", "item", "sub_item"):
            if master[k]:
                rec[k] = master[k]
    elif not company:
        rec["brn"] = ""
    for k, v in zip(("industry", "item", "sub_item"), DEFAULT_INDUSTRY):
        rec.setdefault(k, v)
        if not rec[k]:
            rec[k] = v
    old_ov, method, _ = seed.parse_detail(base.get("detail", ""))
    overview = db.to_str(row.get("지원개요"))
    rec["detail"] = seed.compose_detail(overview, method or "-", db.to_str(row.get("지원내용")))
    if not db.to_str(base.get("purpose_detail")) or db.to_str(base.get("purpose_detail")) == old_ov:
        rec["purpose_detail"] = overview
    rec.setdefault("dept", cfg.get("dept_default", ""))
    rec.setdefault("disclose", "N")
    rec.setdefault("include_holidays", "Y")
    return rec


def _cell_entries(in_month: pd.DataFrame, logs: pd.DataFrame, eq: pd.DataFrame) -> dict[dt.date, list[dict]]:
    """날짜별로 달력 칸에 보여 줄 실적 (장비, 업체, 그날 몫의 시간, 담당자, 기간 여부)."""
    if in_month.empty:
        return {}
    name_of = dict(zip(eq["id"].astype(int), eq["name"]))
    cat_of = dict(zip(eq["id"].astype(int), (_cat_of(u) for u in eq.get("use", pd.Series([""] * len(eq))))))
    info = logs.set_index("id")
    out: dict[dt.date, list[dict]] = {}
    for r in in_month.itertuples(index=False):
        if r.log_id not in info.index:
            continue
        lg = info.loc[r.log_id]
        multi = lg["start_date"] != lg["end_date"]
        rec = lg.to_dict() | {"id": int(r.log_id)}
        if multi:  # 기간 실적은 그날 몫만 하루짜리로 복사
            rec.update(hours=round(float(r.hours), 1), fee=round(float(r.fee)))
        out.setdefault(r.day.date(), []).append({
            "id": int(r.log_id), "rec": rec,
            "equip": name_of.get(int(r.equip_id), "?"), "company": db.to_str(lg["company"]) or "내부",
            "cat": cat_of.get(int(r.equip_id), "기타"),
            "hours": float(r.hours), "staff": db.to_str(lg["created_by"]),
            "period": f"{lg['start_date']:%m/%d}~{lg['end_date']:%m/%d}" if multi else "",
        })
    for v in out.values():
        v.sort(key=lambda e: (CAT_ORDER.index(e["cat"]), e["period"] != "", -e["hours"]))
    return out


def _day_head(d: dt.date, entries: list[dict], holiday: bool, today: bool) -> tuple[str, str | None]:
    """날짜 머리 글자와, 마우스를 올렸을 때 보일 그날 실적 전체."""
    num = f"**{d.day}**"
    if holiday or d.weekday() == 6:
        num = f":red[**{d.day}**]"
    elif d.weekday() == 5:
        num = f":blue[**{d.day}**]"  # 오늘은 CSS로 동그라미 표시
    total = sum(e["hours"] for e in entries)
    head = num + (f"\u2002{len(entries)}건 · {_hours(total)}" if entries else "")
    if not entries:
        return head, None
    tip = [f"**{d:%m/%d} ({WEEKDAYS[d.weekday()]})**\u2003:gray[{len(entries)}건 · {_hours(total)}]"]
    tip += [_entry_card(e) for e in entries]
    return head, "\n\n---\n\n".join(tip)


# 장비용도(장비 정보) → 달력 구분. 색은 구분마다 고정 (배경, 진한 색)
CATS = {"시험": ("#FDECEF", "#E35D78"), "제조": ("#E5F6EC", "#1FA971"), "분석": ("#EEE9FD", "#7C5CE0"),
        "기타": ("#EEF1F5", "#8A97A8")}
CAT_ORDER = list(CATS)
FIXED_CATS = ["시험", "제조", "분석"]  # 칸마다 비어 있어도 항상 보이는 구역
CAT_KEY = {"시험": "test", "제조": "make", "분석": "anal", "기타": "etc"}


def _cat_of(use: str) -> str:
    u = str(use or "").strip()
    if u in ("생산", "제조"):
        return "제조"
    return u if u in CATS else "기타"


def _card_html(d: dt.date, entries: list[dict]) -> str:
    """날짜 칸 위에 뜨는 카드 (그날 실적 전체를 큰 글씨로)."""
    e_ = html.escape
    total = sum(x["hours"] for x in entries)
    rows = []
    for x in entries:
        cells = [("업체", x["company"]), ("시간", _hours(x["hours"]))]
        if x["staff"]:
            cells.append(("담당", x["staff"]))
        if x["period"]:
            cells.append(("기간", x["period"]))
        grid = "".join(f"<span>{e_(k)}</span><span>{e_(str(v))}</span>" for k, v in cells)
        bg, fg = CATS[x["cat"]]
        tag = f"<span class='cc-tag' style='background:{bg};color:{fg}'>{x['cat']}</span>"
        rows.append(f"<div class='cc-e' style='border-left-color:{fg}'><div class='cc-n'>{tag}{e_(x['equip'])}</div>"
                    f"<div class='cc-r'>{grid}</div></div>")
    return (f"<div class='cal-card'><div class='cc-h'><span class='cc-d'>{d.month}월 {d.day}일 "
            f"({WEEKDAYS[d.weekday()]})</span><span class='cc-sum'>{len(entries)}건 · {_hours(total)}</span></div>"
            + "".join(rows) + "</div>")


def _entry_card(e: dict) -> str:
    """마우스를 올리면 뜨는 작은 카드: 장비명 굵게, 아래 줄에 업체·시간·담당자."""
    lines = [f"**{_md(e['equip'])}**",
             f":gray[업체]\u2003{_md(e['company'])}",
             f":gray[시간]\u2003**{_hours(e['hours'])}**"
             + (f"\u2003\u2003:gray[담당]\u2003{_md(e['staff'])}" if e["staff"] else "")]
    if e["period"]:
        lines.append(f":gray[기간]\u2003{e['period']}")
    return "  \n".join(lines)


def _entry_text(e: dict) -> str:
    extra = " · ".join(x for x in (e["staff"], f"기간 {e['period']}" if e["period"] else "") if x)
    return (f"{_md(e['equip'])} · {_md(e['company'])} · {_hours(e['hours'])}"
            + (f" ({_md(extra)})" if extra else ""))


def _reset_period_pick() -> None:
    st.session_state.cal_pnonce = st.session_state.get("cal_pnonce", 0) + 1  # 표 선택을 풀어 창이 다시 뜨지 않게


@st.dialog("기간 실적 고치기", width="medium", on_dismiss=_reset_period_pick)
def _edit_period(rec: dict, label_of: dict, comp_opts: list, staff_opts: list) -> None:
    eq_ids = list(label_of)
    eid = st.selectbox("장비", eq_ids, index=eq_ids.index(rec["equip_id"]) if rec["equip_id"] in eq_ids else 0,
                       format_func=label_of.get, key="pe_eq")
    c1, c2 = st.columns(2)
    start = c1.date_input("사용시작일", value=rec["start_date"].date(), format="YYYY-MM-DD", key="pe_s")
    end = c2.date_input("사용종료일", value=rec["end_date"].date(), format="YYYY-MM-DD", key="pe_e")
    comp = rec.get("company") or ""
    opts = [""] + comp_opts + ([comp] if comp and comp not in comp_opts else [])
    company = st.selectbox("업체", opts, index=opts.index(comp), format_func=lambda v: v or "(내부 사용)", key="pe_c")
    c1, c2, c3 = st.columns(3)
    hours = c1.number_input("사용시간(h)", min_value=0, step=1, value=int(rec["hours"]), key="pe_h")
    fee = c2.number_input("사용료(원)", min_value=0, step=1000, value=int(rec["fee"]), key="pe_f")
    samples = c3.number_input("시료수", min_value=0, step=1, value=int(rec["samples"]), key="pe_n")
    c1, c2, c3 = st.columns(3)
    purpose = c1.selectbox("사용목적", seed.PURPOSES, index=seed.PURPOSES.index(rec["purpose"])
                           if rec["purpose"] in seed.PURPOSES else 0, key="pe_p")
    utype = c2.selectbox("활용유형", seed.USAGE_TYPES, index=seed.USAGE_TYPES.index(rec["usage_type"])
                         if rec["usage_type"] in seed.USAGE_TYPES else 0, key="pe_u")
    sopts = staff_opts + ([rec["created_by"]] if rec["created_by"] and rec["created_by"] not in staff_opts else [])
    staff = c3.selectbox("담당자", sopts, index=sopts.index(rec["created_by"]) if rec["created_by"] in sopts else 0,
                         key="pe_w")
    new = {"equip_id": eid, "start_date": start, "end_date": end, "company": company, "hours": hours, "fee": fee,
           "samples": samples, "purpose": purpose, "usage_type": utype, "created_by": staff}
    b1, b2 = st.columns(2)
    if b1.button("저장", type="primary", icon=":material/save:", width="stretch", key="pe_save"):
        full = {k: rec.get(k) for k in db.LOG_FIELDS} | new
        if company != comp:
            m = {r["name"]: r for r in db.load_companies().to_dict("records")}.get(company)
            full["brn"] = m["brn"] if m is not None else ""
        errs = rules.validate(full)
        if errs:
            for e in errs:
                st.error(e)
            return
        db.update_logs({int(rec["id"]): full})
        st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
        st.session_state.cal_saved = "기간 실적을 고쳤습니다."
        st.rerun()
    if b2.button("이 실적 삭제", icon=":material/delete:", width="stretch", key="pe_del"):
        db.delete_logs([int(rec["id"])])
        st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
        st.session_state.cal_saved = "기간 실적을 지웠습니다. 실수면 '되돌리기'를 누르세요."
        st.rerun()


def _click_day(d: dt.date, clip: dict | None, logs: pd.DataFrame) -> None:
    """날짜 칸을 누름: 그날을 선택만 함 (붙여넣기는 Ctrl+V)."""
    _clear_sel()
    st.session_state.pop("cal_pick", None)
    _pick_day(d)


def _click_entry(d: dt.date, e: dict, clip: dict | None, logs: pd.DataFrame) -> None:
    """실적 한 줄을 누름: 이 실적을 선택만 함 (복사는 Ctrl+C)."""
    _clear_sel()
    st.session_state.cal_pick = {"day": d, "id": e["id"], "rec": e["rec"], "period": bool(e["period"]),
                                 "label": f"{e['equip']} · {e['company']} · {_hours(e['hours'])}"}
    _pick_day(d)


def _targets() -> list[dt.date]:
    """붙여 넣을 날짜: 드래그로 고른 날들, 없으면 선택한 날 하루."""
    days = _sel_days()
    if days:
        return days
    pick = st.session_state.get("cal_pick")
    if pick:
        return [pick["day"]]
    d = st.session_state.get("cal_day")
    return [d] if d else []


def _copy() -> None:
    """Ctrl+C: 선택한 실적 한 건, 또는 선택한 날(들)의 실적을 복사."""
    pick = st.session_state.get("cal_pick")
    if pick:
        st.session_state.cal_clip = {"from": pick["day"], "rows": [dict(pick["rec"], _off=0)],
                                     "label": pick["label"], "keys": [(pick["day"], pick["id"])]}
        st.session_state.cal_saved = f"{_cut(pick['label'], 30)} 복사했습니다. 붙여 넣을 날짜를 고르고 Ctrl+V."
        return
    days = _targets()
    if not days:
        return
    logs = db.load_logs()
    rows, keys = [], []
    for d in days:
        for r in _day_rows(logs, d).to_dict("records"):
            rows.append(dict(r, _off=(d - days[0]).days))
            keys.append((d, int(r["id"])))
    if not rows:
        st.session_state.cal_saved = "선택한 날에는 복사할 실적이 없습니다."
        return
    span = f"{days[0]:%m/%d}" + (f"~{days[-1]:%m/%d}" if len(days) > 1 else "")
    st.session_state.cal_clip = {"from": days[0], "rows": rows, "label": f"{span} 실적 {len(rows)}건", "keys": keys}
    st.session_state.cal_saved = f"{span} 실적 {len(rows)}건을 복사했습니다. 붙여 넣을 날짜를 고르고 Ctrl+V."


def _delete_ids(ids: list[int], label: str) -> int:
    if not ids:
        return 0
    with db.undo_group(label):
        n = db.delete_logs(ids)
    pick = st.session_state.get("cal_pick")
    if pick and int(pick["id"]) in set(ids):
        st.session_state.pop("cal_pick", None)
    st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
    return n


def _click_x(d: dt.date, e: dict) -> None:
    """✕: 그 자리에서 '삭제할까요?'를 한 번 더 물음."""
    st.session_state.cal_xconfirm = (d, e["id"])


def _cancel_x() -> None:
    st.session_state.pop("cal_xconfirm", None)


def _confirm_x(d: dt.date, e: dict) -> None:
    """삭제 확인: 이 실적 한 건을 지움 (되돌리기 가능)."""
    st.session_state.pop("cal_xconfirm", None)
    n = _delete_ids([e["id"]], f"{d:%m/%d} {_cut(e['equip'], 12)} 삭제")
    if n:
        st.session_state.cal_saved = f"{d:%m/%d} {_cut(e['equip'], 20)} 실적을 지웠습니다. 실수면 Ctrl+Z 또는 '되돌리기'."


def _sel_days() -> list[dt.date]:
    return list(st.session_state.get("cal_sel") or [])


def _delete_days(days: list[dt.date]) -> None:
    """선택한 날들의 하루짜리 실적을 지움. 여러 날에 걸친 기간 실적은 남김."""
    logs = db.load_logs()
    ids, kept = [], 0
    for d in days:
        rows = _day_rows(logs, d)
        ids += [int(i) for i in rows["id"]]
        ts = pd.Timestamp(d)
        if not logs.empty:
            kept += int(((logs["start_date"] <= ts) & (logs["end_date"] >= ts)).sum()) - len(rows)
    span = f"{days[0]:%m/%d}" + (f"~{days[-1]:%m/%d}" if len(days) > 1 else "")
    n = _delete_ids(ids, f"{span} 실적 삭제")
    msg = f"{span} 실적 {n}건을 지웠습니다. 실수면 Ctrl+Z 또는 '되돌리기'." if n else f"{span}에는 지울 실적이 없습니다."
    if kept:
        msg += f" (여러 날에 걸친 기간 실적 {kept}건은 그대로 두었습니다)"
    st.session_state.cal_saved = msg


def _paste_days(days: list[dt.date] | None = None) -> None:
    """Ctrl+V: 엑셀처럼 붙여넣기. 한 날을 복사했으면 선택한 모든 날에, 여러 날을 복사했으면 첫 날부터 같은 간격으로."""
    clip = st.session_state.get("cal_clip")
    if not clip:
        st.session_state.cal_saved = "먼저 실적이나 날짜를 고르고 Ctrl+C로 복사하세요."
        return
    days = days or _targets()
    if not days:
        return
    multi = any(r.get("_off", 0) for r in clip["rows"])
    logs = db.load_logs()
    plan, skipped, filled = [], 0, set()
    starts = days[:1] if multi else days
    for t in starts:
        for r in clip["rows"]:
            d = t + dt.timedelta(days=int(r.get("_off", 0)))
            p, sk = _paste_plan([r], [d], logs)
            plan += p
            skipped += sk
            if p:
                filled.add(d)
    span = f"{min(filled):%m/%d}" + (f"~{max(filled):%m/%d}" if len(filled) > 1 else "") if filled else ""
    with db.undo_group(f"{span} 붙여넣기"):
        added = db.insert_logs(plan) if plan else 0
    st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
    st.session_state.cal_saved = (f"{span}에 {added}건 붙여 넣었습니다"
                                  + (f" (같은 장비·업체가 이미 있는 {skipped}건은 건너뜀)" if skipped else "")) if added else \
        "같은 장비·업체가 이미 있어 붙여 넣지 않았습니다"


def _ask_delete(days: list[dt.date] | None = None) -> None:
    """Delete 키 / 선택 막대의 '삭제': 바로 지우지 않고 '삭제할까요?'를 먼저 띄움."""
    days = days or _sel_days()
    pick = st.session_state.get("cal_pick")
    if days:
        ask = {"kind": "days", "days": days}
    elif pick and not pick["period"]:
        ask = {"kind": "clip", "id": int(pick["id"]), "day": pick["day"], "label": pick["label"]}
    elif st.session_state.get("cal_day"):
        ask = {"kind": "days", "days": [st.session_state.cal_day]}
    else:
        return
    if ask["kind"] == "days":
        logs = db.load_logs()
        n = sum(len(_day_rows(logs, d)) for d in ask["days"])
        if not n:
            return
        a, b = ask["days"][0], ask["days"][-1]
        span = f"{a:%m/%d}" if a == b else f"{a:%m/%d}~{b:%m/%d}"
        ask["text"] = f"{span}의 실적 {n}건을 삭제할까요?"
    else:
        ask["text"] = f"{ask['day']:%m/%d} {_cut(ask['label'], 24)}을(를) 삭제할까요?"
    st.session_state.cal_delask = ask


def _do_pending_delete() -> None:
    ask = st.session_state.pop("cal_delask", None)
    if not ask:
        return
    if ask["kind"] == "days":
        _delete_days(ask["days"])
    else:
        n = _delete_ids([ask["id"]], f"{ask['day']:%m/%d} 실적 삭제")
        if n:
            st.session_state.cal_saved = f"{ask['day']:%m/%d} {_cut(ask['label'], 24)}을(를) 지웠습니다. 실수면 Ctrl+Z."


def _cancel_delete() -> None:
    st.session_state.pop("cal_delask", None)


def _on_cmd() -> None:
    """화면의 키보드·드래그 동작이 숨은 입력칸으로 보내는 명령을 처리."""
    raw = str(st.session_state.get("cal_cmd") or "")
    parts = raw.split("|")
    cmd = parts[0]
    if cmd == "sel" and len(parts) >= 3:
        a, b = sorted([dt.date.fromisoformat(parts[1]), dt.date.fromisoformat(parts[2])])
        st.session_state.cal_sel = [a + dt.timedelta(days=i) for i in range((b - a).days + 1)]
        st.session_state.pop("cal_pick", None)
        st.session_state.cal_day = b if b.month == st.session_state.get("cal_month", b).month else a
    elif cmd == "del":
        if st.session_state.get("cal_delask"):  # 확인창이 떠 있을 때 Delete를 한 번 더 → 삭제
            _do_pending_delete()
        else:
            _ask_delete()
    elif cmd == "copy":
        _copy()
    elif cmd == "paste":
        _paste_days()
    elif cmd == "esc":
        if st.session_state.pop("cal_delask", None) or st.session_state.pop("cal_xconfirm", None):
            return
        st.session_state.pop("cal_sel", None)
        st.session_state.pop("cal_pick", None)
        st.session_state.pop("cal_clip", None)


def _clear_sel() -> None:
    st.session_state.pop("cal_sel", None)


def _clear_all() -> None:
    for k in ("cal_sel", "cal_pick", "cal_clip"):
        st.session_state.pop(k, None)


def _drop_clip() -> None:
    st.session_state.pop("cal_clip", None)


KEYS_JS = r"""
<script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  // 화면을 다시 그리면 이 iframe이 새로 생기므로, 예전 iframe이 단 이벤트는 떼고 새로 담
  const old = win.__calKeys || [];
  old.forEach(([t, f, o]) => doc.removeEventListener(t, f, o));
  const mine = [];
  const on = (t, f, o) => { doc.addEventListener(t, f, o); mine.push([t, f, o]); };
  win.__calKeys = mine;
  const send = (v) => {
    const inp = doc.querySelector('.st-key-cal_cmd input');
    if (!inp) return;
    const set = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, 'value').set;
    set.call(inp, v + '|' + Date.now());
    inp.dispatchEvent(new win.Event('input', {bubbles: true}));
    inp.dispatchEvent(new win.KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
  };
  const onCal = () => !!doc.querySelector('.st-key-calgrid');
  const typing = (el) => el && (el.closest('input, textarea, select, [contenteditable="true"]') ||
                                 el.closest('[data-testid="stDataFrame"], [data-testid="stDataEditor"], [role="dialog"]'));
  const cellOf = (el) => el && el.closest && el.closest('.st-key-calgrid div[class*="st-key-cell_"]');
  const dateOf = (cell) => { const m = cell && cell.className.match(/st-key-cell_(\d{4}-\d{2}-\d{2})/); return m ? m[1] : null; };
  let start = null, cur = null, dragging = false;
  const paint = () => {
    doc.querySelectorAll('.st-key-calgrid .cal-drag').forEach(c => c.classList.remove('cal-drag'));
    if (!dragging) return;
    const [a, b] = [start, cur].sort();
    doc.querySelectorAll('.st-key-calgrid div[class*="st-key-cell_"]').forEach(c => {
      const d = dateOf(c); if (d && d >= a && d <= b) c.classList.add('cal-drag');
    });
  };
  on('mousedown', (e) => {
    if (e.button !== 0) return;
    const c = cellOf(e.target); start = dateOf(c); cur = start; dragging = false;
  }, true);
  on('mouseover', (e) => {
    if (!start) return;
    const d = dateOf(cellOf(e.target));
    if (d && d !== cur) { cur = d; if (cur !== start) dragging = true; paint(); }
  }, true);
  on('mouseup', (e) => {
    if (start && dragging) {
      e.preventDefault(); e.stopPropagation();
      const swallow = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
      doc.addEventListener('click', swallow, {capture: true, once: true});
      setTimeout(() => doc.removeEventListener('click', swallow, true), 300);
      send('sel|' + start + '|' + cur);
    }
    start = null; dragging = false;
  }, true);
  on('keydown', (e) => {
    if (!onCal() || typing(e.target)) return;
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); send('del'); }
    else if (mod && (e.key === 'v' || e.key === 'V')) { e.preventDefault(); send('paste'); }
    else if (mod && (e.key === 'c' || e.key === 'C')) {
      if (String(win.getSelection ? win.getSelection() : '').trim()) return;  // 글자를 드래그해 둔 경우는 보통 복사
      e.preventDefault(); send('copy');
    }
    else if (mod && (e.key === 'z' || e.key === 'Z')) {
      const b = doc.querySelector('.st-key-undo_top button, .st-key-undo_side button');
      if (b) { e.preventDefault(); b.click(); }
    }
    else if (e.key === 'Escape') { send('esc'); }
  }, true);
})();
</script>
"""


def _day_cell(col, d: dt.date, entries: list[dict], *, selected: bool, holiday: bool, today: bool,
              clip: dict | None, logs: pd.DataFrame, shown_cats: list[str]) -> None:
    cell = col.container(border=True, key=f"cell_{d}")
    head, _ = _day_head(d, entries, holiday, today)
    # 날짜 버튼은 칸 전체를 덮음 → 칸 어디를 눌러도 선택/붙여넣기 (CSS 참고)
    cell.button(head, key=f"day_{d}", type="tertiary", width="stretch",
                on_click=_click_day, args=(d, clip, logs))
    cats = [c for c in shown_cats if c in FIXED_CATS or any(e["cat"] == c for e in entries)]
    for c in cats:
        ents = [e for e in entries if e["cat"] == c]
        sec = cell.container(key=f"sec_{CAT_KEY[c]}_{d}")
        hours = f"{_hours(sum(e['hours'] for e in ents))}" if ents else ""
        sec.markdown(f"<div class='cal-sec-h{'' if ents else ' none'}'>{c}<b>{hours}</b></div>",
                     unsafe_allow_html=True)
        for e in ents[:CELL_LINES]:
            label = f"{_md(e['equip'])}\n\n{_hours(e['hours'])} · {_md(e['company'])}"
            if st.session_state.get("cal_xconfirm") == (d, e["id"]):
                cf = sec.container(key=f"cf_{d}_{e['id']}")
                cf.markdown(f"<div class='cal-cf-q'><b>{html.escape(_cut(e['equip'], 14))}</b><br>삭제할까요?</div>",
                            unsafe_allow_html=True)
                with cf.container(horizontal=True, gap="small"):
                    st.button("삭제", key=f"cfy_{d}_{e['id']}", type="primary", width="stretch",
                              on_click=_confirm_x, args=(d, e))
                    st.button("취소", key=f"cfn_{d}_{e['id']}", width="stretch", on_click=_cancel_x)
                continue
            row = sec.container(key=f"er_{d}_{e['id']}")
            row.button(label, key=f"ent_{d}_{e['id']}", width="stretch",
                       on_click=_click_entry, args=(d, e, clip, logs))
            if not e["period"]:  # 기간 실적은 아래 '기간 실적'에서 고침
                row.button("", icon=":material/close:", key=f"x_{d}_{e['id']}", help="이 실적 삭제",
                           on_click=_click_x, args=(d, e))
        if len(ents) > CELL_LINES:
            sec.container(key=f"more_{d}_{CAT_KEY[c]}").markdown(f"+{len(ents) - CELL_LINES}건 더")
    if entries:
        side = "r" if d.weekday() >= 4 else ""  # 오른쪽 칸은 카드를 왼쪽으로 펼침
        cell.container(key=f"card{side}_{d}").markdown(_card_html(d, entries), unsafe_allow_html=True)


def render(header: bool = True) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if header:
        page_header("달력 입력", "실적")
    msg = st.session_state.pop("cal_saved", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")

    cfg = db.get_settings()
    eq = db.load_equipment()
    comp = db.load_companies()
    logs = db.load_logs()

    today = dt.date.today()
    day: dt.date = st.session_state.setdefault("cal_day", today)
    month: dt.date = st.session_state.setdefault("cal_month", day.replace(day=1))

    # ── 달력 ──────────────────────────────────────────────
    with st.container(key="calnav", horizontal=True, vertical_alignment="center", gap="small"):
        if st.button("", icon=":material/chevron_left:", key="cal_prev", help="이전 달"):
            st.session_state.cal_month = _shift_month(month, -1)
            st.rerun()
        st.markdown(f"<div class='cal-title'><span style='opacity:.55;font-size:.8em'>{month.year}</span>&nbsp; "
                    f"<span style='color:var(--accent)'>{month.month}월</span></div>", unsafe_allow_html=True)
        if st.button("", icon=":material/chevron_right:", key="cal_next", help="다음 달"):
            st.session_state.cal_month = _shift_month(month, 1)
            st.rerun()
        if st.button("오늘", key="cal_today", icon=":material/today:"):
            _pick_day(today)
            st.rerun()

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
    hol = kr_holidays({weeks[0][0].year, weeks[-1][-1].year, today.year, today.year + 1})
    daily = expand_daily(logs, cfg.get("alloc_mode", "spread"))
    in_month = daily[(daily["day"] >= pd.Timestamp(weeks[0][0])) & (daily["day"] <= pd.Timestamp(weeks[-1][-1]))]
    by_day = _cell_entries(in_month, logs, eq)
    present = FIXED_CATS + (["기타"] if any(e["cat"] == "기타" for v in by_day.values() for e in v) else [])
    shown = st.pills("구분", present, selection_mode="multi", default=present, key=f"cal_cats_{month}",
                     label_visibility="collapsed",
                     format_func=lambda c: f"{c} {sum(e['cat'] == c for dd, v in by_day.items() if dd.month == month.month for e in v)}건")
    pill_css = ""
    for i, c in enumerate(present, start=1):
        bg, fg = CATS[c]
        b = f'div[class*="st-key-cal_cats"] [data-testid="stButtonGroup"] button:nth-of-type({i})'
        pill_css += (f"{b} {{border-color: {fg}55 !important; color: {fg} !important;}} "
                     f"{b}[kind$='Active'] {{background: {bg} !important; border-color: {fg} !important;}} "
                     f"{b} p::before {{content: ''; display: inline-block; width: .55em; height: .55em; border-radius: 50%; "
                     f"background: {fg}; margin-right: .4em; vertical-align: .05em;}}")
    st.markdown(f"<style>{pill_css}</style>", unsafe_allow_html=True)
    shown_cats = [c for c in present if c in (shown or [])]
    by_day = {dd: [e for e in v if e["cat"] in shown_cats] for dd, v in by_day.items()}

    # ── 복사 / 붙여넣기 ─────────────────────────────────────
    clip = st.session_state.get("cal_clip")
    if clip and "keys" not in clip:  # 예전 방식으로 복사해 둔 것은 버림
        st.session_state.pop("cal_clip", None)
        clip = None
    pick = st.session_state.get("cal_pick")
    if pick and pick["day"].replace(day=1) != month:
        pick = None
    sel_days = [d for d in _sel_days() if d.month == month.month]
    if sel_days or pick or clip:
        with st.container(key="cal_selbar", horizontal=True, vertical_alignment="center", gap="small"):
            if sel_days:
                what = f"{sel_days[0]:%m/%d}~{sel_days[-1]:%m/%d} {len(sel_days)}일 선택"
            elif pick:
                what = f"{_cut(pick['label'], 30)} 선택"
            else:
                what = "붙여 넣을 날짜를 고르세요"
            if clip and not (sel_days or pick):
                st.markdown(f":blue[:material/content_paste: 복사됨]\u2002{_md(_cut(clip['label'], 26))}"
                            "\u2003:blue[날짜를 고르고 Ctrl+V]", width="content")
            else:
                st.markdown(f"**{_md(what)}**" + ("\u2003:blue[복사됨]" if clip else ""), width="content")
            if sel_days or pick:
                st.button("복사", icon=":material/content_copy:", key="cal_sel_copy", on_click=_copy,
                          help="Ctrl+C")
            if clip:
                st.button("붙여넣기", icon=":material/content_paste:", key="cal_sel_paste",
                          on_click=_paste_days, help="Ctrl+V")
            if sel_days or (pick and not pick["period"]):
                st.button("삭제", icon=":material/delete:", key="cal_sel_del", on_click=_ask_delete,
                          args=(sel_days or None,), help="Delete")
            st.button("", icon=":material/close:", key="cal_sel_clear", on_click=_clear_all, help="닫기 (Esc)")
    ask = st.session_state.get("cal_delask")
    if ask:
        with st.container(key="cal_delbar", horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f":material/delete: **{_md(ask['text'])}**\u2003:gray[Delete 한 번 더 · Esc 취소]",
                        width="content")
            st.button("삭제", key="cal_del_yes", type="primary", on_click=_do_pending_delete)
            st.button("취소", key="cal_del_no", on_click=_cancel_delete)
    st.text_input("cmd", key="cal_cmd", on_change=_on_cmd, label_visibility="collapsed")
    import streamlit.components.v1 as components
    components.html(KEYS_JS, height=0)

    grid = st.container(key="calgrid")
    sel = "".join(f".st-key-cell_{d} {{background: rgba(45, 143, 213, 0.14) !important; border-color: var(--accent) !important;}}"
                  for d in sel_days)
    for week in weeks:
        if week[5].month == month.month:
            sel += f" .st-key-cell_{week[5]} {{background: #F5F8FF !important;}}"
        if week[6].month == month.month:
            sel += f" .st-key-cell_{week[6]} {{background: #FFF6F7 !important;}}"
    sel += (f" .st-key-day_{today} button strong {{background: var(--accent) !important; color: #fff !important; "
            "box-shadow: 0 2px 6px rgba(45, 143, 213, .35);}")
    sel += (f".st-key-cell_{day} {{border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent);}}")
    if pick:  # 선택한 실적: 파란 테두리
        sel += (f" .st-key-ent_{pick['day']}_{pick['id']} button {{box-shadow: 0 0 0 2px var(--accent) !important;"
                " background: #EAF3FD !important;}")
    if clip:  # 복사한 실적: 엑셀처럼 움직이는 점선
        for kd, kid in clip["keys"]:
            sel += f" .st-key-ent_{kd}_{kid} button {{outline: 2px dashed var(--accent); outline-offset: 1px; animation: calAnts .9s linear infinite;}}"
    grid.markdown(f"<style>{sel}</style>", unsafe_allow_html=True)
    head = grid.columns(7)
    for i, w in enumerate(WEEKDAYS):
        cls = " sun" if i == 6 else (" sat" if i == 5 else "")
        head[i].markdown(f"<div class='cal-wk{cls}'>{w}</div>", unsafe_allow_html=True)
    for week in weeks:
        cols = grid.columns(7)
        for i, d in enumerate(week):
            if d.month != month.month:
                cols[i].markdown(f"<div class='cal-out'>{d.day}</div>", unsafe_allow_html=True)
                continue
            _day_cell(cols[i], d, by_day.get(d, []), selected=d == day, holiday=d in hol, today=d == today,
                      clip=clip, logs=logs, shown_cats=shown_cats)
    st.markdown("<div class='cal-mobile-hint'>날짜를 누르면 아래에 그날 실적이 나옵니다. "
                "다른 날로 복사는 '실적 목록'의 복제를 쓰세요.</div>", unsafe_allow_html=True)

    # ── 선택한 날 입력 ─────────────────────────────────────
    st.divider()
    st.subheader(f"{day:%Y-%m-%d} ({WEEKDAYS[day.weekday()]}) 입력",
                 help="맨 아래 빈 행에 입력하면 추가, '삭제' 칸에 체크하면 삭제. 다 고친 뒤 저장을 누르세요. "
                      "달력에서 실적이나 날짜를 고르고 Ctrl+C, 다른 날짜를 고르고 Ctrl+V로 복사할 수 있습니다.")

    ts = pd.Timestamp(day)
    rows = _day_rows(logs, day)
    period = logs[(logs["start_date"] <= ts) & (logs["end_date"] >= ts)] if not logs.empty else logs
    period = period.drop(rows.index) if not period.empty else period

    active = eq[(eq["retired_on"].isna() | (eq["retired_on"] >= ts)) &
                (eq["acquired_on"].isna() | (eq["acquired_on"] <= ts))]
    label_of = dict(zip(eq["id"], eq["label"]))
    eq_id = dict(zip(eq["label"], eq["id"]))
    eq_opts = list(active["label"]) + [label_of[i] for i in rows["equip_id"] if i in label_of
                                       and label_of[i] not in set(active["label"])]
    comp_by_name = {r["name"]: r for r in comp.to_dict("records")}
    comp_opts = list(comp_by_name) + sorted({c for c in rows["company"] if c and c not in comp_by_name})

    staff_opts = db.staff_names(list(rows["created_by"]))
    missing = [name for name, empty in (("장비", eq.empty), ("담당자", not staff_opts)) if empty]
    if missing:
        st.warning(f"등록된 {'·'.join(missing)}이(가) 없어 새로 입력할 수 없습니다. "
                   f"{', '.join(m + ' 정보' for m in missing)} 메뉴에서 먼저 등록하세요.")
    added = st.session_state.pop("company_added", None)
    if added:
        st.toast(f"'{added}' 업체를 등록했습니다. '업체' 칸에서 고르세요.", icon=":material/check_circle:")
    last_staff = st.session_state.get("last_staff") or st.session_state.get("me")

    view = pd.DataFrame({
        "id": rows["id"].astype("Int64"),
        "장비": rows["equip_id"].map(label_of),
        "업체": rows["company"].replace("", None),
        "담당자": rows["created_by"].replace("", None),
        "활용유형": rows["usage_type"], "사용목적": rows["purpose"],
        "사용시간": rows["hours"].astype(int), "시료수": rows["samples"].astype(int), "사용료": rows["fee"].astype(int),
        "지원개요": [seed.parse_detail(t)[0] for t in rows["detail"]],
        "지원내용": [seed.parse_detail(t)[2] for t in rows["detail"]],
        "기타": rows["etc"],
    }).reset_index(drop=True)
    # 빈 날은 열 형식을 알 수 없어 편집기가 오류를 내므로 형식을 고정
    view = view.astype({c: "string" for c in ("장비", "업체", "담당자", "활용유형", "사용목적", "지원개요", "지원내용", "기타")}
                       | {c: "Int64" for c in ("id", "사용시간", "시료수", "사용료")})
    view.insert(0, "삭제", False)

    ver = st.session_state.setdefault("cal_ver", 0)
    edited = st.data_editor(
        view, key=f"cal_ed_{day}_{ver}", num_rows="dynamic", hide_index=True, width="stretch",
        column_order=[c for c in view.columns if c != "id"],
        column_config={
            "삭제": st.column_config.CheckboxColumn(width="small", default=False,
                                                  help="지울 행에 체크하고 저장하세요. 실수하면 '되돌리기'로 살릴 수 있습니다."),
            "장비": st.column_config.SelectboxColumn(options=eq_opts, required=True, width="large"),
            "업체": st.column_config.SelectboxColumn(options=comp_opts, width="medium",
                                                   help="내부 사용이면 비워 두세요. 목록에 없으면 '기준 정보 › 업체'에서 추가합니다."),
            "담당자": st.column_config.SelectboxColumn(options=staff_opts, required=True,
                                                    default=last_staff if last_staff in staff_opts else None,
                                                    help="목록에 없으면 '기준 정보 › 담당자'에서 추가합니다."),
            "활용유형": st.column_config.SelectboxColumn(options=seed.USAGE_TYPES, required=True, default="외부"),
            "사용목적": st.column_config.SelectboxColumn(options=seed.PURPOSES, required=True, default="생산"),
            "사용시간": st.column_config.NumberColumn("사용시간(h)", min_value=0, max_value=24, step=1, format="%d",
                                                  required=True),
            "시료수": st.column_config.NumberColumn(min_value=0, step=1, format="%d", default=0),
            "사용료": st.column_config.NumberColumn("사용료(원)", min_value=0, step=1000, format="%d", default=0),
            "지원개요": st.column_config.TextColumn(width="medium"),
            "지원내용": st.column_config.TextColumn(width="medium"),
        },
    )

    orig = {int(r["id"]): r for r in rows.to_dict("records")}
    view_by_id = {int(r["id"]): r for r in view.to_dict("records")}
    new_rows, changed, kept = [], {}, set()
    for r in edited.to_dict("records"):
        rid = r.get("id")
        gone = bool(r.get("삭제")) and not pd.isna(r.get("삭제"))
        if rid is None or pd.isna(rid):
            if db.to_str(r.get("장비")) and not gone:
                new_rows.append(r)
            continue
        rid = int(rid)
        if gone:
            continue
        kept.add(rid)
        a = {k: db.to_str(r.get(k)) for k in FIELDS}
        b = {k: db.to_str(view_by_id[rid].get(k)) for k in FIELDS}
        if a != b:
            changed[rid] = r
    removed = [i for i in orig if i not in kept]

    dirty = bool(new_rows or changed or removed)
    confirm = True
    c1, c3, c2 = st.columns([1, 1.2, 2.8])
    if c3.button("새 업체 등록", icon=":material/add_business:", width="stretch", key="cal_new_comp",
                 help="목록에 없는 업체를 바로 등록합니다. 등록하면 '업체' 칸에서 고를 수 있습니다."):
        new_company_dialog()
    if c1.button("저장", icon=":material/save:", type="primary", disabled=not dirty or not confirm, width="stretch"):
        errors, inserts, updates = [], [], {}
        base_new = {"start_date": day, "end_date": day}
        for r in new_rows:
            rec = _record(r, base_new, comp_by_name, eq_id, cfg)
            errors += [f"[새 행 · {r.get('장비')}] {e}" for e in rules.validate(rec)]
            if not rec["created_by"]:
                errors.append(f"[새 행 · {r.get('장비')}] 담당자를 선택하세요.")
            inserts.append(rec)
        for rid, r in changed.items():
            base = {k: orig[rid].get(k) for k in db.LOG_FIELDS if k in orig[rid]}
            base.update(start_date=day, end_date=day)
            rec = _record(r, base, comp_by_name, eq_id, cfg)
            errors += [f"[{r.get('장비')}] {e}" for e in rules.validate(rec)]
            if not rec["created_by"]:
                errors.append(f"[{r.get('장비')}] 담당자를 선택하세요.")
            updates[rid] = rec
        # 같은 장비를 하루 24시간 넘게 쓸 수는 없음 (저장된 행 + 새 행 기준)
        per_equip: dict[int, float] = {}
        for rec in list(inserts) + list(updates.values()):
            per_equip[rec["equip_id"]] = per_equip.get(rec["equip_id"], 0) + db.to_num(rec["hours"], 0)
        for rid, r in orig.items():
            if rid not in updates and rid not in removed:
                per_equip[int(r["equip_id"])] = per_equip.get(int(r["equip_id"]), 0) + db.to_num(r["hours"], 0)
        for eid, h in per_equip.items():
            if h > 24:
                errors.append(f"[{label_of.get(eid, eid)}] 하루 사용시간 합계가 {h:,.0f}h로 24h를 넘습니다.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            with db.undo_group(f"{day:%m/%d} 저장"):
                n_in = db.insert_logs(inserts)
                n_up = db.update_logs(updates) if updates else 0
                n_del = db.delete_logs(removed)
            if inserts:
                st.session_state.last_staff = inserts[-1]["created_by"]
            st.session_state.cal_ver = ver + 1
            st.session_state.cal_saved = f"{day:%m/%d} 저장 · 추가 {n_in}건 · 수정 {n_up}건 · 삭제 {n_del}건"
            st.rerun()
    if dirty:
        c2.caption(f"저장 안 된 변경: 추가 {len(new_rows)} · 수정 {len(changed)} · 삭제 {len(removed)}")

    if not period.empty:
        with st.expander(f"이 날이 포함된 기간 실적 {len(period)}건 · 행을 누르면 고칠 수 있습니다", expanded=False):
            pv = period.reset_index(drop=True)
            ev = st.dataframe(pd.DataFrame({
                "장비": pv["equip_id"].map(label_of), "업체": pv["company"].replace("", "(내부)"),
                "시작일": pv["start_date"].dt.date, "종료일": pv["end_date"].dt.date,
                "사용시간(전체)": pv["hours"].astype(int), "담당자": pv["created_by"],
            }), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                key=f"cal_period_{day}_{ver}_{st.session_state.get('cal_pnonce', 0)}")
            picked = ev.selection.rows if ev else []
            if picked:
                _edit_period(pv.iloc[picked[0]].to_dict(), label_of, list(comp_by_name), staff_opts)
