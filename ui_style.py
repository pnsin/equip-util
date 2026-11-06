"""공통 화면 스타일 — 기본 테마 "navy": 남색 메뉴 + 밝은 본문 (2026-11-02 사용자 선택, Power BI형).

앞으로 추가하는 화면도 이 규칙을 기본으로 한다.
- 색은 아래 TOKENS만 쓴다. 화면 코드에 색 값을 직접 쓰지 말고 CSS 변수 var(--이름)이나 이 파일의 상수를 쓴다.
- 본문은 밝게, 색은 '뜻'이 있을 때만 (목표 달성·미달, 경고).
- 글꼴은 Pretendard, 숫자는 같은 폭(tabular) — .streamlit/config.toml 테마와 같은 값.
- 쪽 제목은 page_header, 영역 제목은 section_bar 또는 st.subheader (둘 다 같은 모양).
- 글자 크기 단계: 0.75 · 0.85 · 0.95 · 1.05 · 1.25 · 1.6rem.
"""
from __future__ import annotations

import base64
import functools
import html
import os

import streamlit as st
from core.terms import w

SYSTEM_TITLE = "장비 관리 시스템"
TEAM_NAME = "배터리산업팀"

# ------------------------------------------------------------------ 테마 (색 토큰)
# 화면 코드에는 색 값을 직접 쓰지 말고 var(--이름) 이나 T["이름"] 을 쓴다.
# 'st' 는 .streamlit/config.toml [theme] 에 넣는 값 (Streamlit 기본 위젯 색).
THEMES = {
    # battery-app과 같은 다크 관제실형
    "dark": {
        "bg": "#0F141A", "panel": "#151C24", "panel2": "#1A222C", "deep": "#111820",
        "line": "#263140", "line2": "#2E3A49", "ink": "#E3E9EF", "muted": "#8B97A5", "dim": "#5F6B7A",
        "accent": "#2D8FD5", "accent-hi": "#4FB3F0", "accent-bg": "#12263A",
        "ok": "#5CCB93", "ok-bg": "#12301F", "ng": "#FF8A7A", "ng-bg": "#3A1714", "warn": "#F0B35C", "warn-bg": "#33260F",
        "bar-off": "#3A4656", "shadow": "0 24px 60px rgba(0,0,0,.45)", "card-shadow": "none",
        "side": "#0A0E13", "side-line": "#263140", "side-ink": "#E3E9EF", "side-muted": "#8B97A5", "side-dim": "#5F6B7A",
        "side-hover": "#151C24", "side-active": "#1B2633", "side-active-ink": "#4FB3F0",
        "logo": "logo_dark.png", "base": "dark",
    },
    # A. 흰 바탕 카드형 (Looker Studio · Metabase)
    "light": {
        "bg": "#F5F7FA", "panel": "#FFFFFF", "panel2": "#F1F4F8", "deep": "#F8FAFC",
        "line": "#E3E8EF", "line2": "#CBD3DD", "ink": "#1F2937", "muted": "#5B6675", "dim": "#98A2B0",
        "accent": "#1A73E8", "accent-hi": "#1A73E8", "accent-bg": "#E8F0FE",
        "ok": "#188038", "ok-bg": "#E6F4EA", "ng": "#D93025", "ng-bg": "#FCE8E6", "warn": "#B06000", "warn-bg": "#FEF3E0",
        "bar-off": "#C9D1DC", "shadow": "0 12px 40px rgba(31,41,55,.10)", "card-shadow": "0 1px 2px rgba(31,41,55,.06)",
        "side": "#FFFFFF", "side-line": "#E3E8EF", "side-ink": "#1F2937", "side-muted": "#5B6675", "side-dim": "#98A2B0",
        "side-hover": "#F1F4F8", "side-active": "#E8F0FE", "side-active-ink": "#1A73E8",
        "logo": "logo_light.png", "base": "light",
    },
    # B. 남색 메뉴 + 밝은 본문 (Power BI)
    "navy": {
        "bg": "#F2F4F7", "panel": "#FFFFFF", "panel2": "#F3F5F8", "deep": "#F7F8FA",
        "line": "#E1E5EB", "line2": "#C8D0DA", "ink": "#1B2430", "muted": "#5A6474", "dim": "#97A1AE",
        "accent": "#5B6CFF", "accent-hi": "#5B6CFF", "accent-bg": "#EEF0FF",
        "ok": "#1E8E5A", "ok-bg": "#E5F4EC", "ng": "#C9372C", "ng-bg": "#FBE9E7", "warn": "#B5650B", "warn-bg": "#FDF1E2",
        "bar-off": "#C5CDD8", "shadow": "0 12px 40px rgba(17,28,46,.14)", "card-shadow": "0 1px 3px rgba(17,28,46,.08)",
        "side": "#132036", "side-line": "#22324D", "side-ink": "#E4EAF2", "side-muted": "#9DAABD", "side-dim": "#6F7F96",
        "side-hover": "#1B2B45", "side-active": "#25395A", "side-active-ink": "#FFFFFF",
        "logo": "logo_dark.png", "base": "light",
    },
    # C. 따뜻한 회색 리포트형 (Tableau)
    "warm": {
        "bg": "#FAF9F7", "panel": "#FFFFFF", "panel2": "#F4F3F0", "deep": "#F8F7F4",
        "line": "#E7E4DE", "line2": "#D3CFC7", "ink": "#2A2A2A", "muted": "#66625B", "dim": "#A39E95",
        "accent": "#4E79A7", "accent-hi": "#3F6A99", "accent-bg": "#EAF0F6",
        "ok": "#3E8E41", "ok-bg": "#EAF4EA", "ng": "#C8454A", "ng-bg": "#FBEAEA", "warn": "#D87A16", "warn-bg": "#FDF0E1",
        "bar-off": "#D6D1C8", "shadow": "0 12px 40px rgba(42,42,42,.10)", "card-shadow": "none",
        "side": "#F1EFEB", "side-line": "#E2DED6", "side-ink": "#2A2A2A", "side-muted": "#66625B", "side-dim": "#A39E95",
        "side-hover": "#E8E5DF", "side-active": "#E1E8F0", "side-active-ink": "#3F6A99",
        "logo": "logo_light.png", "base": "light",
    },
    # D. 말랑한 업무툴 (2026-11-06 전체 디자인 통일): 흰 메뉴 + 라벤더블루 한 색 + 옅은 그림자
    "soft": {
        "bg": "#F7F8FC", "panel": "#FFFFFF", "panel2": "#F3F4FA", "deep": "#FAFBFE",
        "line": "#E6E9F2", "line2": "#D5DAE6", "ink": "#1E2433", "muted": "#6B7385", "dim": "#A3AAB9",
        "accent": "#5B6CFF", "accent-hi": "#4B5BEA", "accent-bg": "#EEF0FF",
        "ok": "#1A9A6C", "ok-bg": "#E6F6EF", "ng": "#E5484D", "ng-bg": "#FDECEC", "warn": "#D98B1E", "warn-bg": "#FEF4E4",
        "bar-off": "#DDE1EC", "shadow": "0 12px 40px rgba(30,36,51,.10)", "card-shadow": "0 1px 3px rgba(30,36,51,.05)",
        "side": "#FFFFFF", "side-line": "#E6E9F2", "side-ink": "#1E2433", "side-muted": "#6B7385", "side-dim": "#A3AAB9",
        "side-hover": "#F3F4FA", "side-active": "#EEF0FF", "side-active-ink": "#4B5BEA",
        "logo": "logo_light.png", "base": "light",
    },
}
THEME_NAME = os.environ.get("EQUIP_THEME", "soft")
TOKENS = {k: v for k, v in THEMES.get(THEME_NAME, THEMES["dark"]).items() if k not in ("logo", "base")}
T = TOKENS

