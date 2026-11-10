"""달력으로 하루 단위 실적을 입력하고, 하루치 입력을 다른 날로 복사하는 화면."""
from __future__ import annotations

import calendar
import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import chargers as chg, db, rules, seed
from core import period as per
from core.calc import expand_daily, kr_holidays
from ui_style import T, page_header
from views.common import new_company_dialog, num_input

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
DEFAULT_INDUSTRY = ("전기전자", "이차전지_에너지", "이차전지")

# 표 열 이름 → 내부 키
FIELDS = {
    "장비": "equip_label", "업체": "company", "담당자": "created_by", "활용유형": "usage_type", "사용목적": "purpose",
    "사용시간": "hours", "시료수": "samples", "사용료": "fee",
    "지원개요": "overview", "지원내용": "content", "기타": "etc",
}


CELL_LINES = 3  # 달력 칸에 바로 보여 줄 실적 수 (나머지는 "+N")
CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@700;800&display=swap');
.block-container {padding-top: 2.5rem;}
.st-key-calgrid [data-testid="stHorizontalBlock"] {gap: 0.4rem;}
/* 달 이동 줄 */
.st-key-calnav {margin-bottom: .8rem; align-items: center;}
.st-key-calnav .cal-title {font-family: 'Nunito', 'Pretendard Variable', 'Pretendard', sans-serif; font-size: 1.45rem; font-weight: 800;
  color: var(--ink); min-width: 8.5rem; text-align: center;
  line-height: 2.25rem;}
.st-key-calnav [data-testid="stElementContainer"]:has(.cal-title) {width: auto !important; flex: none;}
.st-key-calnav [data-testid="stMarkdownContainer"] {margin: 0;}
.st-key-calnav div[class*="st-key-cal_prev"] button, .st-key-calnav div[class*="st-key-cal_next"] button {
  width: 2.25rem; height: 2.25rem; min-height: 0; padding: 0; border-radius: 6px;}
.st-key-calnav div[class*="st-key-cal_today"] {margin-left: auto;}
/* 화면 폭을 넓게 쓰고, 넓은 화면에서는 달력 오른쪽에 입력 카드 */
/* 좁은 화면: 입력 카드는 오른쪽에 떠 있는 서랍처럼 */
@media (max-width: 1500px) {
  .st-key-calwrap > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:has(.st-key-ep_panel)) {
    width: 100% !important; flex: 1 1 100% !important;}
  .st-key-calwrap > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.st-key-ep_panel) {
    position: fixed !important; right: 16px; top: 4.2rem; width: 380px !important; flex: none !important; z-index: 900;}
  .st-key-ep_panel {box-shadow: 0 18px 48px rgba(15, 30, 60, .25) !important;}
}
/* 입력 카드는 화면을 내려도 따라옴 (길면 카드 안에서 스크롤) */
.st-key-calwrap > [data-testid="stHorizontalBlock"] {align-items: stretch !important;}
.st-key-calwrap [data-testid="stColumn"]:has(.st-key-ep_panel) > [data-testid="stVerticalBlock"] {height: 100%;}
.st-key-calwrap [data-testid="stColumn"]:has(.st-key-ep_panel) {min-width: 360px;}
.st-key-ep_panel {position: sticky !important; top: 4.2rem; max-height: calc(100vh - 5.2rem); overflow-y: auto !important;
  scrollbar-width: thin; animation: epIn .18s ease-out;}
@keyframes epIn {from {opacity: 0; transform: translateX(10px);} to {opacity: 1; transform: none;}}
.st-key-ep_panel {background: var(--panel); border: none; border-radius: 20px; padding: 16px 16px 14px;
  box-shadow: 0 2px 4px rgba(30, 50, 90, .04), 0 12px 32px rgba(30, 50, 90, .08); gap: .45rem;}