# 그래프 색 (plotly)
CHART_FONT = dict(family="Pretendard Variable, Pretendard, Noto Sans KR, Malgun Gothic, sans-serif", color=T["ink"], size=12)
CHART_GRID = T["line"]
SERIES = [T["accent"], T["ok"], T["warn"], "#8E6CC0", "#D45087", "#2A9D8F", T["muted"]]

_DIR = os.path.dirname(__file__)
LOGO_PATH = os.path.join(_DIR, "assets", THEMES.get(THEME_NAME, THEMES["dark"])["logo"])
FAVICON_PATH = os.path.join(_DIR, "assets", "favicon.png")


@functools.lru_cache(maxsize=4)
def _data_uri(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def favicon():
    return FAVICON_PATH if os.path.exists(FAVICON_PATH) else "📊"


_VARS = ":root { " + " ".join(f"--{k}: {v};" for k, v in TOKENS.items()) + " }"

_CSS = """
<style>
  @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css");
  __VARS__
  .block-container { padding-top: 3.6rem; padding-bottom: 4rem; max-width: 1600px; }
  .stApp:not(:has(.login-bg)) [data-testid="stMainBlockContainer"] { padding-left: 2.5rem !important; padding-right: 2.5rem !important; }
  /* 접속 화면: 왼쪽 메뉴 칸은 숨김 (메뉴는 접속 전에도 만들어 둬야 접속 뒤 늘 펼쳐진 채로 시작함) */
  .stApp:has(.login-bg) [data-testid="stSidebar"], .stApp:has(.login-bg) [data-testid="stExpandSidebarButton"],
  .stApp:has(.login-bg) [data-testid="stSidebarCollapsedControl"] { display: none !important; }
  [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { font-family: "Pretendard Variable", "Pretendard", "Noto Sans KR", "Malgun Gothic", sans-serif; }
  [data-testid="stAppViewContainer"] { background: var(--bg); }
  footer { visibility: hidden; }
  [data-testid="stHeader"] { background: color-mix(in srgb, var(--bg) 85%, transparent); backdrop-filter: blur(6px); }

  /* ---------- 쪽 머리: 작은 머리글 + 제목 + 표시 + 오른쪽 설명 ---------- */
  .ph { display: flex; align-items: flex-end; justify-content: space-between; gap: .6rem 1.5rem; flex-wrap: wrap;
        padding: 0 0 .8rem 0; margin: 0 0 1.1rem 0; border-bottom: 1px solid var(--line); }
  .ph .eb { font-size: .75rem; font-weight: 600; letter-spacing: .14em; color: var(--muted); margin-bottom: .15rem; }
  .ph .t { display: flex; align-items: center; gap: .7rem; font-size: 1.6rem; font-weight: 700; letter-spacing: -.02em;
        line-height: 1.25; color: var(--ink); }
  .ph .chip { font-size: .75rem; font-weight: 600; letter-spacing: 0; padding: .12rem .65rem; border-radius: 999px;
        color: var(--ac); border: 1px solid color-mix(in srgb, var(--ac) 45%, transparent);
        background: color-mix(in srgb, var(--ac) 14%, transparent); }
  .ph .desc { font-size: .85rem; color: var(--muted); max-width: 560px; line-height: 1.5; word-break: keep-all; text-align: right; }
  @media (max-width: 760px) { .ph .desc { text-align: left; } .ph .t { font-size: 1.35rem; } }

  /* ---------- 영역 제목: st.subheader · section_bar 모두 같은 모양 ---------- */
  [data-testid="stHeading"] h3, .sec-bar { display: flex; align-items: center; gap: .6rem;
        font-size: 1.05rem; font-weight: 700; color: var(--ink) !important; letter-spacing: 0;
        padding: 0 0 .55rem 0; margin: 1.6rem 0 .8rem 0; border-bottom: 1px solid var(--line); }
  [data-testid="stHeading"] h3 * { color: var(--ink) !important; }
  .sec-bar .no { display: inline-flex; align-items: center; justify-content: center; width: 1.5rem; height: 1.5rem;
        border-radius: 4px; background: var(--panel2); border: 1px solid var(--line2); color: var(--accent-hi);
        font-family: "IBM Plex Mono", monospace; font-size: .85rem; font-weight: 600; flex: none; }
  .sec-bar .sub { margin-left: auto; font-size: .85rem; font-weight: 400; color: var(--muted); text-align: right; }
  .sec-bar.first { margin-top: .4rem; }

  /* ---------- 버튼 (크기는 건드리지 않음: 달력 칸 버튼도 같은 primary를 씀) ---------- */
  .stButton button[kind="primary"], .stDownloadButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {
        background: var(--accent); border-color: var(--accent); color: #FFFFFF !important; font-weight: 600; }
  .stButton button[kind="primary"] p, .stDownloadButton button[kind="primary"] p, .stFormSubmitButton button[kind="primary"] p { color: #FFFFFF !important; }
  .stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover {
        background: var(--accent-hi); border-color: var(--accent-hi); }
  .stButton button[kind="primary"]:disabled, .stDownloadButton button[kind="primary"]:disabled, .stFormSubmitButton button[kind="primary"]:disabled {
        background: var(--panel2); border-color: var(--line2); }
  .stButton button[kind="primary"]:disabled p { color: var(--dim) !important; }

  /* ---------- 숫자: 같은 폭 ---------- */
  [data-testid="stMetricValue"], [data-testid="stNumberInputContainer"] input, .kpi b { font-variant-numeric: tabular-nums; }

  /* ---------- 지표 카드 ---------- */
  [data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 4px; padding: .6rem .85rem; box-shadow: var(--card-shadow); }
  [data-testid="stMetricLabel"] { color: var(--muted); font-size: .85rem; }
  [data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 600; color: var(--ink); }
  [data-testid="stMetricDelta"] { font-size: .85rem; }

  /* ---------- 테두리 상자 ---------- */
  [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-color: var(--line); }
  .stTabs [data-baseweb="tab-list"] { gap: .4rem; border-bottom: 1px solid var(--line); }
  .stTabs [data-baseweb="tab"] p { font-size: .95rem; font-weight: 600; }
  [data-testid="stExpander"] details { border-color: var(--line); background: var(--panel); }
  [data-testid="stExpander"] summary p { font-weight: 600; }
  [data-testid="stCaptionContainer"] { color: var(--muted); }

  /* ---------- 빈 화면 안내 ---------- */
  .empty { border: 1px dashed var(--line2); border-radius: 6px; background: var(--panel); padding: 1.6rem 1.4rem; text-align: center; margin: .4rem 0 1rem 0; }
  .empty .ic { font-size: 1.6rem; color: var(--dim); line-height: 1; margin-bottom: .5rem; }
  .empty .h { font-size: 1.05rem; font-weight: 700; color: var(--ink); margin-bottom: .3rem; }
  .empty .b { font-size: .85rem; color: var(--muted); line-height: 1.6; word-break: keep-all; }
  .soon { max-width: 460px; margin: 3rem auto 2rem auto; text-align: center; background: var(--panel); border: 1px solid var(--line); border-radius: 22px; box-shadow: var(--card-shadow); padding: 2.4rem 1.6rem 2rem 1.6rem; }
  .soon-ic { width: 84px; height: 84px; margin: 0 auto 1rem auto; border-radius: 50%; background: var(--accent-bg); display: flex; align-items: center; justify-content: center; font-size: 2.4rem; animation: soon-bob 2.6s ease-in-out infinite; }
  .soon-tag { display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .08em; color: var(--accent); background: var(--accent-bg); border-radius: 999px; padding: .18rem .7rem; margin-bottom: .7rem; }
  .soon-h { font-size: 1.2rem; font-weight: 700; color: var(--ink); margin-bottom: .35rem; }
  .soon-b { font-size: .88rem; color: var(--muted); line-height: 1.6; word-break: keep-all; }
  .soon-dots { margin-top: 1.1rem; display: flex; gap: .4rem; justify-content: center; }
  .soon-dots i { width: 7px; height: 7px; border-radius: 50%; background: var(--line2); animation: soon-dot 1.4s ease-in-out infinite; }
  .soon-dots i:nth-child(2) { animation-delay: .2s; } .soon-dots i:nth-child(3) { animation-delay: .4s; }
  @keyframes soon-bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
  @keyframes soon-dot { 0%, 100% { background: var(--line2); } 50% { background: var(--accent); } }

  /* ---------- 안내 한 줄 (회색 띠) ---------- */
  .note { font-size: .85rem; color: var(--muted); background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--line2);
        border-radius: 4px; padding: .5rem .8rem; margin: 0 0 .8rem 0; line-height: 1.6; word-break: keep-all; }
  .note b { color: var(--ink); font-weight: 600; }

  /* ---------- 목표 진행 막대 ---------- */
  .goal { background: var(--panel); border: 1px solid var(--line); border-radius: 4px; padding: .7rem .9rem .8rem .9rem; margin: .6rem 0 .4rem 0; }
  .goal .row { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; flex-wrap: wrap; font-size: .85rem; color: var(--muted); }
  .goal .row b { color: var(--ink); font-weight: 600; }
  .goal .bar { position: relative; height: 8px; border-radius: 999px; background: var(--deep); border: 1px solid var(--line); margin-top: .5rem; overflow: hidden; }
  .goal .bar > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; background: var(--c); }

  /* ---------- 왼쪽 메뉴 ---------- */
  [data-testid="stSidebar"] { background: var(--side); border-right: 1px solid var(--side-line); }
  section[data-testid="stSidebar"] { width: 260px !important; min-width: 260px !important; max-width: 260px !important; }
  [data-testid="stSidebarHeader"] { height: 2.2rem; min-height: 0; padding-bottom: 0; }
  [data-testid="stSidebarUserContent"] { padding-top: 0; }
  [data-testid="stSidebar"] .brand { padding: 0 0 .9rem 0; margin: 0 0 .2rem 0; border-bottom: 1px solid var(--side-line); }
  [data-testid="stSidebar"] .brand img { width: 140px; display: block; margin: 0 0 .7rem 0; }
  [data-testid="stSidebar"] .brand-title { font-size: 1.05rem; font-weight: 700; color: var(--side-ink); line-height: 1.3; margin: 0; white-space: nowrap; letter-spacing: -.01em; }
  [data-testid="stSidebar"] .brand-sub { font-size: .75rem; color: var(--side-muted); margin: .2rem 0 0 0; }
  [data-testid="stSidebar"] .nav-group { font-size: .75rem; font-weight: 600; letter-spacing: .12em; color: var(--side-dim); margin: 1rem 0 .2rem 0; padding: 0 .6rem; }
  [data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { margin-bottom: -0.85rem; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a { padding: .38rem .6rem; border-radius: 4px; margin: 0; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: var(--side-hover); }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a span { font-size: .95rem; color: var(--side-ink); display: flex; align-items: center; gap: .6rem; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a span::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--side-dim); flex: none; opacity: .6; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] { background: var(--side-active); }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span,
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] span { color: var(--side-active-ink); font-weight: 600; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span::before,
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] span::before { background: var(--side-active-ink); opacity: 1; }
  [data-testid="stSidebar"] .side-foot { font-size: .75rem; color: var(--side-dim); line-height: 1.6; margin-top: .2rem; }
  [data-testid="stSidebar"] .side-foot .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--ok); margin-right: .4rem; }
  [data-testid="stSidebar"] .side-foot .dot.off { background: var(--warn); }
  [data-testid="stSidebar"] .stButton button { color: var(--side-muted); border-color: var(--side-line); background: transparent; }
  [data-testid="stSidebar"] .stButton button p { color: var(--side-muted); }
  [data-testid="stSidebar"] hr { border-color: var(--side-line); }
  [data-testid="stSidebar"] .stButton button:hover, [data-testid="stSidebar"] .stButton button:hover p { color: var(--side-ink); border-color: var(--side-dim); }

  /* ---------- 되돌리기 띠 ---------- */
  .st-key-undo_bar { background: var(--accent-bg); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
        border-radius: 6px; padding: .35rem .5rem .35rem .9rem; margin: 0 0 .8rem 0; }
  .st-key-undo_bar .undo-txt { font-size: .9rem; color: var(--ink); }
  .st-key-undo_bar [data-testid="stElementContainer"]:has(.undo-txt) { flex: 1; }
  [data-testid="stSidebar"] .stButton button[kind="tertiary"] { border: none; min-height: 0; padding: 0; margin-left: auto; display: block; }
  [data-testid="stSidebar"] .stButton button[kind="tertiary"] p { font-size: .8rem; text-decoration: underline; }

  /* ---------- 도움말 팝업 ---------- */
  [data-testid="stTooltipContent"] { font-size: .9rem; line-height: 1.55; max-width: 520px; }

  /* ---------- 접속 화면 (2026-11-04 시안 C "자물쇠 친구") ---------- */
  .login-gap { height: 18vh; }
  .stApp:has(.login-bg) [data-testid="stHeader"] { background: transparent; backdrop-filter: none; }
  .login-bg { position: fixed; inset: 0; z-index: 0; pointer-events: none;
        background: radial-gradient(circle at 1px 1px, #D9E0EE 1.2px, transparent 1.3px) 0 0 / 22px 22px,
                    linear-gradient(160deg, #EEF3FF, #F6F1FF 55%, #FFF4EE); }
  .st-key-login_card { position: relative; z-index: 1; max-width: 400px; margin: 0 auto; overflow: visible;
        background: rgba(255,255,255,.95); border: 1px solid #fff; border-radius: 28px;
        padding: 0 36px 26px 36px; box-shadow: 0 20px 50px rgba(60,70,120,.12); }
  .login-mascot { display: block; width: 150px; height: 150px; margin: -80px auto -2px auto;
        filter: drop-shadow(0 8px 12px rgba(80,100,160,.16)); }
  .login-mascot .shut, .login-mascot .peek, .login-mascot .sad { display: none; }
  .st-key-login_card:has(input[type="password"]:focus) .login-mascot .open,
  .st-key-login_card:has(input[type="password"]:not(:placeholder-shown)) .login-mascot .open { display: none; }
  .st-key-login_card:has(input[type="password"]:focus) .login-mascot .shut,
  .st-key-login_card:has(input[type="password"]:not(:placeholder-shown)) .login-mascot .shut { display: inline; }
  .st-key-login_card:has(input[type="text"]) .login-mascot .open,
  .st-key-login_card:has(input[type="text"]) .login-mascot .shut { display: none; }
  .st-key-login_card:has(input[type="text"]) .login-mascot .peek { display: inline; }
  .login-mascot.failed .smile { display: none; }
  .login-mascot.failed .sad { display: inline; }
  .login-mascot.failed .shut, .login-mascot.failed .peek { display: none !important; }
  .login-mascot.failed .open { display: inline !important; }
  .login-head { text-align: center; }
  .login-head .t { font-size: 1.4rem; font-weight: 700; color: var(--ink); letter-spacing: -.02em; line-height: 1.3; margin: 0 0 .35rem 0; }
  .login-head .d { font-size: .85rem; color: #7A8597; margin: 0 0 1.3rem 0; }
  .st-key-login_card [data-testid="stForm"] { border: none; padding: 0; }
  .st-key-login_card [data-testid="stTextInputRootElement"] { border-radius: 14px; min-height: 3.1rem; background: #F7F9FC;
        border: 1.5px solid #D9DFEA; transition: box-shadow .15s, border-color .15s; }
  .st-key-login_card [data-testid="stTextInputRootElement"]:focus-within { border-color: #7FA6E8; background: #fff; box-shadow: 0 0 0 4px #E3ECFB; }
  .st-key-login_card [data-testid="stTextInputRootElement"] > div, .st-key-login_card [data-testid="stTextInputRootElement"] input { background: transparent; }
  .st-key-login_card [data-testid="stTextInputRootElement"] input { font-size: 1rem; }
  .st-key-login_card [data-testid="stTextInputRootElement"] [data-testid="stTextInputIcon"],
  .st-key-login_card [data-testid="stTextInputRootElement"] span[data-testid="stIconMaterial"] { color: #8A95A8; }
  .st-key-login_card [data-testid="stFormSubmitButton"], .st-key-login_card [data-testid="stFormSubmitButton"] button { width: 100%; }
  .st-key-login_card [data-testid="stFormSubmitButton"] button { min-height: 3.1rem; border-radius: 14px; border: none;
        background: linear-gradient(135deg, #24395E, #132036); box-shadow: 0 8px 18px rgba(19,32,54,.25); transition: transform .12s, box-shadow .12s; }
  .st-key-login_card [data-testid="stFormSubmitButton"] button:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(19,32,54,.32); }
  .st-key-login_card [data-testid="stFormSubmitButton"] button p { font-size: 1rem; font-weight: 600; }
  .st-key-login_card [data-testid="InputInstructions"] { display: none; }
  .login-foot { text-align: center; margin-top: 1rem; }
  .login-foot span { display: inline-flex; align-items: center; gap: 5px; font-size: .8rem; color: #2E8B60;
        background: #E8F6EF; padding: .25rem .75rem; border-radius: 99px; }
  .login-logo { position: fixed; left: 40px; top: 30px; width: 170px; z-index: 1000001; pointer-events: none; }
  .login-bg .lb, .login-bg .ls { position: absolute; transform: translate(-50%, -50%); }
  .login-bg .lb { animation: login-float 6s ease-in-out infinite; filter: drop-shadow(0 6px 10px rgba(80,100,160,.08)); }
  .login-bg svg { width: 100%; height: 100%; display: block; }
  @keyframes login-float { 0%, 100% { transform: translate(-50%, -50%); } 50% { transform: translate(-50%, calc(-50% - 10px)); } }
  @media (prefers-reduced-motion: reduce) { .login-bg .lb { animation: none; } }
  @media (max-width: 760px) {
    .login-bg .desk { display: none; }
    .login-bg .lb { width: 64px !important; height: 64px !important; }
    .login-bg .lb:nth-child(1) { left: 14% !important; top: 12% !important; }
    .login-bg .lb:nth-child(2) { left: 86% !important; top: 12% !important; }
    .login-logo { left: 50%; transform: translateX(-50%); top: 22px; width: 120px; }
  }
  .login-foot svg { width: 13px; height: 13px; }
  .login-err { font-size: .85rem; color: var(--ng); background: var(--ng-bg); border-radius: 12px;
        padding: .5rem .8rem; margin: .1rem 0 .3rem 0; text-align: center; }
  /* 견적서 (2026-11-04) */
  .q-tile { background: var(--panel); border-radius: 14px; box-shadow: var(--card-shadow); padding: .8rem 1rem; margin-bottom: .6rem; }
  .q-tile b { display: block; font-size: 1.6rem; line-height: 1.2; }
  .q-tile span { font-size: .85rem; color: var(--muted); }
  .q-inline { display: inline-block; min-width: 9rem; margin-right: .6rem; }
  .q-sub { font-weight: 700; font-size: 1.05rem; margin: .1rem 0 .4rem 0; }
  .q-total { background: var(--panel); border-radius: 14px; box-shadow: var(--card-shadow); padding: .9rem 1.1rem; margin-bottom: .7rem; }
  .q-tr { display: flex; justify-content: space-between; font-size: .85rem; color: var(--muted); padding: .18rem 0; }
  .q-tr b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
  .q-big { display: flex; justify-content: space-between; align-items: baseline; border-top: 1px solid var(--line); margin-top: .5rem; padding-top: .6rem; }
  .q-big span { font-size: .85rem; color: var(--muted); }
  .q-big b { font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  /* ---------- 공통 모양 (2026-11-06): 카드 16px · 버튼/입력 10px · 칩 999px · 숫자 고정폭 ---------- */
  [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { font-feature-settings: "tnum"; letter-spacing: -.01em; }
  .stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-baseweb="input"], [data-baseweb="select"] > div,
  [data-baseweb="textarea"], [data-testid="stDateInput"] > div > div { border-radius: 10px !important; }
  [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) , [data-testid="stExpander"] details,
  [data-testid="stDataFrame"], [data-testid="stMetric"] { border-radius: 16px; }
  /* ---------- 색감 (2026-11-06): 라벤더→핑크 파스텔 + 그라데이션 포인트 ---------- */
  .stApp:not(:has(.login-bg)) [data-testid="stAppViewContainer"] {
        background: radial-gradient(1200px 500px at 85% -10%, #EDEBFF 0%, transparent 60%),
                    radial-gradient(900px 420px at 10% 0%, #FDEFF6 0%, transparent 55%), var(--bg); }
  [data-testid="stHeader"] { background: transparent; backdrop-filter: none; }
  [data-testid="stSidebar"] { background: linear-gradient(180deg, #F3F1FF 0%, #F8F4FF 55%, #FDF3F8 100%); border-right: 1px solid #E9E5FA; }
  [data-testid="stSidebar"] .nav-group { color: #8B7FD9; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a { border-radius: 10px; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a span::before { background: #B9B1F5; opacity: 1; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: rgba(255,255,255,.7); }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] { background: #FFFFFF; box-shadow: 0 2px 8px rgba(91,108,255,.14); }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span::before,
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] span::before { background: linear-gradient(135deg, #5B6CFF, #B36BFF); }
  [data-testid="stSidebar"] .brand { border-bottom-color: #E4DFFA; }
  .ph { border-bottom: 0; position: relative; }
  .ph::after { content: ""; position: absolute; left: 0; bottom: 0; width: 56px; height: 4px; border-radius: 99px;
        background: linear-gradient(90deg, #5B6CFF, #B36BFF, #FF8FB8); }
  .ph .eb { color: #8B7FD9; }
  [data-testid="stHeading"] h3, .sec-bar { border-bottom: 0; }
  [data-testid="stHeading"] h3::before, .sec-bar::before { content: ""; width: 4px; height: 1.05em; border-radius: 99px; flex: none;
        background: linear-gradient(180deg, #5B6CFF, #B36BFF); }
  .stButton button[kind="primary"], .stDownloadButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {
        background: linear-gradient(135deg, #5B6CFF 0%, #8B6CFF 100%) !important; border: 0 !important; box-shadow: 0 4px 12px rgba(91,108,255,.25); }
  .stApp:not(:has(.login-bg)) [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
        background: #FFFFFF; border-color: #ECEAF8 !important; box-shadow: 0 2px 10px rgba(91,108,255,.06); }
  [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] { background: #FBFAFF !important; }
  [data-testid="stDataFrame"] { box-shadow: 0 1px 6px rgba(91,108,255,.05); }
  /* 메뉴 아이콘: 묶음 색 둥근 타일 */
  [data-testid="stSidebar"] [data-testid="stPageLink"] a span::before { display: none; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a { padding: .3rem .5rem; gap: .65rem; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a [data-testid="stIconMaterial"] {
        width: 28px; height: 28px; border-radius: 9px; display: inline-flex; align-items: center; justify-content: center;
        font-size: 17px; color: var(--nc, #5B6CFF) !important; background: var(--nb, #E9EBFF); flex: none; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] [data-testid="stIconMaterial"],
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] [data-testid="stIconMaterial"] {
        color: #FFFFFF !important; background: var(--nc, #5B6CFF); box-shadow: 0 3px 8px color-mix(in srgb, var(--nc, #5B6CFF) 35%, transparent); }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span,
  [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] span { color: var(--side-ink); font-weight: 700; }
  [data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { margin-bottom: -0.95rem; }
  /* 로고와 시스템 이름 분리 · 묶음 구분 · 글자 진하게 */
  [data-testid="stSidebar"] .brand { border-bottom: 0; padding: 0 0 .4rem 0; }
  [data-testid="stSidebar"] .brand img { width: 128px; margin: .2rem 0 1.1rem .3rem; }
  [data-testid="stSidebar"] .brand-card { display: flex; align-items: center; gap: .6rem; padding: .65rem .75rem; border-radius: 14px;
        background: #FFFFFF; box-shadow: 0 2px 10px rgba(91,108,255,.10); border: 1px solid #ECE8FB; }
  [data-testid="stSidebar"] .brand-ic { width: 30px; height: 30px; border-radius: 10px; flex: none; display: inline-flex;
        align-items: center; justify-content: center; background: linear-gradient(135deg, #5B6CFF, #B36BFF); color: #fff; }
  [data-testid="stSidebar"] .brand-ic span { font-family: "Material Symbols Rounded"; font-size: 18px; line-height: 1; }
  [data-testid="stSidebar"] .brand-title { font-size: 1.02rem; font-weight: 800; color: #1E2433; margin: 0; }
  [data-testid="stSidebar"] .nav-group { font-size: .72rem; font-weight: 700; letter-spacing: .08em; color: #7D72C9;
        margin: 1.05rem 0 .45rem 0; padding: .85rem .5rem 0; border-top: 1px dashed #DDD6F6; }
  [data-testid="stSidebar"] .brand + div .nav-group, [data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.brand) + [data-testid="stElementContainer"] .nav-group { border-top: 0; padding-top: .3rem; }
  [data-testid="stSidebar"] [data-testid="stPageLink"] a span { color: #2B3245 !important; font-weight: 500; font-size: .95rem; }
</style>
""".replace("__VARS__", _VARS)


def apply_style():
    st.markdown(_CSS, unsafe_allow_html=True)


# 표 칸·숫자 칸을 처음 누를 때 Streamlit 화면은 편집기 조각(js 파일)을 그제야 내려받습니다.
# 앱이 다시 배포되는 1~2분 사이에 누르면 그 파일을 못 받아
# "Failed to fetch dynamically imported module …" 오류가 나고, 새로고침 전까지 그 표는 계속 깨져 있습니다.
# 그래서 화면을 열자마자 편집기 조각을 미리 받아 둡니다 (브라우저가 한 번 받은 조각은 다시 받지 않음).
_LAZY = ("data-grid-overlay-editor", "number-overlay-editor", "NumberInput")


@functools.lru_cache(maxsize=1)
def _lazy_chunks() -> tuple[str, ...]:
    import glob
    d = os.path.join(os.path.dirname(st.__file__), "static", "static", "js")
    return tuple(os.path.basename(f) for n in _LAZY for f in glob.glob(os.path.join(d, n + ".*.js")))


_PRELOAD_JS = """
<script>
(function () {
  const files = __FILES__;
  if (window.__edPre === files.join()) return;
  window.__edPre = files.join();
  const main = document.querySelector('script[src*="/static/js/index."]');
  if (main) {
    const base = new URL('.', main.src);
    files.forEach((f) => import(new URL(f, base).href).catch(() => { window.__edPre = ''; }));
  }
  // 그래도 못 받았으면 (미리 받기 전에 배포가 시작된 경우) 오류 아래에 새로고침 단추를 붙임
  if (window.__edWatch) return;
  window.__edWatch = new MutationObserver(() => {
    document.querySelectorAll('[data-testid="stException"], [data-testid="stAlertContainer"]').forEach((el) => {
      if (el.dataset.edFix || !/dynamically imported module/.test(el.textContent)) return;
      el.dataset.edFix = '1';
      const b = document.createElement('button');
      b.textContent = '앱이 방금 새로 바뀌었어요. 눌러서 새로고침';
      b.style.cssText = 'margin-top:.6rem;padding:.45rem .9rem;border:0;border-radius:8px;'
        + 'background:#5B6CFF;color:#fff;font-weight:600;cursor:pointer';
      b.onclick = () => location.reload();
      el.appendChild(b);
    });
  });
  window.__edWatch.observe(document.body, {childList: true, subtree: true});
})();
</script>
"""


def preload_editors():
    """접속 화면에서도 부름: 메뉴 칸이 처음부터 있어야 접속 뒤 메뉴가 접힌 채로 시작하지 않음 (접속 화면에선 CSS로 숨김)."""
    _preload_editors()


def _preload_editors():
    files = _lazy_chunks()
    if not files:
        return
    with st.sidebar:
        st.html(_PRELOAD_JS.replace("__FILES__", repr(list(files)).replace("'", '"')), unsafe_allow_javascript=True)


def page_header(title: str, eyebrow: str = "", chip: str = "", desc: str = "", accent: str | None = None):
    """쪽 맨 위 제목 줄: 작은 머리글 + 제목 + 표시, 오른쪽에 한 줄 설명."""
    e = html.escape
    ac = accent or T["accent-hi"]
    st.markdown(
        f'<div class="ph" style="--ac:{ac}"><div>{f"<div class=eb>{e(eyebrow)}</div>" if eyebrow else ""}'
        f'<div class="t">{e(title)}{f"<span class=chip>{e(chip)}</span>" if chip else ""}</div></div>'
        f'{f"<div class=desc>{e(desc)}</div>" if desc else ""}</div>', unsafe_allow_html=True)


def section_bar(title: str, no: int | None = None, sub: str = "", first: bool = False):
    """영역 제목 막대 (번호 + 제목 + 오른쪽 보조 설명)."""
    chip = f'<span class="no">{no}</span>' if no else ""
    st.markdown(f'<div class="sec-bar{" first" if first else ""}">{chip}<span>{html.escape(title)}</span>'
                f'<span class="sub">{html.escape(sub)}</span></div>', unsafe_allow_html=True)


def note(text_html: str):
    """회색 안내 띠. text_html 안의 값은 호출하는 쪽에서 escape한다."""
    st.markdown(f'<div class="note">{text_html}</div>', unsafe_allow_html=True)


def empty_state(title: str, body: str = "", icon: str = "○"):
    """비어 있는 화면 안내 상자."""
    e = html.escape
    st.markdown(f'<div class="empty"><div class="ic">{e(icon)}</div><div class="h">{e(title)}</div>'
                f'{f"<div class=b>{e(body)}</div>" if body else ""}</div>', unsafe_allow_html=True)


def goal_bar(ratio: float, left_html: str, right_html: str, color: str | None = None):
    """목표 대비 진행 막대."""
    pct = max(0.0, min(ratio, 1.0)) * 100
    c = color or (T["ok"] if ratio >= 1 else T["accent-hi"])
    st.markdown(f'<div class="goal"><div class="row"><span>{left_html}</span><span>{right_html}</span></div>'
                f'<div class="bar" style="--c:{c}"><i style="width:{pct:.1f}%"></i></div></div>', unsafe_allow_html=True)


def sidebar_brand():
    """왼쪽 메뉴 맨 위: 로고(어두운 바탕용) + 시스템 이름."""
    uri = _data_uri(LOGO_PATH)
    logo = f'<img src="{uri}" alt="로고">' if uri else ""
    st.markdown(f'<div class="brand">{logo}<div class="brand-card"><span class="brand-ic">'
                '<span class="material-symbols-rounded">precision_manufacturing</span></span>'
                f'<p class="brand-title">{html.escape(SYSTEM_TITLE)}</p></div></div>', unsafe_allow_html=True)


def nav_group(name: str):
    st.markdown(f'<div class="nav-group">{html.escape(name)}</div>', unsafe_allow_html=True)


_MASCOT = """<svg class="login-mascot{cls}" viewBox="0 0 140 140" aria-hidden="true">
<defs><linearGradient id="lm-body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#A9C8FF"/><stop offset="1" stop-color="#C9B8FF"/></linearGradient>
<linearGradient id="lm-shackle" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8FB0F2"/><stop offset="1" stop-color="#A996EE"/></linearGradient></defs>
<path d="M50 64V50a20 20 0 0 1 40 0v14" stroke="url(#lm-shackle)" stroke-width="12" fill="none" stroke-linecap="round"/>
<path d="M47 52a23 23 0 0 1 12-17" stroke="#fff" stroke-opacity=".55" stroke-width="3" fill="none" stroke-linecap="round"/>
<rect x="28" y="58" width="84" height="66" rx="32" fill="url(#lm-body)"/>
<ellipse cx="50" cy="68" rx="13" ry="5" fill="#fff" opacity=".5" transform="rotate(-18 50 68)"/>
<g class="open"><ellipse cx="56" cy="86" rx="6" ry="7" fill="#1E2433"/><ellipse cx="84" cy="86" rx="6" ry="7" fill="#1E2433"/>
<circle cx="58.3" cy="83.3" r="2.4" fill="#fff"/><circle cx="86.3" cy="83.3" r="2.4" fill="#fff"/>
<circle cx="54.5" cy="89" r="1.1" fill="#fff"/><circle cx="82.5" cy="89" r="1.1" fill="#fff"/></g>
<g class="shut" stroke="#1E2433" stroke-width="3.2" fill="none" stroke-linecap="round"><path d="M49 86q7 6 14 0"/><path d="M77 86q7 6 14 0"/></g>
<g class="peek"><path d="M49 86q7 6 14 0" stroke="#1E2433" stroke-width="3.2" fill="none" stroke-linecap="round"/>
<ellipse cx="84" cy="86" rx="6" ry="7" fill="#1E2433"/><circle cx="86.3" cy="83.3" r="2.4" fill="#fff"/></g>
<ellipse cx="46" cy="98" rx="7.5" ry="4.5" fill="#FF9FB5" opacity=".55"/><ellipse cx="94" cy="98" rx="7.5" ry="4.5" fill="#FF9FB5" opacity=".55"/>
<path class="smile" d="M63 96q3.5 4 7 0q3.5 4 7 0" stroke="#1E2433" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<g class="sad" stroke="#1E2433" stroke-width="2.6" fill="none" stroke-linecap="round"><path d="M64 100q6 -5 12 0"/><path d="M49 77l8 -3"/><path d="M91 77l-8 -3"/></g>
<path d="M116 33Q116 40 123 40Q116 40 116 47Q116 40 109 40Q116 40 116 33z" fill="#FFD3C2"/><path d="M24 51Q24 56 29 56Q24 56 24 61Q24 56 19 56Q24 56 24 51z" fill="#B9A6FF"/><path d="M120 100Q120 104 124 104Q120 104 120 108Q120 104 116 104Q120 104 120 100z" fill="#C9B8FF"/></svg>"""

_SHIELD = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round"><path d="M12 3l7 3v5.5c0 4.5-3 8-7 9.5-4-1.5-7-5-7-9.5V6z"/><path d="M9 12l2 2 4-4"/></svg>')



def _face(x, y, s=1.0, c="#1E2433"):
    return (f'<g transform="translate({x} {y}) scale({s})"><circle cx="-7" cy="0" r="3" fill="{c}"/><circle cx="7" cy="0" r="3" fill="{c}"/>'
            f'<circle cx="-6" cy="-1" r="1" fill="#fff"/><circle cx="8" cy="-1" r="1" fill="#fff"/>'
            f'<ellipse cx="-12" cy="5" rx="3.5" ry="2.2" fill="#FF9FB5" opacity=".6"/><ellipse cx="12" cy="5" rx="3.5" ry="2.2" fill="#FF9FB5" opacity=".6"/>'
            f'<path d="M-3 4q1.5 2 3 0q1.5 2 3 0" stroke="{c}" stroke-width="1.6" fill="none" stroke-linecap="round"/></g>')


def _spark(color):
    return (f'<svg viewBox="-10 -10 20 20"><path d="M0 -10Q0 0 10 0Q0 0 0 10Q0 0 -10 0Q0 0 0 -10z" fill="{color}"/></svg>')


_ICONS = {
    "battery": '<rect x="-14" y="-20" width="28" height="42" rx="8" fill="#9FDDBF"/><rect x="-6" y="-25" width="12" height="6" rx="2" fill="#7CC7A8"/>' + _face(0, 2, .8),
    "gear": '<g fill="#FFB49A">' + "".join(f'<rect x="-5" y="-24" width="10" height="12" rx="3" transform="rotate({a})"/>' for a in range(0, 360, 45))
            + '<circle r="17"/></g>' + _face(0, 0, .75),
    "flask": '<path d="M-6 -24h12v14l14 24a6 6 0 0 1-5 9h-30a6 6 0 0 1-5-9l14-24z" fill="#FFB3C7"/><rect x="-9" y="-27" width="18" height="5" rx="2.5" fill="#F58FAA"/>' + _face(0, 8, .7),
    "bulb": '<circle cy="-4" r="17" fill="#FFE08A"/><rect x="-8" y="11" width="16" height="10" rx="3" fill="#E9C46A"/>' + _face(0, -4, .75),
    "chart": '<rect x="-20" y="-20" width="40" height="40" rx="10" fill="#C9B8FF"/><rect x="-11" y="0" width="6" height="12" rx="2" fill="#fff"/>'
             '<rect x="-3" y="-8" width="6" height="20" rx="2" fill="#fff"/><rect x="5" y="-14" width="6" height="26" rx="2" fill="#fff"/>',
    "dot": '<circle r="16" fill="#A9C8FF"/>' + _face(0, 0, .6),
}
# (아이콘, 바탕색, 왼쪽 %, 위 %, 지름 px, 기울기, 휴대폰에서도 보임)
_BUBBLES = [("battery", "#E6F7EF", 19.5, 31, 104, -8, True), ("gear", "#FFEDE6", 80.5, 29, 96, 10, True),
            ("flask", "#FFE9EF", 15.5, 70, 92, 6, False), ("bulb", "#FFF5D6", 84.5, 70, 108, -6, False),
            ("chart", "#EFEAFF", 31, 86, 68, 8, False), ("dot", "#E6F0FF", 70, 11, 60, 0, False)]
_SPARKS = [("#FFD3C2", 29.5, 21, 16), ("#C9B8FF", 72.5, 86, 18), ("#A9C8FF", 9.5, 50, 12), ("#FFB3C7", 92, 50, 14)]


def _login_deco() -> str:
    out = []
    for i, (icon, bg, x, y, d, rot, phone) in enumerate(_BUBBLES):
        out.append(f'<div class="lb{"" if phone else " desk"}" style="left:{x}%;top:{y}%;width:{d}px;height:{d}px;--r:{rot}deg;'
                   f'animation-delay:-{i * 1.3:.1f}s"><svg viewBox="-50 -50 100 100"><circle r="50" fill="{bg}"/>'
                   f'<g transform="rotate({rot})">{_ICONS[icon]}</g></svg></div>')
    for c, x, y, d in _SPARKS:
        out.append(f'<div class="ls desk" style="left:{x}%;top:{y}%;width:{d}px;height:{d}px">{_spark(c)}</div>')
    return "".join(out)


def login_bg():
    """접속 화면 배경 (카드 밖에 그려야 카드 위를 덮지 않음)."""
    uri = _data_uri(os.path.join(_DIR, "assets", "logo_light.png"))
    logo = f'<img class="login-logo" src="{uri}" alt="로고">' if uri else ""
    st.markdown(f'<div class="login-bg">{_login_deco()}</div>{logo}', unsafe_allow_html=True)


def login_head(failed: bool = False):
    """접속 화면 위쪽: 자물쇠 친구(비밀번호를 치는 동안 눈을 감음) + 제목."""
    st.markdown(_MASCOT.replace("{cls}", " failed" if failed else "").replace("\n", "")
                + f'<div class="login-head"><div class="t">{html.escape(SYSTEM_TITLE)}</div>'
                '<div class="d">팀 비밀번호로 들어와 주세요</div></div>', unsafe_allow_html=True)


def login_foot():
    """접속 화면 아래쪽: 보안 표시 (로고는 화면 왼쪽 위에 크게)."""
    st.markdown(f'<div class="login-foot"><span>{_SHIELD}보안 연결됨</span></div>', unsafe_allow_html=True)


# 그래프 오른쪽 위 버튼: 그림으로 저장(보고서 붙여넣기용)만 남김
CHART_CONFIG = {"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2},
                "modeBarButtonsToRemove": ["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
                                           "autoScale2d", "resetScale2d", "toggleSpikelines",
                                           "hoverClosestCartesian", "hoverCompareCartesian"]}


def nice_step(top: float) -> float:
    """보조축 눈금 간격: 4~6칸이 되도록 2·5·10·20·25·50 중에서."""
    for step in (2, 5, 10, 20, 25, 50):
        if top / step <= 6:
            return step
    return 100


def chart_layout(fig, height: int, legend: bool = True):
    """plotly 그래프를 어두운 화면에 맞게."""
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36 if legend else 12, b=8), font=CHART_FONT,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=T["muted"])),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=T["panel2"], bordercolor=T["line2"], font=dict(color=T["ink"], family=CHART_FONT["family"])),
        showlegend=legend,
    )
    fig.update_xaxes(gridcolor=CHART_GRID, zerolinecolor=CHART_GRID, linecolor=T["line"], tickfont=dict(color=T["muted"]),
                     title_font=dict(color=T["muted"], size=12))
    fig.update_yaxes(gridcolor=CHART_GRID, zerolinecolor=CHART_GRID, linecolor=T["line"], tickfont=dict(color=T["muted"]),
                     title_font=dict(color=T["muted"], size=12))
    return fig


# 2026-11-06: 빈 칸에 회색 "None" 글자가 보이지 않게, 모든 표의 빈 칸 표시를 빈칸으로
def _blank_none(fn):
    import functools

    @functools.wraps(fn)
    def wrap(*a, **k):
        k.setdefault("placeholder", "")
        return fn(*a, **k)
    return wrap


if not getattr(st.data_editor, "_blank_none", False):
    for _n in ("data_editor", "dataframe"):
        _f = _blank_none(getattr(st, _n))
        _f._blank_none = True
        setattr(st, _n, _f)