.st-key-ep_close {width: auto !important;}
.st-key-ep_close button {height: 38px; width: 38px; padding: 0; border-radius: 12px; border: none; background: #26334D;}
.st-key-ep_form {gap: .45rem !important;}
.st-key-ep_form [data-testid="stWidgetLabel"] {margin-bottom: 0; min-height: 0;}
.st-key-ep_head {align-items: flex-start !important;}
.ep-h {line-height: 1.25;}
.ep-d {font-family: 'Nunito', 'Pretendard Variable', 'Pretendard', sans-serif; font-size: 1.3rem; font-weight: 900; color: var(--ink);}
.ep-d em {font-style: normal; font-size: .95rem; color: #94A3B8; font-weight: 700; margin-left: 4px;}
.ep-n {display: block; font-size: .85rem; font-weight: 700; color: var(--accent); margin-top: 2px;}
.st-key-ep_new {width: auto !important;}
.st-key-ep_new button {border: none !important; background: var(--accent) !important; color: #fff !important; border-radius: 12px !important;
  font-weight: 700; padding: 0 14px; height: 38px; box-shadow: 0 3px 10px rgba(45, 143, 213, .3);}
.st-key-ep_new button p {color: #fff !important; font-weight: 700;}
.st-key-ep_list {gap: 6px !important;}
.st-key-ep_list button {justify-content: flex-start; text-align: left; padding: 8px 12px 8px 30px; border-radius: 12px;
  border: none !important; background: rgba(85,143,230,0.16); position: relative; min-height: 0;}
.st-key-ep_list button::before {content: ''; position: absolute; left: 12px; top: 50%; width: 10px; height: 10px; margin-top: -5px;
  border-radius: 50%; background: var(--chip-fg, #334155);}
.st-key-ep_list button:hover {background: rgba(85,143,230,0.16);}
.st-key-ep_list button div[data-testid="stMarkdownContainer"] {text-align: left; width: 100%;}
.st-key-ep_list button p {margin: 0; font-size: .8rem; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #94A3B8;}
.st-key-ep_list button p:first-child {font-weight: 700; font-size: .88rem; color: #F8FAFC;}
.st-key-ep_list button > div {justify-content: flex-start !important; width: 100%; min-width: 0;}
.st-key-ep_list button[data-testid="stBaseButton-primary"] {background: rgba(85,154,230,0.16) !important; box-shadow: inset 0 0 0 2px var(--accent);}
.st-key-ep_list button[data-testid="stBaseButton-primary"] p {color: #94A3B8 !important;}
.st-key-ep_list button[data-testid="stBaseButton-primary"] p:first-child {color: #F8FAFC !important;}
.st-key-ep_panel [data-testid="stMarkdownContainer"]:has(.ep-t, .ep-h, .ep-empty) {margin-bottom: 0 !important;}
.ep-empty {font-size: .85rem; color: #94A3B8; background: rgba(85,143,230,0.16); border-radius: 12px; padding: 12px; text-align: center;}
div[class*="st-key-ep_row_test_"] button {--chip-fg: #E35D78;} div[class*="st-key-ep_row_chg_"] button {--chip-fg: #C04FD8;} div[class*="st-key-ep_row_make_"] button {--chip-fg: #1FA971;}
div[class*="st-key-ep_row_anal_"] button {--chip-fg: #7C5CE0;}
.st-key-ep_form {border-top: 1px solid #26334D; padding-top: 14px; gap: .65rem;}
.ep-t {font-weight: 800; font-size: 1.05rem; color: var(--ink); display: flex; align-items: center; gap: 8px;}
.ep-t span {font-size: .72rem; font-weight: 800; padding: 2px 9px; border-radius: 999px;}
.ep-path {margin: -8px 0 8px; font-size: .74rem; color: var(--muted); line-height: 1.45;}
.ep-path span {display: inline-block; margin-right: 6px; padding: 0 8px; border-radius: 999px; font-weight: 700;
  background: var(--accent-bg); color: var(--accent);}
.st-key-ep_form [data-testid="stWidgetLabel"] p {font-size: .8rem; font-weight: 700; color: #94A3B8;}
.st-key-ep_form [data-baseweb="select"] > div, .st-key-ep_form [data-baseweb="input"], .st-key-ep_form [data-baseweb="textarea"],
.st-key-ep_form [data-testid="stNumberInputContainer"] {background: #26334D !important; border: 1.5px solid transparent !important; border-radius: 11px !important;}
.st-key-ep_form [data-baseweb="input"] > div, .st-key-ep_form [data-baseweb="textarea"] > div,
.st-key-ep_form [data-testid="stNumberInputContainer"] input, .st-key-ep_form [data-baseweb="input"] input,
.st-key-ep_form textarea {background: transparent !important;}
.st-key-ep_form [data-baseweb="select"] > div:focus-within, .st-key-ep_form [data-baseweb="input"]:focus-within,
.st-key-ep_form [data-baseweb="textarea"]:focus-within, .st-key-ep_form [data-testid="stNumberInputContainer"]:focus-within {
  border-color: var(--accent) !important; background: var(--panel) !important;}
.st-key-ep_form [data-testid="stNumberInputContainer"] button {background: var(--panel) !important; border-radius: 8px !important; margin: 3px;
  width: 28px; box-shadow: 0 1px 2px rgba(0, 0, 0, .06);}
.st-key-ep_form [data-testid="stButtonGroup"] button {border-radius: 999px !important; padding: 2px 13px; min-height: 0; height: 32px;
  border: none !important; background: #26334D;}
.st-key-ep_form [data-testid="stButtonGroup"] button p {font-size: .82rem; font-weight: 600; color: #94A3B8;}
.st-key-ep_form [data-testid="stButtonGroup"] button[aria-checked="true"] {background: var(--accent) !important;}
.st-key-ep_form [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
.st-key-ep_newcomp {margin-top: -.45rem;}
.st-key-ep_newcomp button {min-height: 0; padding: 0; color: var(--accent);} .st-key-ep_newcomp button p {font-size: .76rem; font-weight: 700;}
.st-key-ep_btns {margin-top: .5rem;}
.st-key-ep_btns div[class*="st-key-ep_del"] {width: auto !important;}
.st-key-ep_save button {height: 46px; border-radius: 13px; font-weight: 800; box-shadow: 0 4px 12px rgba(45, 143, 213, .3); border: none;}
.st-key-ep_del button {height: 46px; border-radius: 13px; color: #E5484D; background: rgba(230,85,95,0.16); border: none; padding: 0 18px;}
.st-key-ep_del button:hover {background: rgba(230,85,95,0.16); color: #D63A40;}
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
  background: var(--panel, #fff); border: 1px solid var(--line2, #334155); color: var(--muted, #94A3B8);}
.st-key-calgrid div[class*="st-key-x_"] button:hover {background: #d9534f; border-color: #d9534f; color: #fff;}
.st-key-calgrid div[class*="st-key-x_"] button span {font-size: 14px !important;}
/* 드래그 선택 */
.st-key-calgrid {user-select: none; -webkit-user-select: none;}
.st-key-calgrid div[class*="st-key-cell_"][data-drag] {background: rgba(45, 143, 213, 0.14) !important;
  border-color: var(--accent) !important;}
.st-key-cal_cmd {display: none !important;}
.st-key-calgrid div[class*="st-key-cell_"][data-jspick] {background: rgba(45, 143, 213, 0.12) !important;
  border: 2px solid var(--accent) !important; box-shadow: 0 0 0 3px rgba(45, 143, 213, .18) !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"])[data-jspick] button {box-shadow: 0 0 0 2px var(--accent) !important; background: rgba(85,154,230,0.16) !important;}
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
.cal-card {background: #334155; border: 1px solid #3A4866; border-radius: 14px;
  box-shadow: 0 14px 32px rgba(15, 30, 60, .32); padding: 13px 15px; color: rgba(85,139,230,0.16);}
.cal-card::after {content: ''; position: absolute; bottom: -7px; left: 26px; width: 12px; height: 12px;
  background: #334155; transform: rotate(45deg); border-radius: 2px;}
div[class*="st-key-cardr_"] .cal-card::after {left: auto; right: 26px;}
.cal-card .cc-h {display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;
  padding-bottom: 8px; border-bottom: 1px solid rgba(255, 255, 255, .14);}
.cal-card .cc-d {font-size: 1.05rem; font-weight: 700; color: #fff;}
.cal-card .cc-sum {font-size: .85rem; color: rgba(85,154,230,0.3); font-weight: 700;}
.cal-card .cc-e {padding: 7px 10px; border-left: 3px solid var(--accent, #2D8FD5); margin: 6px 0;
  background: rgba(255, 255, 255, .06); border-radius: 0 8px 8px 0;}
.cal-card .cc-n {font-size: .95rem; font-weight: 700; line-height: 1.35; margin-bottom: 4px; word-break: keep-all; color: #fff;}
.cal-card .cc-r {display: grid; grid-template-columns: 3.2em 1fr; gap: 2px 8px; font-size: .88rem; line-height: 1.5;}
.cal-card .cc-r span:nth-child(odd) {color: #94A3B8;}
.cal-card .cc-h2 {font-weight: 700;}
.cal-card .cc-tag {display: inline-block; font-size: .72rem; font-weight: 700; padding: 1px 7px; border-radius: 999px;
  margin-right: 6px; vertical-align: 1px;}
/* 칸 안의 구역 (시험 / 제조 / 분석): 비어 있어도 항상 보임 */
.st-key-calgrid div[class*="st-key-sec_"] {position: relative; z-index: 1; pointer-events: none; gap: 4px !important;
  border-radius: 12px; padding: 4px 5px 6px; background: var(--sec-bg); border: none;}
.st-key-calgrid div[class*="st-key-sec_"] div[class*="st-key-er_"],
.st-key-calgrid div[class*="st-key-sec_"] div[class*="st-key-more_"] {pointer-events: auto;}
.st-key-calgrid div[class*="st-key-sec_"] [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
.cal-sec-h {display: flex; align-items: center; gap: 6px; font-size: .72rem; font-weight: 800; line-height: 1.6;
  color: var(--sec-fg); padding: 0 3px;}
.cal-sec-h::before {content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--sec-fg);}
.cal-sec-h b {margin-left: auto; font-weight: 700;}
/* B 스티커형: 구분 알약 + 색깔 스티커 */
.st-key-calgrid [data-testid="stMarkdownContainer"]:has(.cal-chips) {margin-bottom: 0 !important;}
[data-testid="stElementContainer"]:has(> div .cal-chips) {position: relative; z-index: 1; pointer-events: none;}
.cal-chips {display: flex; gap: 4px; margin: 0 0 4px;}
.cal-chip {flex: 1; text-align: center; font-size: .68rem; font-weight: 800; padding: 2px 0; border-radius: 999px;
  background: #26334D; color: #94A3B8; white-space: nowrap;}
.cal-chip.on.c-test {background: rgba(230,85,114,0.16); color: #E35D78;} .cal-chip.on.c-make {background: rgba(85,230,153,0.16); color: #1FA971;}
.cal-chip.on.c-anal {background: rgba(117,85,230,0.16); color: #7C5CE0;} .cal-chip.on.c-etc {background: #26334D; color: #94A3B8;}
.cal-chip.c-etc:not(.on) {display: none;}
/* 빈 구역: 색 없이 얇은 줄과 흐린 글자만 */
.st-key-calgrid div[class*="st-key-sec_"]:not(:has(div[class*="st-key-er_"])):not(:has(div[class*="st-key-cf_"])) {
  background: transparent; border-radius: 0; padding: 1px 5px 3px; border-bottom: 1px solid #26334D;}
.cal-sec-h.none {opacity: .38;}
/* ✕ 누른 뒤 '삭제할까요?' */
.st-key-calgrid div[class*="st-key-cf_"] {pointer-events: auto; position: relative; z-index: 3; gap: 4px !important;
  background: rgba(230,85,85,0.16); border: 1px solid rgba(230,85,85,0.3); border-radius: 8px; padding: 5px 6px;}
.cal-cf-q {font-size: .7rem; line-height: 1.35; color: #8A2C2C; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.st-key-calgrid div[class*="st-key-cf_"] button {min-height: 0; height: 24px; padding: 0 4px; border-radius: 6px;}
.st-key-calgrid div[class*="st-key-cf_"] button p {font-size: .72rem !important; font-weight: 700;}
.st-key-calgrid div[class*="st-key-cfy_"] button {background: #E5484D !important; border-color: #E5484D !important; color: #fff !important;}
.st-key-calgrid div[class*="st-key-sec_test_"] {--sec-bg: rgba(230,85,114,0.16); --sec-line: #E35D7833; --sec-fg: #E35D78; --chip-fg: #E35D78;}
.st-key-calgrid div[class*="st-key-sec_chg_"] {--sec-bg: rgba(217,70,239,0.14); --sec-line: #C04FD833; --sec-fg: #C04FD8; --chip-fg: #C04FD8;}
.st-key-calgrid div[class*="st-key-sec_make_"] {--sec-bg: rgba(85,230,153,0.16); --sec-line: #1FA97133; --sec-fg: #1FA971; --chip-fg: #1FA971;}
.st-key-calgrid div[class*="st-key-sec_anal_"] {--sec-bg: rgba(117,85,230,0.16); --sec-line: #7C5CE033; --sec-fg: #7C5CE0; --chip-fg: #7C5CE0;}
.st-key-calgrid div[class*="st-key-sec_etc_"] {--sec-bg: #26334D; --sec-line: #8A97A833; --sec-fg: #94A3B8; --chip-fg: #94A3B8;}
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
  padding: 6px 8px 6px 18px; border-radius: 999px; background: #334155; color: #fff;
  box-shadow: 0 12px 30px rgba(15, 30, 60, .30); animation: calPop .18s ease-out;}
.st-key-cal_delbar {bottom: 84px; background: var(--panel); border: 1px solid rgba(230,85,85,0.3); box-shadow: 0 12px 30px rgba(180, 40, 40, .18);}
@keyframes calPop {from {opacity: 0; transform: translate(-50%, 8px);} to {opacity: 1; transform: translate(-50%, 0);}}
.st-key-cal_selbar [data-testid="stMarkdownContainer"], .st-key-cal_delbar [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
.st-key-cal_selbar p, .st-key-cal_delbar p {margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: .88rem;}
.st-key-cal_selbar p {color: #fff;} .st-key-cal_selbar p span {color: rgba(85,154,230,0.3) !important;}
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
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button {justify-content: flex-start; text-align: left;}
.st-key-calgrid div[class*="st-key-day_"] button > div,
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button > div {width: 100%; min-width: 0; justify-content: flex-start;}
.st-key-calgrid div[class*="st-key-day_"] button p {font-size: 0.76rem; color: #94A3B8;}
.st-key-calgrid div[class*="st-key-day_"] button strong {font-family: 'Nunito', 'Pretendard Variable', 'Pretendard', sans-serif;
  font-size: 1.12rem; font-weight: 800; letter-spacing: -.01em; display: inline-flex; align-items: center;
  justify-content: center; min-width: 1.75em; height: 1.75em; border-radius: 999px; margin-right: 2px;}
.st-key-calgrid div[class*="st-key-day_"] button:hover strong {background: rgba(45, 143, 213, 0.12);}
/* 실적 한 줄 (누르면 이 실적 선택) */
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button {
  justify-content: flex-start; min-height: 0; padding: 4px 8px; border: none; border-radius: 8px;
  background: var(--chip-bg, #26334D); border-left: none; border-radius: 12px !important;
  box-shadow: none; padding: 6px 9px !important;
  transition: transform .1s ease, box-shadow .1s ease;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button:hover {transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(20, 40, 80, .12); filter: saturate(1.15);}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p {font-size: 0.72rem; line-height: 1.4; color: #94A3B8;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:first-child {font-weight: 700; font-size: .78rem; color: #F8FAFC;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:first-child::before {content: var(--cat-label, ""); display: inline-block;
  font-size: .62rem; font-weight: 800; padding: 0 6px; margin-right: 5px; border-radius: 999px; line-height: 1.6;
  background: var(--chip-fg, #334155); color: #fff; vertical-align: 1px;}
/* 달력 모양: 둥근 흰 칸, 은은한 그림자, 주말은 옅은 색 */
.st-key-calgrid div[class*="st-key-cell_"] {background: var(--panel); border: 2px solid transparent !important; border-radius: 18px !important;
  box-shadow: 0 1px 2px rgba(30, 50, 90, .05), 0 4px 14px rgba(30, 50, 90, .04); transition: box-shadow .15s ease;}
.st-key-calgrid div[class*="st-key-cell_"]:hover {box-shadow: 0 2px 4px rgba(30, 50, 90, .06), 0 10px 24px rgba(30, 50, 90, .10);}
.st-key-calgrid .cal-wk {text-align: center; font-size: 1.05rem; font-weight: 800; color: #94A3B8; padding: 2px 0 4px;}
.st-key-calgrid .cal-wk.sat {color: #3D7BE0;} .st-key-calgrid .cal-wk.sun {color: #E0566A;}
.st-key-calgrid .cal-out {min-height: 230px; border-radius: 18px; border: none; padding: 8px 10px;
  font-family: 'Nunito', sans-serif; font-weight: 800; font-size: 1.05rem; color: #334155; background: rgba(255,255,255,.4);}
.st-key-calgrid div[class*="st-key-more_"] p {font-size: 0.7rem; color: #94A3B8; margin: 0 0 0 4px;}
/* 휴대폰: 7칸을 한 줄에 유지한 작은 달력 (날짜·건수만, 누르면 아래에 그날 실적) */
.cal-mobile-hint {display: none;}
@media (max-width: 640px) {
  .st-key-calgrid div[class*="st-key-card"] {display: none !important;}
  .st-key-calgrid [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 3px !important;}
  .st-key-calgrid [data-testid="stColumn"] {min-width: 0 !important; width: auto !important; flex: 1 1 0 !important;}
  .st-key-calgrid div[class*="st-key-cell_"] {min-height: 54px; padding: 3px 2px; border-radius: 8px;}
  .st-key-calgrid div[class*="st-key-er_"], .st-key-calgrid div[class*="st-key-more_"],
  .st-key-calgrid [data-testid="stElementContainer"]:has(.cal-chips) {display: none !important;}
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
/* ===== v3: 작은 달력 카드 + 작은 입력 카드 ===== */
.st-key-calcard {background: var(--panel); border-radius: 22px; padding: 16px 16px 14px;
  box-shadow: 0 1px 2px rgba(30, 50, 90, .04), 0 10px 30px rgba(30, 50, 90, .06); gap: .5rem;}
.st-key-calnav {margin-bottom: .2rem !important;}
.st-key-calnav .cal-title {font-size: 1.35rem; min-width: 7.5rem;}
.st-key-calnav div[class*="st-key-cal_prev"] button, .st-key-calnav div[class*="st-key-cal_next"] button,
.st-key-cal_today button {border: none !important; background: rgba(85,126,230,0.16) !important; border-radius: 10px !important;
  height: 32px; min-height: 0;}
.st-key-calnav div[class*="st-key-cal_prev"] button, .st-key-calnav div[class*="st-key-cal_next"] button {width: 32px;}
.st-key-cal_today {margin-left: 0 !important;} .st-key-cal_today button p {font-weight: 700; font-size: .82rem;}
.st-key-cal_legend {margin-left: auto;}
div[class*="st-key-cal_cats"] {margin: 0 !important;}
div[class*="st-key-cal_cats"] [data-testid="stButtonGroup"] button {min-height: 0; height: 28px; padding: 0 11px;}
.st-key-calgrid [data-testid="stHorizontalBlock"] {gap: 6px !important;}
.st-key-calgrid > [data-testid="stLayoutWrapper"], .st-key-calgrid {gap: 6px !important;}
.st-key-calgrid .cal-wk {font-size: .82rem !important; font-weight: 800; color: #94A3B8; padding: 0 0 2px !important;}
.st-key-calgrid .cal-wk.sat {color: #3D7BE0 !important;} .st-key-calgrid .cal-wk.sun {color: #E0566A !important;}
.st-key-calgrid div[class*="st-key-cell_"] {min-height: 112px !important; padding: 32px 6px 7px !important; gap: 3px !important;
  background: rgba(85,133,230,0.16); border-radius: 14px !important; box-shadow: none !important; border: 1.5px solid transparent !important;}
.st-key-calgrid div[class*="st-key-cell_"]:hover {box-shadow: 0 4px 14px rgba(30, 50, 90, .08) !important; background: var(--panel);}
.st-key-calgrid .cal-out {min-height: 112px !important; background: transparent !important; border: none !important;
  font-size: .9rem !important; padding: 8px 10px !important; color: #334155 !important;}
.st-key-calgrid div[class*="st-key-day_"] button {padding: 5px 6px !important; border-radius: 14px !important;}
.st-key-calgrid div[class*="st-key-day_"] button strong {font-size: .9rem !important; min-width: 24px !important; height: 24px !important;}
.st-key-calgrid div[class*="st-key-day_"] button:hover strong {background: rgba(45, 143, 213, .10);}
[data-testid="stElementContainer"]:has(> div .cal-dh) {position: absolute !important; top: 9px; left: 36px; right: 8px;
  width: auto !important; z-index: 1; pointer-events: none;}
.st-key-calgrid [data-testid="stMarkdownContainer"]:has(.cal-dh) {margin: 0 !important;}
.cal-dh {display: flex; align-items: center; gap: 4px; height: 18px;}
.cal-dots {display: flex; gap: 2px;} .cal-dots i {width: 6px; height: 6px; border-radius: 50%; display: block;}
.cal-tot {margin-left: auto; font-size: .7rem; font-weight: 700; color: #94A3B8;}
.c-test {background: #E35D78;} .c-make {background: #1FA971;} .c-anal {background: #7C5CE0;}
.c-edu {background: #E39A2D;} .c-sup {background: #2E9BD6;} .c-etc {background: #334155;}
/* 스티커 한 줄: 장비 이름 ··· 시간 */
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button {background: var(--chip-bg, #26334D) !important; border-radius: 8px !important;
  padding: 3px 7px 3px 12px !important; min-height: 0 !important; box-shadow: none !important; position: relative;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button::before {content: ''; position: absolute; left: 5px; top: 5px; bottom: 5px;
  width: 3px; border-radius: 3px; background: var(--chip-fg, #334155);}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button div[data-testid="stMarkdownContainer"] {display: flex; align-items: center; gap: 4px;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p {font-size: .72rem !important; line-height: 1.5 !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:first-child {flex: 1; min-width: 0; font-weight: 700; color: #F8FAFC !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:first-child::before {content: none !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:last-child {flex: none; font-weight: 800; color: var(--chip-fg) !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button:hover {transform: none; filter: brightness(.97);}
.st-key-calgrid div[class*="st-key-x_"] {top: -4px !important; right: -4px !important;}
.st-key-calgrid div[class*="st-key-x_"] button {height: 18px !important; width: 18px !important; border-radius: 50% !important;}
.st-key-calgrid div[class*="st-key-more_"] p {font-size: .68rem !important; font-weight: 700; color: #94A3B8; margin-left: 6px;}
.st-key-calgrid div[class*="st-key-cf_"] {padding: 4px 5px !important; gap: 3px !important;}
/* 입력 카드 */
.st-key-calwrap [data-testid="stHorizontalBlock"] {align-items: stretch !important;}
.st-key-calwrap [data-testid="stColumn"]:has(.st-key-ep_panel) > [data-testid="stVerticalBlock"] {height: 100%;}
.st-key-ep_panel {position: sticky !important; top: 4rem; max-height: calc(100vh - 5rem); overflow-y: auto !important;
  padding: 16px !important; border-radius: 22px !important; gap: .5rem !important;
  box-shadow: 0 1px 2px rgba(30, 50, 90, .04), 0 10px 30px rgba(30, 50, 90, .06) !important;}
@media (max-width: 1500px) {
  .st-key-calwrap [data-testid="stColumn"]:not(:has(.st-key-ep_panel)) {width: 100% !important; flex: 1 1 100% !important;}
  .st-key-calwrap [data-testid="stColumn"]:has(.st-key-ep_panel) {position: fixed !important; right: 16px; top: 4rem;
    width: 360px !important; flex: none !important; z-index: 900;}
  .st-key-calwrap [data-testid="stColumn"]:has(.st-key-ep_panel) > [data-testid="stVerticalBlock"] {height: auto;}
  .st-key-ep_panel {position: relative !important; top: 0; box-shadow: 0 18px 48px rgba(15, 30, 60, .25) !important;}
}
.ep-d {font-size: 1.2rem !important;} .ep-d em {font-size: .85rem !important;}
.ep-n {font-size: .75rem !important;}
.st-key-ep_new button {height: 32px !important; padding: 0 11px !important; font-size: .8rem; border-radius: 10px !important;}
.st-key-ep_close button {height: 32px !important; width: 32px !important; border-radius: 10px !important;}
.st-key-ep_list {gap: 4px !important;}
.st-key-ep_list button {padding: 6px 10px 6px 24px !important; border-radius: 10px !important;}
.st-key-ep_list button::before {left: 10px !important; width: 8px !important; height: 8px !important; margin-top: -4px !important;}
.st-key-ep_list button div[data-testid="stMarkdownContainer"] {display: flex; align-items: center; gap: 6px;}
.st-key-ep_list button p {font-size: .76rem !important;}
.st-key-ep_list button p:first-child {flex: 1; min-width: 0; font-size: .8rem !important;}
.st-key-ep_list button p:last-child {flex: none;}
.ep-empty {padding: 9px !important; font-size: .8rem !important;}
.st-key-ep_form {border-top: 1px dashed #26334D !important; padding-top: 10px !important; gap: .5rem !important;}
.ep-t {font-size: .92rem !important;}
.st-key-ep_form [data-testid="stWidgetLabel"] p, .num-l {font-size: .72rem !important; font-weight: 700; color: #94A3B8 !important;}
.num-l {margin-bottom: 4px;}
.st-key-ep_form [data-baseweb="select"] > div, .st-key-ep_form [data-baseweb="input"] {min-height: 36px;}
.st-key-ep_form [data-baseweb="select"] div, .st-key-ep_form input, .st-key-ep_form textarea {font-size: .82rem !important;}
.st-key-ep_form [data-testid="stButtonGroup"] button {height: 28px !important; padding: 0 10px !important;}
.st-key-ep_form [data-testid="stButtonGroup"] button p {font-size: .76rem !important; font-weight: 700 !important;}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button:nth-of-type(1) {--pc: #E35D78; --pb: rgba(230,85,114,0.16);}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button:nth-of-type(2) {--pc: #1FA971; --pb: rgba(85,230,158,0.16);}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button:nth-of-type(3) {--pc: #7C5CE0; --pb: rgba(121,85,230,0.16);}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button:nth-of-type(4) {--pc: #E39A2D; --pb: rgba(230,176,85,0.16);}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button:nth-of-type(5) {--pc: #2E9BD6; --pb: rgba(85,177,230,0.16);}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button {background: var(--pb, rgba(85,126,230,0.16)) !important;}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button p {color: var(--pc, #94A3B8) !important;}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button[aria-checked="true"] {background: var(--pc, #2D8FD5) !important;}
div[class*="st-key-ep_purp_"] [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
div[class*="st-key-ep_type_"] [data-testid="stButtonGroup"] button[aria-checked="true"] {background: #334155 !important;}
/* 숫자 칸 (−/＋) */
div[class*="st-key-num_"] {gap: 0 !important;}
div[class*="st-key-num_"] [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
div[class*="st-key-numr_"] {background: rgba(85,126,230,0.16); border-radius: 10px; padding: 3px; flex-wrap: nowrap !important; min-height: 36px;}
div[class*="st-key-numr_"] [data-testid="stElementContainer"]:has(button) {width: auto !important; flex: none;}
div[class*="st-key-numr_"] button {min-height: 0 !important; height: 28px; width: 28px; padding: 0 !important; border: none !important;
  background: var(--panel) !important; border-radius: 8px !important; box-shadow: 0 1px 2px rgba(0, 0, 0, .06);}
div[class*="st-key-numr_"] button p {font-size: .9rem !important; color: #94A3B8; font-weight: 700;}
div[class*="st-key-numr_"] [data-baseweb="input"] {background: transparent !important; border: none !important; min-height: 28px !important;}
div[class*="st-key-numr_"] input {text-align: center; font-weight: 700; padding: 0 2px !important;}
.st-key-ep_form [data-testid="stExpander"] details {border: none !important; background: transparent;}
.st-key-ep_form [data-testid="stExpander"] summary {padding: 0 !important; font-size: .78rem; color: var(--accent); font-weight: 700;}
.st-key-ep_save button, .st-key-ep_del button {height: 40px !important;}
/* ===== v4: 구역형 달력 (시험/제조/분석 줄) + 시안 색 ===== */
.st-key-calgrid div[class*="st-key-cell_"] {min-height: 168px !important; padding: 34px 6px 8px !important; gap: 4px !important;}
.st-key-calgrid .cal-out {min-height: 168px !important;}
.st-key-calgrid div[class*="st-key-day_"] button p {font-size: .72rem; color: #94A3B8; font-weight: 700;}
.st-key-calgrid div[class*="st-key-sec_"] {background: transparent !important; padding: 0 !important; gap: 3px !important;
  border: none !important; border-radius: 0 !important;}
.st-key-calgrid div[class*="st-key-sec_"]:not(:has(div[class*="st-key-er_"])):not(:has(div[class*="st-key-cf_"])) {
  border: 1px dashed color-mix(in srgb, var(--sec-fg) 30%, transparent) !important; border-radius: 999px !important;
  padding: 0 4px !important;}
.cal-sec-h {font-size: .68rem !important; line-height: 1.55 !important; padding: 0 4px !important;}
.cal-sec-h.none {opacity: .55 !important;}
.st-key-calgrid div[class*="st-key-sec_edu_"] {--sec-bg: rgba(230,176,85,0.16); --sec-fg: #E39A2D; --chip-fg: #E39A2D;}
.st-key-calgrid div[class*="st-key-sec_sup_"] {--sec-bg: rgba(85,177,230,0.16); --sec-fg: #2E9BD6; --chip-fg: #2E9BD6;}
/* 줄 이름(시험·제조·분석)을 누르면 그 구분 장비로 새 실적 — 이름 위에 투명 버튼 */
.st-key-calgrid div[class*="st-key-lane_"] {position: absolute !important; top: 0; left: 0; right: 0; height: 19px;
  z-index: 2; pointer-events: auto; margin: 0 !important;}
.st-key-calgrid div[class*="st-key-lane_"] button {width: 100%; height: 100%; min-height: 0 !important; padding: 0 !important;
  opacity: 0; cursor: pointer;}
.st-key-calgrid div[class*="st-key-sec_"]:has(div[class*="st-key-lane_"]:hover) .cal-sec-h {
  background: var(--sec-bg); border-radius: 999px; opacity: 1 !important;}
.st-key-calgrid div[class*="st-key-sec_"]:has(div[class*="st-key-lane_"]:hover) .cal-sec-h b::after {content: ' +'; font-weight: 800;}
/* 입력 카드: 장비 구분 고르기 (작은 알약) */
.st-key-ep_grp {margin-bottom: -6px;}
.st-key-ep_grp [data-testid="stButtonGroup"] button {min-height: 28px !important; padding: 0 12px !important; border-radius: 999px !important;
  font-size: .78rem !important;}
.st-key-ep_grp [data-testid="stButtonGroup"] {flex-wrap: wrap; row-gap: 4px;}
/* 입력 카드: 하루 / 기간 스위치 */
div[class*="st-key-ep_mode_"] [data-testid="stButtonGroup"] {background: #26334D; border-radius: 999px; padding: 3px; width: fit-content;}
div[class*="st-key-ep_mode_"] [data-testid="stButtonGroup"] button {border: none !important; border-radius: 999px !important;
  min-height: 30px !important; padding: 0 20px !important; background: transparent !important; color: var(--muted) !important;}
div[class*="st-key-ep_mode_"] [data-testid="stButtonGroup"] button[aria-checked="true"] {background: var(--panel) !important;
  color: var(--accent) !important; box-shadow: 0 1px 4px rgba(17, 28, 46, .15);}
div[class*="st-key-ep_mode_"] [data-testid="stButtonGroup"] button p {font-weight: 700; font-size: .84rem; color: var(--muted) !important;}
div[class*="st-key-ep_mode_"] [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: var(--accent) !important;}
/* 기간: 빠른 종료일 · 합계 상자 */
.st-key-ep_quick {gap: 4px !important; margin-top: -6px; flex-wrap: wrap;}
.st-key-ep_quick button {min-height: 24px !important; padding: 0 10px !important; border-radius: 999px !important;
  background: #26334D !important; font-size: .74rem !important;}
.st-key-ep_quick button p {font-size: .74rem !important; font-weight: 700; color: var(--muted) !important;}
.st-key-ep_quick button:hover {background: rgba(85,102,230,0.16) !important;}
.st-key-ep_quick button:hover p {color: var(--accent) !important;}
.ep-sum {background: linear-gradient(135deg, rgba(85,128,230,0.16), rgba(137,85,230,0.16)); border-radius: 14px; padding: 9px 13px; margin: 2px 0 4px;}
.ep-sum b {display: block; color: var(--accent); font-size: .98rem;}
.ep-sum span {font-size: .74rem; color: var(--muted);}
/* 충방전기 챔버 고르기 */
.ep-chlab {font-size: .875rem; color: var(--ink); margin: 8px 0 2px; line-height: 1.4;}
div[class*="st-key-ep_cbox_"] {margin-top: 4px;}
div[class*="st-key-ep_cbox_"] .ep-chlab {margin: 0; font-size: .8rem; color: var(--muted);}
div[class*="st-key-ep_cbox_"] button {min-height: 0 !important; padding: 0 4px !important;}
div[class*="st-key-ep_cbox_"] button p {font-size: .76rem !important;}
div[class*="st-key-ep_cn_"] [data-testid="stButtonGroup"] {gap: 4px;}
div[class*="st-key-ep_cn_"] [data-testid="stButtonGroup"] button {min-width: 34px; min-height: 26px !important;
  padding: 0 6px !important; border-radius: 8px !important; justify-content: center;}
div[class*="st-key-ep_cn_"] [data-testid="stButtonGroup"] button p {font-size: .74rem !important;}
div[class*="st-key-ep_cn_"] button[aria-pressed="true"] {background: #5B6CFF !important; border-color: #5B6CFF !important;}
div[class*="st-key-ep_cn_"] button[aria-pressed="true"] p {color: #fff !important; font-weight: 700;}
div[class*="st-key-ep_ch_"] [data-testid="stButtonGroup"] {flex-wrap: wrap; gap: 5px;}
div[class*="st-key-ep_ch_"] [data-testid="stButtonGroup"] button {border-radius: 10px !important; min-height: 30px !important;
  padding: 0 10px !important;}
div[class*="st-key-ep_ch_"] [data-testid="stButtonGroup"] button p {font-size: .76rem; font-weight: 700;}
div[class*="st-key-ep_ch_"] [data-testid="stButtonGroup"] button[aria-pressed="true"] {background: var(--accent) !important;
  border-color: var(--accent) !important;}
div[class*="st-key-ep_ch_"] [data-testid="stButtonGroup"] button[aria-pressed="true"] p {color: #fff !important;}
/* 스티커: 연한 구분 색 + 왼쪽 진한 막대, 1줄 장비·시간 / 2줄 업체 */
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button {padding: 5px 8px 5px 13px !important; border-radius: 9px !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button::before {top: 6px !important; bottom: 6px !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button div[data-testid="stMarkdownContainer"] {display: grid !important;
  grid-template-columns: minmax(0, 1fr) auto; column-gap: 6px; row-gap: 1px; width: 100%;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p {white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin: 0 !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:nth-child(1) {font-size: .76rem !important; font-weight: 800; color: #F8FAFC !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:nth-child(2) {font-size: .74rem !important; font-weight: 800; color: var(--chip-fg) !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:nth-child(3) {grid-column: 1 / -1; font-size: .68rem !important;
  font-weight: 500 !important; color: #94A3B8 !important;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button > div > span {flex: 1 1 auto; min-width: 0; width: 100%;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button > div, .st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button div[data-testid="stMarkdownContainer"] {
  width: 100% !important; min-width: 0;}
.st-key-calgrid :is(div[class*="st-key-ent_"], div[class*="st-key-chg_"]) button p:nth-child(2) {text-align: right;}
.st-key-calgrid div[class*="st-key-more_"] p {margin-left: 4px !important;}
.st-key-calgrid .cal-wk {padding-bottom: 8px !important;}
.st-key-calwrap [data-testid="stHorizontalBlock"]:has(.st-key-ep_panel) {flex-wrap: nowrap !important;}
.st-key-calwrap [data-testid="stColumn"]:not(:has(.st-key-ep_panel)) {min-width: 0 !important;}
.st-key-calgrid [data-testid="stColumn"], .st-key-calgrid div[class*="st-key-cell_"] {min-width: 0 !important;}
.st-key-ep_list:not(:has(button)) {display: none !important;}
/* 구역을 칸 안에 고르게: 시험/제조/분석이 처음부터 같은 높이로 나뉨 */
.st-key-calgrid div[class*="st-key-cell_"] {min-height: 240px !important;}
.st-key-calgrid div[class*="st-key-cell_"] > [data-testid="stLayoutWrapper"]:has(> div[class*="st-key-sec_"]),
.st-key-calgrid div[class*="st-key-cell_"] > div[class*="st-key-sec_"] {flex: 1 1 0 !important; display: flex; flex-direction: column;}
.st-key-calgrid div[class*="st-key-sec_"] {flex: 1 1 auto !important; min-height: 44px;}
.st-key-calgrid div[class*="st-key-sec_"]:not(:has(div[class*="st-key-er_"])):not(:has(div[class*="st-key-cf_"])) {
  border-radius: 10px !important; padding: 2px 4px !important;}
.st-key-calgrid .cal-out {min-height: 240px !important;}
.st-key-calgrid div[class*="st-key-cell_"][data-unsel] {background: rgba(85,133,230,0.16) !important; border-color: transparent !important; box-shadow: none !important;}
.st-key-calgrid div[class*="st-key-ent_"][data-jsmulti="1"] button {box-shadow: 0 0 0 2px var(--accent) !important; background: rgba(85,154,230,0.16) !important;}
.st-key-calgrid div[class*="st-key-ent_"][data-jsmulti="0"] button {box-shadow: none !important; background: var(--chip-bg, #26334D) !important;}
.st-key-calgrid[data-dragging] div[class*="st-key-card"] {display: none !important;}
[data-testid="stElementContainer"]:has(> div .cal-state), [data-testid="stMarkdown"]:has(.cal-state) {display: none !important;}
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
    span: dict[str, tuple] = {}  # 묶음ID → 전체 기간 (달마다 나눠 저장한 기간 실적)
    if "series" in logs:
        sl = logs[logs["series"].map(db.to_str) != ""]
        span = {k: (g["start_date"].min(), g["end_date"].max()) for k, g in sl.groupby("series")}
    chans = db.load_channels()
    ch_name = dict(zip(chans["id"].astype(int), chans["chamber"])) if not chans.empty else {}
    chg = db.charger_ids(eq, chans)
    root_of = dict(zip(eq["id"].astype(int), eq["root_id"])) if "root_id" in eq else {}
    out: dict[dt.date, list[dict]] = {}
    for r in in_month.itertuples(index=False):
        if r.log_id not in info.index:
            continue
        lg = info.loc[r.log_id]
        a, b = span.get(db.to_str(lg.get("series")), (lg["start_date"], lg["end_date"]))
        multi = a != b
        rec = lg.to_dict() | {"id": int(r.log_id)}
        if multi:  # 기간 실적은 그날 몫만 하루짜리로 복사
            rec.update(hours=round(float(r.hours), 1), fee=round(float(r.fee)))
        out.setdefault(r.day.date(), []).append({
            "id": int(r.log_id), "rec": rec,
            "equip": name_of.get(int(r.equip_id), "?") + "".join(
                f" · {ch_name[i]}" for i in db.chamber_ids(lg.get("chambers"))[:2] if i in ch_name)
                + (" …" if len(db.chamber_ids(lg.get("chambers"))) > 2 else ""),
            "company": db.to_str(lg["company"]) or "내부",
            "cat": _log_cat(lg["purpose"], int(r.equip_id) in chg),
            "hours": float(r.hours), "staff": db.to_str(lg["created_by"]),
            "period": f"{a:%m/%d}~{b:%m/%d}" if multi else "",
            "charger": int(r.equip_id) in chg, "equip_id": int(r.equip_id),
            "root": int(root_of.get(int(r.equip_id), r.equip_id) or r.equip_id),
            "n_ch": max(len(db.chamber_ids(lg.get("chambers"))), 1),
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
CHARGER_GROUP = "시험(충방전기)"
CATS = {"시험": ("rgba(230,85,114,0.16)", "#E35D78"), CHARGER_GROUP: ("rgba(217,70,239,0.16)", "#C04FD8"), "제조": ("rgba(85,230,158,0.16)", "#1FA971"), "분석": ("rgba(121,85,230,0.16)", "#7C5CE0"),
        "교육": ("rgba(230,176,85,0.16)", "#E39A2D"), "지원": ("rgba(85,177,230,0.16)", "#2E9BD6"), "기타": ("#26334D", "#334155")}
CAT_ORDER = list(CATS)
FIXED_CATS = ["시험", CHARGER_GROUP, "제조", "분석", "교육", "지원"]
LANE_CATS = ["시험", CHARGER_GROUP, "제조", "분석"]  # 칸마다 비어 있어도 보이는 구역 (2026-11-10 시험을 환경·충방전으로 나눔)
GROUP_LABEL = {"시험": "시험(환경)", CHARGER_GROUP: "시험(충방전)"}  # 입력 카드 구분 버튼에 보이는 이름
CARD_GROUPS = ["시험", CHARGER_GROUP, "제조", "분석"]  # 입력 카드 장비 구분 (시험 = 충방전기 뺀 시험 장비)
CAT_KEY = {"시험": "test", CHARGER_GROUP: "chg", "제조": "make", "분석": "anal", "교육": "edu", "지원": "sup", "기타": "etc"}
PURPOSE_CAT = {"시험": "시험", "생산": "제조", "분석": "분석", "계측": "분석", "교육": "교육", "기타": "지원"}
LANE_PURPOSE = {"시험": "시험", "제조": "생산", "분석": "분석", "교육": "교육", "지원": "기타",
                CHARGER_GROUP: "시험"}  # 줄을 눌러 열 때 사용목적


def _log_cat(purpose, charger: bool) -> str:
    """실적 → 달력 구역. 충방전기 시험은 '시험(충방전)' 구역에 따로."""
    c = PURPOSE_CAT.get(db.to_str(purpose), "지원")
    return CHARGER_GROUP if charger and c == "시험" else c


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
        tag = f"<span class='cc-tag' style='background:{bg};color:{fg}'>{GROUP_LABEL.get(x['cat'], x['cat'])}</span>"
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


def _click_day(d: dt.date, clip: dict | None, logs: pd.DataFrame) -> None:
    """날짜 칸을 누름: 그날을 선택만 함 (붙여넣기는 Ctrl+V)."""
    _clear_sel()
    st.session_state.pop("cal_pick", None)
    st.session_state.pop("cal_lane", None)
    st.session_state.cal_open = True
    _pick_day(d)


def _click_lane(d: dt.date, cat: str) -> None:
    """칸 안의 '시험·제조·분석' 줄을 누름: 그날 새 실적을 열고 그 구분 장비만 보여 줌."""
    _clear_sel()
    st.session_state.pop("cal_pick", None)
    st.session_state.cal_lane = cat
    st.session_state.cal_open = True
    _pick_day(d)


def _click_entry(d: dt.date, e: dict, clip: dict | None, logs: pd.DataFrame) -> None:
    """실적 한 줄을 누름: 이 실적을 선택만 함 (복사는 Ctrl+C)."""
    _clear_sel()
    st.session_state.cal_pick = {"day": d, "id": e["id"], "rec": e["rec"], "period": bool(e["period"]),
                                 "label": f"{e['equip']} · {e['company']} · {_hours(e['hours'])}"}
    st.session_state.cal_open = True
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
    """Ctrl+C: Ctrl+클릭으로 고른 실적들, 선택한 실적 한 건, 또는 선택한 날(들)의 실적을 복사."""
    picks = _picks()
    if picks:  # 고른 실적들은 붙여 넣을 날에 모두 함께 들어감
        st.session_state.cal_clip = {"from": picks[0]["day"], "rows": [dict(p["rec"], _off=0) for p in picks],
                                     "label": f"실적 {len(picks)}건", "keys": [(p["day"], p["id"]) for p in picks]}
        return
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
    picks = [p for p in _picks() if not p["period"]]
    if not days and picks:
        ask = {"kind": "ids", "ids": [int(p["id"]) for p in picks], "text": f"고른 실적 {len(picks)}건을 삭제할까요?"}
        st.session_state.cal_delask = ask
        return
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
    elif ask["kind"] == "ids":
        _delete_ids(ask["ids"], f"실적 {len(ask['ids'])}건 삭제")
        st.session_state.pop("cal_picks", None)
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
    elif cmd == "unsel":
        _clear_sel()
    elif cmd == "undo":  # Ctrl+Z: 마지막 저장·삭제·붙여넣기를 되돌림 (최근 30번까지)
        if db.undo_last():
            for k in [k for k in st.session_state if str(k).endswith("_editor") or str(k).startswith("cal_ed_")]:
                st.session_state.pop(k, None)
            st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
            st.session_state.entry_ver = st.session_state.get("entry_ver", 0) + 1
            st.session_state.pop("cal_picks", None)
            st.session_state.pop("cal_pick", None)
    elif cmd == "tog" and len(parts) >= 3:
        _toggle_pick(dt.date.fromisoformat(parts[1]), int(parts[2]))
    elif cmd == "esc":
        if st.session_state.pop("cal_delask", None) or st.session_state.pop("cal_xconfirm", None):
            return
        st.session_state.pop("cal_sel", None)
        st.session_state.pop("cal_pick", None)
        st.session_state.pop("cal_picks", None)
        st.session_state.pop("cal_clip", None)


def _clear_sel() -> None:
    st.session_state.pop("cal_sel", None)
    st.session_state.pop("cal_picks", None)


def _picks() -> list[dict]:
    return list(st.session_state.get("cal_picks") or [])


def _toggle_pick(day: dt.date, log_id: int) -> None:
    """Ctrl+클릭: 실적을 여러 개 골라 둠 (엑셀처럼). 처음 고른 실적도 함께 들어감."""
    picks = _picks()
    if not picks and st.session_state.get("cal_pick"):
        picks = [st.session_state.cal_pick]
    if any(p["day"] == day and int(p["id"]) == log_id for p in picks):
        picks = [p for p in picks if not (p["day"] == day and int(p["id"]) == log_id)]
    else:
        logs, eq = db.load_logs(), db.load_equipment()
        row = logs[logs["id"] == log_id]
        if row.empty:
            return
        lg = row.iloc[0]
        rec = lg.to_dict() | {"id": log_id}
        multi = lg["start_date"] != lg["end_date"]
        if multi:  # 기간 실적은 그날 몫만
            daily = expand_daily(row, db.get_settings().get("alloc_mode", "spread"))
            dd = daily[daily["day"] == pd.Timestamp(day)]
            if not dd.empty:
                rec.update(hours=round(float(dd["hours"].iloc[0]), 1), fee=round(float(dd["fee"].iloc[0])))
        name = dict(zip(eq["id"].astype(int), eq["name"])).get(int(lg["equip_id"]), "?")
        picks.append({"day": day, "id": log_id, "rec": rec, "period": bool(multi),
                      "label": f"{name} · {db.to_str(lg['company']) or '내부'} · {_hours(float(rec['hours']))}"})
    st.session_state.pop("cal_sel", None)
    st.session_state.cal_picks = picks
    if len(picks) == 1:
        st.session_state.cal_pick = picks[0]
        st.session_state.pop("cal_picks", None)
    elif not picks:
        st.session_state.pop("cal_pick", None)
        st.session_state.pop("cal_picks", None)
    else:
        st.session_state.pop("cal_pick", None)


def _clear_all() -> None:
    for k in ("cal_sel", "cal_pick", "cal_picks", "cal_clip"):
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
    doc.querySelectorAll('.st-key-calgrid [data-drag]').forEach(c => c.removeAttribute('data-drag'));
    if (!dragging) return;
    const [a, b] = [start, cur].sort();
    doc.querySelectorAll('.st-key-calgrid div[class*="st-key-cell_"]').forEach(c => {
      const d = dateOf(c); if (d && d >= a && d <= b) c.setAttribute('data-drag', '1');
    });
  };
  // 바로 표시해 둔 선택을 지우고 서버가 그린 선택 표시로 돌아감
  const clearQuick = () => {
    doc.querySelectorAll('[data-jspick]').forEach(el => el.removeAttribute('data-jspick'));
    const g = doc.querySelector('.st-key-calgrid'); if (g) g.removeAttribute('data-js');
  };
  // 누르는 순간 바로 선택 표시 (서버 응답을 기다리지 않음)
  const quickPick = (t) => {
    const c = cellOf(t); if (!c || t.closest('div[class*="st-key-x_"], div[class*="st-key-cf_"]')) return;
    const g = doc.querySelector('.st-key-calgrid'); if (!g) return;
    doc.querySelectorAll('[data-jspick]').forEach(el => el.removeAttribute('data-jspick'));
    g.setAttribute('data-js', '1');
    const ent = t.closest('div[class*="st-key-ent_"]');
    c.setAttribute('data-jspick', '1');
    if (ent) ent.setAttribute('data-jspick', '1');
    // 서버가 같은 선택을 그려 주면(또는 8초가 지나면) 바로 표시를 걷어 냄
    const want = ent ? (ent.className.match(/st-key-(ent_\S+)/) || [])[1] : 'cell_' + dateOf(c);
    const t0 = Date.now();
    clearInterval(win.__calQuickT);
    win.__calQuickT = setInterval(() => {
      const done = [...doc.querySelectorAll('style')].some(st => st.textContent.includes(':not([data-js]) .st-key-' + want + ' '));
      if (done || Date.now() - t0 > 8000) { clearInterval(win.__calQuickT); clearQuick(); }
    }, 80);
  };
  const entOf = (el) => el && el.closest && el.closest('.st-key-calgrid div[class*="st-key-ent_"]');
  const clearMulti = () => doc.querySelectorAll('[data-jsmulti]').forEach(el => el.removeAttribute('data-jsmulti'));
  on('mousedown', (e) => {
    if (e.button !== 0) return;
    if ((e.ctrlKey || e.metaKey) && entOf(e.target)) { start = null; return; }  // Ctrl+클릭은 mouseup에서 처리
    clearMulti();
    if (cellOf(e.target)) {  // 칸 안에서는 글자 선택·끌어다 놓기가 시작되지 않게 (드래그 선택이 끊기는 원인)
      e.preventDefault();
      const sel = win.getSelection && win.getSelection(); if (sel) sel.removeAllRanges();
    }
    if (!cellOf(e.target)) {
      clearQuick();  // 달력 밖(입력 카드 등)을 누르면 서버 표시를 따름
      // 여러 날을 골라 둔 상태에서 다른 곳을 누르면 선택을 풂 (엑셀처럼)
      const bar = doc.querySelector('.cal-state[data-multi]');
      const keep = e.target.closest && e.target.closest(
        '.st-key-cal_selbar, .st-key-cal_delbar, [role="dialog"], [data-testid="stSidebar"], [data-baseweb="popover"]');
      if (!keep && bar) {
        doc.querySelectorAll('.st-key-calgrid div[class*="st-key-cell_"]').forEach(c => c.setAttribute('data-unsel', '1'));
        send('unsel');
      }
    }
    const c = cellOf(e.target); start = dateOf(c); cur = start; dragging = false;
    const g = doc.querySelector('.st-key-calgrid'); if (g && start) g.setAttribute('data-dragging', '1');
  }, true);
  on('dragstart', (e) => { if (cellOf(e.target)) e.preventDefault(); }, true);
  on('mousemove', (e) => {
    if (!start) return;
    if (!(e.buttons & 1)) { start = null; dragging = false; paint(); return; }  // 버튼을 이미 뗀 경우
    // 화면 위·아래 끝으로 끌면 저절로 스크롤 (아래 주까지 이어서 고를 수 있게)
    const edge = 60, vh = win.innerHeight;
    if (e.clientY > vh - edge || e.clientY < edge) {
      const step = e.clientY > vh - edge ? 18 : -18;
      const sc = doc.querySelector('[data-testid="stMain"]');
      if (sc && sc.scrollHeight > sc.clientHeight) sc.scrollBy(0, step); else win.scrollBy(0, step);
    }
    const d = dateOf(cellOf(doc.elementFromPoint(e.clientX, e.clientY)));
    if (d && d !== cur) { cur = d; if (cur !== start) { dragging = true; clearQuick(); } paint(); }
  }, true);
  on('mouseup', (e) => {
    const ent = (e.ctrlKey || e.metaKey) && e.button === 0 && entOf(e.target);
    if (ent) {  // Ctrl+클릭: 실적을 하나씩 더하거나 뺌 (엑셀처럼)
      e.preventDefault(); e.stopPropagation();
      const swallow = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
      doc.addEventListener('click', swallow, {capture: true, once: true});
      setTimeout(() => doc.removeEventListener('click', swallow, true), 300);
      const m = ent.className.match(/st-key-ent_(\d{4}-\d{2}-\d{2})_(\d+)/);
      if (m) {
        const onNow = ent.getAttribute('data-jsmulti') === '1' ||
          (ent.getAttribute('data-jsmulti') !== '0' && getComputedStyle(ent.querySelector('button')).boxShadow.includes('2px'));
        ent.setAttribute('data-jsmulti', onNow ? '0' : '1');
        send('tog|' + m[1] + '|' + m[2]);
      }
      start = null; dragging = false; return;
    }
    if (start) {  // 손을 뗀 자리를 한 번 더 확인 (빠르게 끌었을 때 마지막 칸을 놓치지 않게)
      const d = dateOf(cellOf(doc.elementFromPoint(e.clientX, e.clientY)));
      if (d && d !== cur) { cur = d; if (cur !== start) dragging = true; }
    }
    if (start && dragging) {
      e.preventDefault(); e.stopPropagation();
      const swallow = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
      doc.addEventListener('click', swallow, {capture: true, once: true});
      setTimeout(() => doc.removeEventListener('click', swallow, true), 300);
      send('sel|' + start + '|' + cur);
    } else if (start && e.button === 0) {
      quickPick(e.target);
    }
    start = null; dragging = false;
    doc.querySelectorAll('[data-dragging]').forEach(el => el.removeAttribute('data-dragging'));
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
    else if (mod && (e.key === 'z' || e.key === 'Z')) { e.preventDefault(); send('undo'); }
    else if (e.key === 'Escape') { clearQuick(); clearMulti(); send('esc'); }
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
    # 구역: 시험·제조·분석은 비어 있어도 항상, 교육·지원은 실적이 있을 때만
    cats = [c for c in shown_cats if c in LANE_CATS or any(e["cat"] == c for e in entries)]
    for c in cats:
        ents = [e for e in entries if e["cat"] == c]
        chg = [e for e in ents if e.get("charger")]  # 충방전기도 다른 실적처럼 한 건씩 (누르면 입력 카드)
        chg_h = 0 if d.weekday() >= 5 else sum(  # 주장비마다 하루 최대 8h
            min(db.CHARGER_DAY_MAX, sum(e["hours"] for e in chg if e["root"] == i)) for i in {e["root"] for e in chg})
        sec = cell.container(key=f"sec_{CAT_KEY[c]}_{d}")
        hours = _hours(sum(e["hours"] for e in ents if not e.get("charger")) + chg_h) if ents else ""
        sec.markdown(f"<div class='cal-sec-h{'' if ents else ' none'}'>{GROUP_LABEL.get(c, c)}<b>{hours}</b></div>",
                     unsafe_allow_html=True)
        # 줄 이름 위에 투명 버튼: 누르면 이 구분 장비만 보이는 새 실적 입력
        sec.button(GROUP_LABEL.get(c, c), key=f"lane_{CAT_KEY[c]}_{d}", type="tertiary", help=f"{GROUP_LABEL.get(c, c)} 실적 추가",
                   on_click=_click_lane, args=(d, c))
        for e in ents[:CELL_LINES]:
            short = e["equip"]  # 세부장비 이름 그대로 (양극·음극 구분이 보이게, 길면 … 처리)
            label = f"{_md(short)}\n\n{_hours(e['hours'])}\n\n{_md(e['company'])}"
            if st.session_state.get("cal_xconfirm") == (d, e["id"]):
                cf = sec.container(key=f"cf_{d}_{e['id']}")
                cf.markdown(f"<div class='cal-cf-q'><b>{html.escape(_cut(short, 10))}</b> 삭제할까요?</div>",
                            unsafe_allow_html=True)
                with cf.container(horizontal=True, gap="small"):
                    st.button("삭제", key=f"cfy_{d}_{e['id']}", type="primary", width="stretch",
                              on_click=_confirm_x, args=(d, e))
                    st.button("취소", key=f"cfn_{d}_{e['id']}", width="stretch", on_click=_cancel_x)
                continue
            row = sec.container(key=f"er_{d}_{e['id']}")
            row.button(label, key=f"ent_{d}_{e['id']}", width="stretch",
                       on_click=_click_entry, args=(d, e, clip, logs))
            if not e["period"]:
                row.button("", icon=":material/close:", key=f"x_{d}_{e['id']}", help="이 실적 삭제",
                           on_click=_click_x, args=(d, e))
        if len(ents) > CELL_LINES:
            sec.container(key=f"more_{d}_{CAT_KEY[c]}").markdown(f"+{len(ents) - CELL_LINES}")
    if entries:
        side = "r" if d.weekday() >= 4 else ""  # 오른쪽 칸은 카드를 왼쪽으로 펼침
        cell.container(key=f"card{side}_{d}").markdown(_card_html(d, entries), unsafe_allow_html=True)


def render(header: bool = True) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if header:
        page_header("달력 입력", "실적")
    st.session_state.pop("cal_saved", None)  # 저장·삭제 알림은 띄우지 않음 (달력 칸에 바로 보임)

    cfg = db.get_settings()
    eq = db.load_equipment()
    comp = db.load_companies()
    logs = db.load_logs()

    today = dt.date.today()
    day: dt.date = st.session_state.setdefault("cal_day", today)
    month: dt.date = st.session_state.setdefault("cal_month", day.replace(day=1))

    # ── 달력 (흰 카드 하나) + 날짜를 누르면 오른쪽에 입력 카드 ──────────────
    is_open = bool(st.session_state.get("cal_open"))
    if is_open:  # 입력 카드가 열릴 때만 넓게, 닫히면 다른 화면과 같은 폭
        st.markdown("<style>.block-container {max-width: 2300px !important;}</style>", unsafe_allow_html=True)
    wrap = st.container(key="calwrap")
    if is_open:
        left, right = wrap.columns([2.6, 1], gap="medium")
    else:
        left, right = wrap, None
    card = left.container(key="calcard")
    with card.container(key="calnav", horizontal=True, vertical_alignment="center", gap="small"):
        if st.button("", icon=":material/chevron_left:", key="cal_prev", help="이전 달"):
            st.session_state.cal_month = _shift_month(month, -1)
            st.rerun()
        st.markdown(f"<div class='cal-title'><span style='opacity:.55;font-size:.8em'>{month.year}</span>&nbsp; "
                    f"<span style='color:var(--accent)'>{month.month}월</span></div>", unsafe_allow_html=True)
        if st.button("", icon=":material/chevron_right:", key="cal_next", help="다음 달"):
            st.session_state.cal_month = _shift_month(month, 1)
            st.rerun()
        legend = st.container(key="cal_legend", width="content")

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
    hol = kr_holidays({weeks[0][0].year, weeks[-1][-1].year, today.year, today.year + 1})
    daily = expand_daily(logs, cfg.get("alloc_mode", "spread"))
    in_month = daily[(daily["day"] >= pd.Timestamp(weeks[0][0])) & (daily["day"] <= pd.Timestamp(weeks[-1][-1]))]
    by_day = _cell_entries(in_month, logs, eq)
    present = list(FIXED_CATS)
    shown = legend.pills("구분", present, selection_mode="multi", default=present, key=f"cal_cats2_{month}",
                     label_visibility="collapsed",
                     format_func=lambda c: f"{GROUP_LABEL.get(c, c)} {sum(e['cat'] == c for dd, v in by_day.items() if dd.month == month.month for e in v)}")
    pill_css = ""
    for i, c in enumerate(present, start=1):
        bg, fg = CATS[c]
        b = f'div[class*="st-key-cal_cats"] [data-testid="stButtonGroup"] button:nth-of-type({i})'
        pill_css += (f"{b} {{border: none !important; color: {fg} !important; background: rgba(85,126,230,0.16) !important; opacity: .7;}} "
                     f"{b}[aria-checked='true'] {{background: {bg} !important; opacity: 1;}} "
                     f"{b} p {{color: {fg} !important; font-weight: 700; font-size: .78rem;}} "
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
    picks = _picks()
    if sel_days or len(picks) > 1:  # 여러 날·여러 실적을 골라 둔 상태 (달력 밖을 누르면 풀림)
        st.markdown("<div class='cal-state' data-multi='1'></div>", unsafe_allow_html=True)
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

    grid = card.container(key="calgrid")
    sel = ""
    for week in weeks:
        if week[5].month == month.month:
            sel += f" .st-key-cell_{week[5]} {{background: rgba(85,129,230,0.16) !important;}}"
        if week[6].month == month.month:
            sel += f" .st-key-cell_{week[6]} {{background: rgba(230,85,101,0.16) !important;}}"
    sel += "".join(f".st-key-cell_{d} {{background: rgba(45, 143, 213, 0.12) !important; border: 2px solid var(--accent) !important;}}"
                  for d in sel_days)
    sel += (f" .st-key-day_{today} button strong {{background: var(--accent) !important; color: #fff !important; "
            "box-shadow: 0 2px 6px rgba(45, 143, 213, .35);}")
    if not sel_days:  # 한 날만 선택해도 드래그 선택처럼 또렷하게
        sel += (f" .st-key-calgrid:not([data-js]) .st-key-cell_{day} {{background: rgba(45, 143, 213, 0.12) !important; border: 2px solid var(--accent) !important;"
                " box-shadow: 0 0 0 3px rgba(45, 143, 213, .18) !important;}")
    for dd, ents in by_day.items():  # 실적 스티커 색 (구분별)
        if dd.month != month.month:
            continue
        for e in ents:
            bg, fg = CATS[e["cat"]]
            sel += f" .st-key-er_{dd}_{e['id']} {{--chip-bg: {bg}; --chip-fg: {fg}; --cat-label: '{GROUP_LABEL.get(e['cat'], e['cat'])}';}}"
            if e.get("charger"):
                sel += f" .st-key-er_{dd}_chg{CAT_KEY[e['cat']]} {{--chip-bg: {bg}; --chip-fg: {fg};}}"
    for p in picks:  # Ctrl+클릭으로 고른 실적들
        sel += (f" .st-key-ent_{p['day']}_{p['id']}:not([data-jsmulti='0']) button {{box-shadow: 0 0 0 2px var(--accent) !important;"
                " background: rgba(85,154,230,0.16) !important;}")
    if pick:  # 선택한 실적: 파란 테두리
        sel += (f" .st-key-calgrid:not([data-js]) .st-key-ent_{pick['day']}_{pick['id']} button {{box-shadow: 0 0 0 2px var(--accent) !important;"
                " background: rgba(85,154,230,0.16) !important;}")
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
    card.markdown("<div class='cal-mobile-hint'>날짜를 누르면 그날 실적을 입력할 수 있어요.</div>",
                  unsafe_allow_html=True)

    if right is not None:
        with right:
            _entry_panel(day, logs, eq, comp, cfg)


def _set_end(key: str, start: dt.date, days: int) -> None:
    st.session_state[key] = start + dt.timedelta(days=days - 1)


def _busy_chambers(logs: pd.DataFrame, s: dt.date, e: dt.date, skip: set,
                   chans: pd.DataFrame | None = None) -> dict[int, dict[int, str]]:
    """s~e 에 다른 실적이 쓰는 챔버 → {채널 번호: 업체명}.

    같은 건물의 같은 챔버(예: MV chamber2)를 충방전기 여러 대가 같이 쓰므로, 다른 충방전기 예약이라도
    챔버 이름이 같으면 그 챔버 채널 전체를 쓰는 중으로 봅니다.
    """
    out: dict[int, dict[int, str]] = {}
    if logs.empty or "chambers" not in logs:
        return out
    same: dict[int, list[int]] = {}
    chs_of: dict[int, list[int]] = {}
    if chans is not None and not chans.empty:
        key = {int(i): (c, ch) for i, c, ch in zip(chans["id"], chans["center"], chans["chamber"]) if ch}
        groups: dict[tuple, list[int]] = {}
        for i, k in key.items():
            groups.setdefault(k, []).append(i)
        same = {i: groups[k] for i, k in key.items()}
        chs_of = {int(i): chg.chamber_chs(c, n) for i, c, n in zip(chans["id"], chans["channels"], chans["ch_count"])}
    hit = logs[(logs["chambers"].map(db.to_str) != "") & (logs["start_date"] <= pd.Timestamp(e))
               & (logs["end_date"] >= pd.Timestamp(s)) & ~logs["id"].isin(skip)]
    for c, part, comp_ in zip(hit["chambers"], hit.get("ch_part", [""] * len(hit)), hit["company"]):
        who = db.to_str(comp_) or "내부"
        for i in db.chamber_ids(c):
            for j in same.get(i, [i]):
                chs = chs_of.get(j, [])
                use = chg.used_of(chg.part_of(part, i), chs) if j == i else set(chs)
                for n in use:
                    out.setdefault(j, {}).setdefault(n, who)
    return out


ALL_CH = "전체"  # 채널 칩 맨 앞 '전체' (누르면 모두 고름 / 다시 누르면 모두 뺌)


def _all_chs(key: str, opts: list, on: bool) -> None:
    st.session_state[key] = ([ALL_CH] + list(opts)) if on and opts else []


def _ch_toggle(key: str, opts: list) -> None:
    new, prev = list(st.session_state.get(key) or []), st.session_state.get(key + "_prev") or []
    nums = [n for n in new if n != ALL_CH]
    if ALL_CH in new and ALL_CH not in prev:
        st.session_state[key] = [ALL_CH] + list(opts)
    elif ALL_CH in prev and ALL_CH not in new:
        st.session_state[key] = []
    else:
        st.session_state[key] = ([ALL_CH] if opts and len(nums) == len(opts) else []) + nums


def _close_panel() -> None:
    st.session_state.cal_open = False
    st.session_state.pop("cal_pick", None)


def _new_entry() -> None:
    st.session_state.pop("cal_pick", None)
    st.session_state.pop("cal_lane", None)


def _pick_row(day: dt.date, e: dict) -> None:
    _click_entry(day, e, None, None)


@st.fragment
def _entry_panel(day: dt.date, logs: pd.DataFrame, eq: pd.DataFrame, comp: pd.DataFrame, cfg: dict) -> None:
    """달력 옆 입력 카드: 그날 실적 목록 + 세로로 놓인 입력 칸 (옆으로 넘길 일 없음).

    카드 안에서 장비·업체 등을 고를 때 달력 전체를 다시 그리지 않도록 카드만 따로 다시 그립니다 (fragment).
    달력 모양이 바뀌어야 하는 버튼(닫기·새 실적·목록 선택·삭제·저장)은 st.rerun() 으로 화면 전체를 다시 그립니다.
    """
    ts = pd.Timestamp(day)
    rows = _day_rows(logs, day)
    period = logs[(logs["start_date"] <= ts) & (logs["end_date"] >= ts)] if not logs.empty else logs
    period = period.drop(rows.index) if not period.empty else period

    pickable = db.pick_ids(eq, day)  # 세부장비가 없는 맨 아래 장비만 (예: 5L 믹서(양극))
    short_of = dict(zip(eq["id"], eq["short"]))
    name_of = dict(zip(eq["id"], eq["name"]))
    eq_id = {**dict(zip(eq["label"], eq["id"])), **dict(zip(eq["short"], eq["id"]))}

    chans = db.load_channels()
    chargers = db.charger_ids(eq, chans)
    cat_of = dict(zip(eq["id"].astype(int), (_cat_of(u) for u in eq.get("use", pd.Series([""] * len(eq))))))
    cat_of.update({i: CHARGER_GROUP for i in chargers})  # 충방전기는 '시험(충방전기)'로 따로
    comp_by_name = {r["name"]: r for r in comp.to_dict("records")}
    staff_opts = db.staff_names(list(rows["created_by"]))
    ver = st.session_state.setdefault("cal_ver", 0)

    pick = st.session_state.get("cal_pick")
    orig = {int(r["id"]): r for r in rows.to_dict("records")}
    edit_id = int(pick["id"]) if pick and pick["day"] == day and int(pick["id"]) in orig else None
    series = logs.iloc[0:0]  # 고치는 기간 실적 묶음 (달마다 한 줄)
    if pick and pick["day"] == day and not logs.empty:
        hit = logs[logs["id"] == int(pick["id"])]
        if not hit.empty and per.is_period(hit.iloc[0]):
            series = per.series_rows(logs, int(pick["id"]))
            edit_id = int(series.iloc[0]["id"])
    cur = series.iloc[0].to_dict() if not series.empty else (orig.get(edit_id) if edit_id else None)

    panel = st.container(key="ep_panel")
    with panel:
        total = float(rows["hours"].sum()) if not rows.empty else 0
        with st.container(key="ep_head", horizontal=True, vertical_alignment="top"):
            st.markdown(f"<div class='ep-h'><span class='ep-d'>{day.month}월 {day.day}일"
                        f"<em>{WEEKDAYS[day.weekday()]}요일</em></span>"
                        f"<span class='ep-n'>실적 {len(rows)}건 · {_hours(total)}</span></div>",
                        unsafe_allow_html=True, width="stretch")
            if st.button("실적 추가", icon=":material/add:", key="ep_new", help="이 날짜에 실적을 하나 더 넣어요"):
                _new_entry()
                st.rerun()
            if st.button("", icon=":material/close:", key="ep_close", help="닫기"):
                _close_panel()
                st.rerun()
        # 그날 실적 목록 (누르면 아래 칸에서 고침)
        with st.container(key="ep_list", gap="small"):
            for r in rows.sort_values("id").to_dict("records"):
                rid = int(r["id"])
                c = _log_cat(r["purpose"], int(r["equip_id"]) in db.charger_ids(eq))
                e = {"id": rid, "rec": r, "period": "", "equip": name_of.get(r["equip_id"], "?"),
                     "company": db.to_str(r["company"]) or "내부", "hours": float(r["hours"])}
                if st.button(f"{_md(e['equip'])}\n\n{_hours(e['hours'])} · {_md(e['company'])}",
                             key=f"ep_row_{CAT_KEY[c]}_{rid}", width="stretch",
                             type="primary" if rid == edit_id else "secondary"):
                    _pick_row(day, e)
                    st.rerun()

        st.session_state.pop("company_added", None)
        if eq.empty or not staff_opts:
            st.warning("장비와 담당자를 먼저 '기준 정보'에서 등록하세요.")
            return

        last_staff = st.session_state.get("last_staff") or st.session_state.get("me")
        lane = st.session_state.get("cal_lane")
        groups = ["전체"] + [c for c in CARD_GROUPS if any(cat_of.get(i) == c for i in pickable)]
        cur_cat = cat_of.get(int(cur["equip_id"])) if cur is not None else None
        want = lane if lane in groups else (cur_cat if cur_cat in groups else "전체")
        eq_opts = [short_of[i] for i in pickable]
        if cur is not None and short_of.get(cur["equip_id"]) not in eq_opts:
            eq_opts.append(short_of.get(cur["equip_id"]))
        comp_opts = list(comp_by_name)
        if cur is not None and db.to_str(cur["company"]) and cur["company"] not in comp_opts:
            comp_opts.append(cur["company"])
        ov, _, content = seed.parse_detail(cur["detail"]) if cur is not None else ("", "", "")
        k = f"{day}_{edit_id or 'new'}_{ver}"

        def ix(opts, v):
            return opts.index(v) if v in opts else None

        form = st.container(key="ep_form")
        with form:
            is_series = not series.empty
            v_mode = st.segmented_control("입력 방식", ["하루", "기간"], key=f"ep_mode_{k}",
                                          default="기간" if is_series else "하루", label_visibility="collapsed",
                                          format_func=lambda m: {"하루": "단기", "기간": "장기"}[m],
                                          help="장기: 며칠~몇 달 계속 도는 시험을 한 번에 입력 (달력에는 매일 표시)") or (
                                              "기간" if is_series else "하루")
            if len(groups) > 2:  # 시험·제조·분석 중 하나만 골라 목록을 짧게
                with st.container(key="ep_grp"):
                    g = st.segmented_control("장비 구분", groups, default=want, key=f"ep_grp_{k}_{lane}",
                                             format_func=lambda c: GROUP_LABEL.get(c, c),
                                             label_visibility="collapsed") or "전체"
                if g != "전체":
                    keep = short_of.get(cur["equip_id"]) if cur is not None else None
                    in_g = [i for i in pickable if cat_of.get(i) == g]
                    if g == CHARGER_GROUP and not chans.empty:  # 충방전기: 센터를 누르면 그 센터 충방전기만
                        cen_of = {int(e): db.CENTER_SHORT.get(c, c) for e, c in zip(chans["equip_id"], chans["center"])
                                  if pd.notna(e) and c}
                        cens = [c for c in db.CENTERS if c in cen_of.values()]
                        cur_cen = cen_of.get(int(cur["equip_id"])) if cur is not None else None
                        if len(cens) > 1:
                            cen = st.pills("센터", cens, default=cur_cen if cur_cen in cens else None,
                                           key=f"ep_cen_{k}", label_visibility="collapsed")
                            if cen:
                                in_g = [i for i in in_g if cen_of.get(i) == cen]
                    eq_opts = [short_of[i] for i in in_g]
                    if keep and keep not in eq_opts:
                        eq_opts.append(keep)
            v_eq = st.selectbox("장비", eq_opts, index=ix(eq_opts, short_of.get(cur["equip_id"]) if cur is not None else None),
                                placeholder="장비 이름을 입력해 찾기", key=f"ep_eq_{k}")
            where = db.path_text(eq, eq_id[v_eq]) if v_eq in eq_id else ""
            if where:  # 어느 주장비 소속인지 작게 (시간은 주장비에 합산)
                st.markdown(f"<div class='ep-path'><span>소속</span>{html.escape(where)}</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2, gap="small")
            v_comp = c1.selectbox("업체", comp_opts,
                                  index=ix(comp_opts, db.to_str(cur["company"])) if cur is not None else None,
                                  placeholder="내부면 비워 두기", key=f"ep_comp_{k}")
            v_staff = c2.selectbox("담당자", staff_opts,
                                   index=ix(staff_opts, db.to_str(cur["created_by"]) if cur is not None else last_staff),
                                   placeholder="담당자 선택", key=f"ep_staff_{k}")
            if st.button("새 업체 등록", icon=":material/add:", key="ep_newcomp", type="tertiary"):
                new_company_dialog()
            v_type = st.segmented_control("활용유형", seed.USAGE_TYPES, key=f"ep_type_{k}",
                                          default=db.to_str(cur["usage_type"]) if cur is not None else "외부")
            v_purp = st.segmented_control("사용목적", seed.purpose_choices(db.to_str(cur["purpose"]) if cur is not None else ""),
                                          format_func=seed.purpose_label, key=f"ep_purp_{k}",
                                          default=db.to_str(cur["purpose"]) if cur is not None
                                          else LANE_PURPOSE.get(lane, "생산"))
            v_eid = eq_id.get(v_eq)
            chunks: list[dict] = []
            if v_mode == "기간":
                p_start, p_end = per.series_span(series) if is_series else (day, day + dt.timedelta(days=6))
                c1, c2 = st.columns(2, gap="small")
                v_ps = c1.date_input("시작일", value=p_start, format="YYYY-MM-DD", key=f"ep_ps_{k}")
                if f"ep_pe_{k}" not in st.session_state or st.session_state[f"ep_pe_{k}"] < v_ps:
                    st.session_state[f"ep_pe_{k}"] = max(p_end, v_ps)
                v_pe = c2.date_input("종료일", min_value=v_ps, format="YYYY-MM-DD", key=f"ep_pe_{k}",
                                     help="끝나는 날을 모르면 예상 날짜로 넣고, 나중에 바꾸면 돼요.")
                with st.container(horizontal=True, gap="small", key="ep_quick"):
                    for lab, days in (("+1주", 7), ("+2주", 14), ("+1달", 30), ("+3달", 91), ("+6달", 182)):
                        st.button(lab, key=f"ep_q{days}_{k}", on_click=_set_end, args=(f"ep_pe_{k}", v_ps, days),
                                  type="tertiary")
                c1, c2 = st.columns(2, gap="small", vertical_alignment="bottom")
                v_pd = num_input(c1, "하루 사용시간(h)", f"ep_pd_{k}", per.per_day_of(series) if is_series else 8, 1, 1, 24)
                v_skip = c2.toggle("주말·공휴일 빼기", key=f"ep_skip_{k}",
                                   value=not is_series or all(db.to_str(x) == "N" for x in series["include_holidays"]),
                                   help="켜 두면 평일만 시간에 넣어요.")
                chunks = per.split_period(v_ps, v_pe, v_pd, v_skip) if v_pe >= v_ps else []
                n_days = sum(c["days"] for c in chunks)
                tot = sum(c["hours"] for c in chunks)
                split = f" · {len(chunks)}개월로 나눠 저장" if len(chunks) > 1 else ""
                st.markdown(f"<div class='ep-sum'><b>{n_days}일 · 총 {tot:,}h</b>"
                            f"<span>달력에 하루 {v_pd:g}h씩 자동으로 들어가요{split}</span></div>", unsafe_allow_html=True)
                v_h = tot
            else:
                v_ps = v_pe = day
                v_skip = False
            c1, c2 = st.columns(2, gap="small")
            if v_mode == "하루":
                v_h = num_input(c1, "사용시간(h)", f"ep_h_{k}",
                                float(cur["hours"]) if cur is not None and not is_series else 8, 1, 0, 24)
                v_s = num_input(c2, "시료수", f"ep_s_{k}", float(cur["samples"]) if cur is not None else 1, 1, 0)
            else:
                v_s = num_input(c1, "시료수", f"ep_s_{k}", float(cur["samples"]) if cur is not None else 1, 1, 0)
            # 충방전기: 챔버 고르기 (그 기간에 이미 쓰는 챔버는 업체명이 붙음)
            v_ch, v_part, busy, picked, all_chs = [], "", {}, {}, {}
            mine = chans[chans["equip_id"] == v_eid] if v_eid is not None and not chans.empty else chans.iloc[0:0]
            if not mine.empty:
                skip_ids = set(series["id"].astype(int)) | ({int(edit_id)} if edit_id else set())
                used = _busy_chambers(logs, v_ps, v_pe, skip_ids, chans)
                ch_ids = [int(i) for i in mine["id"]]
                all_chs = {int(i): chg.chamber_chs(c, n) for i, c, n in zip(mine["id"], mine["channels"], mine["ch_count"])}
                # 챔버 채널이 모두 다른 실적에 잡혀 있으면 '쓰는 중' (업체명), 일부만이면 'n/m 사용'
                busy = {i: next(iter(used[i].values())) for i in ch_ids
                        if i in used and all_chs[i] and set(all_chs[i]) <= set(used[i])}
                part_busy = {i: f"{len(set(used[i]) & set(all_chs[i]))}/{len(all_chs[i])}ch 사용 중"
                             for i in ch_ids if i in used and i not in busy}
                ch_name = {int(i): " · ".join(x for x in (c, f"ch {n}" if n else "") if x) or u
                           for i, c, u, n in zip(mine["id"], mine["chamber"], mine["unit"], mine["channels"])}
                ch_cyc = dict(zip(mine["id"].astype(int), mine["cycler"]))
                if len(ch_ids) == 1:  # 챔버가 하나면 고를 필요 없이 바로 채널 (2026-11-10)
                    v_ch = ch_ids
                else:
                    st.markdown("<div class='ep-chlab'>챔버</div>", unsafe_allow_html=True)
                    v_ch = None
                v_ch = v_ch or st.pills("챔버", ch_ids, selection_mode="multi", key=f"ep_ch_{k}_{v_eid}",
                                default=[i for i in db.chamber_ids(cur.get("chambers")) if i in ch_ids] if cur is not None else None,
                                format_func=lambda i: (ch_name.get(i) or f"#{i}") + (
                                    f" · {busy[i]}" if i in busy else f" · {part_busy[i]}" if i in part_busy else ""),
                                label_visibility="collapsed",
                                help="cycler: " + ", ".join(dict.fromkeys(c for c in ch_cyc.values() if c))) or []
                pill_css = "".join(
                    f'div[class*="st-key-ep_ch_"] [data-testid="stButtonGroup"] button:nth-of-type({n}) '
                    "{background: rgba(230,85,114,0.16) !important; color: #B8435C !important; border-color: rgba(230,85,120,0.3) !important;}"
                    for n, i in enumerate(ch_ids, start=1) if i in busy and i not in v_ch)
                if pill_css:
                    st.markdown(f"<style>{pill_css}</style>", unsafe_allow_html=True)
                # 고른 챔버마다 채널을 마우스로 (그 챔버에 있는 채널만, 다른 실적이 쓰는 채널은 빠짐)
                picked: dict[int, list[int]] = {}
                for i in v_ch:
                    chs = all_chs.get(i, [])
                    free = [n for n in chs if n not in used.get(i, {})]
                    if not chs:
                        continue
                    was = chg.part_of(cur.get("ch_part"), i) if cur is not None else ""
                    pk = f"ep_cn_{k}_{i}"
                    if pk not in st.session_state:
                        st.session_state[pk] = [n for n in (chg.nums(was) or free) if n in free]
                        if free and len(st.session_state[pk]) == len(free):
                            st.session_state[pk] = [ALL_CH] + st.session_state[pk]
                    elif any(n not in free and n != ALL_CH for n in st.session_state[pk] or []):
                        st.session_state[pk] = [n for n in st.session_state[pk] if n in free or n == ALL_CH]
                    st.session_state[pk + "_prev"] = list(st.session_state[pk] or [])
                    n_on = len([n for n in st.session_state[pk] or [] if n != ALL_CH])
                    with st.container(key=f"ep_cbox_{k}_{i}", horizontal=True, gap="small", vertical_alignment="center"):
                        st.markdown(f"<div class='ep-chlab'>{html.escape(mine.set_index('id')['chamber'].get(i, '') or ch_name.get(i, ''))} 채널 "
                                    f"<b>{n_on}</b>/{len(chs)}</div>", unsafe_allow_html=True)
                        st.space("stretch")
                        st.button("비우기", key=f"ep_cnz_{k}_{i}", type="tertiary", on_click=_all_chs, args=(pk, free, False))
                    picked[i] = [n for n in st.pills(f"채널 {i}", [ALL_CH] + free, selection_mode="multi", key=pk,
                                                     on_change=_ch_toggle, args=(pk, free),
                                                     label_visibility="collapsed") or [] if n != ALL_CH]
                part = {i: chg.fmt(p) for i, p in picked.items() if set(p) != set(all_chs.get(i, []))}
                if len(v_ch) == 1:
                    v_part = part.get(v_ch[0], "")
                else:
                    v_part = "|".join(f"{i}:{p}" for i, p in part.items())
            # 사용료는 시험이 끝난 뒤 따로 매기므로 입력 카드에서는 받지 않음 (고칠 때는 기존 값 그대로 둠)
            v_f = db.to_num(cur["fee"], 0) if cur is not None else 0
            v_ov = st.text_input("지원개요", ov, placeholder="예: 전극 코팅", key=f"ep_ov_{k}")
            with st.expander("지원내용 · 기타", expanded=bool(content or (cur is not None and db.to_str(cur["etc"])))):
                v_ct = st.text_area("지원내용", content, height=80, placeholder="자세한 내용", key=f"ep_ct_{k}")
                v_etc = st.text_input("기타", db.to_str(cur["etc"]) if cur is not None else "", key=f"ep_etc_{k}")

            with st.container(horizontal=True, gap="small", key="ep_btns"):
                save = st.button("저장" if cur is not None else "추가", icon=":material/check:", type="primary",
                                 key="ep_save", width="stretch")
                if cur is not None:
                    if st.button("삭제", icon=":material/delete:", key="ep_del"):
                        if is_series:
                            a, b = per.series_span(series)
                            st.session_state.cal_delask = {
                                "kind": "ids", "ids": [int(i) for i in series["id"]],
                                "text": f"{a:%m/%d}~{b:%m/%d} 기간 실적({_cut(v_eq or '', 16)})을 삭제할까요?"}
                        else:
                            _ask_delete()
                        st.rerun()
        if save:
            row = {"장비": v_eq, "업체": v_comp, "담당자": v_staff, "활용유형": v_type, "사용목적": v_purp,
                   "사용시간": v_h, "시료수": v_s, "사용료": v_f, "지원개요": v_ov, "지원내용": v_ct, "기타": v_etc}
            base = ({k_: cur.get(k_) for k_ in db.LOG_FIELDS if k_ in cur} if cur is not None else {})
            base.update(start_date=day, end_date=day, include_holidays="N" if v_skip else "Y",
                        chambers=",".join(str(i) for i in v_ch), ch_part=v_part.strip() if v_ch else "")
            errors = []
            if v_mode == "기간" and not chunks:
                errors.append("기간에 시간을 넣을 날이 없어요. 종료일이나 '주말·공휴일 빼기'를 확인하세요.")
            if not mine.empty and (not v_ch or any(not picked.get(i) for i in v_ch if all_chs.get(i))):
                errors.append("채널을 고르세요.")
            clash = [f"{ch_name.get(i, i)}({busy[i]})" for i in v_ch if i in busy] if not mine.empty else []
            if clash:
                errors.append("그 기간에 이미 쓰는 채널이에요: " + ", ".join(clash))
            if not v_eq:
                errors.append("장비를 고르세요.")
            if not v_staff:
                errors.append("담당자를 고르세요.")
            if not v_type or not v_purp:
                errors.append("활용유형과 사용목적을 고르세요.")
            rec = _record(row, base, comp_by_name, eq_id, cfg) if not errors else None
            if rec is not None and v_mode == "기간":
                for c in chunks:
                    errors += [e_ for e_ in rules.validate(rec | c) if e_ not in errors]
            elif rec is not None:
                errors += rules.validate(rec)
                same = sum(db.to_num(r["hours"], 0) for rid, r in orig.items()
                           if rid != edit_id and int(r["equip_id"]) == rec["equip_id"])
                if rec["equip_id"] not in chargers and same + db.to_num(rec["hours"], 0) > 24:
                    errors.append(f"이 장비의 하루 사용시간 합계가 {same + rec['hours']:,.0f}h로 24h를 넘습니다.")
            if errors:
                for e_ in errors:
                    st.error(e_)
            else:
                with db.undo_group(f"{day:%m/%d} {'수정' if cur is not None else '추가'}"):
                    if v_mode == "기간" or is_series:
                        old = series if is_series else (logs[logs["id"] == edit_id] if cur is not None else logs.iloc[0:0])
                        key = (db.to_str(cur.get("series")) if cur is not None else "") or (
                            f"S{db._new_ids(1)[0]}" if len(chunks) > 1 else "")
                        parts = chunks if v_mode == "기간" else [{"start_date": day, "end_date": day, "hours": rec["hours"]}]
                        upd, add, gone = per.plan_changes(old, parts, rec, key if v_mode == "기간" else "")
                        db.update_logs(upd)
                        db.insert_logs(add)
                        db.delete_logs(gone)
                    elif cur is not None:
                        db.update_logs({edit_id: rec})
                    else:
                        db.insert_logs([rec])
                st.session_state.last_staff = rec["created_by"]
                st.session_state.cal_ver = ver + 1
                st.session_state.pop("cal_pick", None)
                st.session_state.cal_saved = (f"{day:%m/%d} {_cut(v_eq, 20)} "
                                              + ("고쳤습니다" if cur is not None else "추가했습니다"))
                st.rerun()

        if not period.empty:
            with st.expander(f"이 날이 포함된 기간 실적 {len(period)}건", expanded=False):
                pv = period.reset_index(drop=True)
                ev = st.dataframe(pd.DataFrame({
                    "장비": pv["equip_id"].map(short_of), "업체": pv["company"].replace("", "(내부)"),
                    "기간": [f"{a:%m/%d}~{b:%m/%d}" for a, b in zip(pv["start_date"], pv["end_date"])],
                    "시간": pv["hours"].astype(int),
                }), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                    key=f"cal_period_{day}_{ver}_{st.session_state.get('cal_pnonce', 0)}")
                picked = ev.selection.rows if ev else []
                if picked:  # 고른 기간 실적을 위 카드에서 고침
                    r = pv.iloc[picked[0]]
                    st.session_state.cal_pick = {"day": day, "id": int(r["id"]), "rec": r.to_dict(), "period": True,
                                                 "label": f"{short_of.get(r['equip_id'], '?')} · {db.to_str(r['company']) or '내부'}"}
                    st.session_state.cal_pnonce = st.session_state.get("cal_pnonce", 0) + 1
                    st.rerun()
