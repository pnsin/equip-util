"""공통 화면 스타일 — 기본 테마 "navy": 남색 메뉴 + 밝은 본문 (2026-11-02 사용자 선택, Power BI형).

앞으로 추가하는 화면도 이 규칙을 기본으로 한다.
- 색은 아래 TOKENS만 쓴다. 화면 코드에 색 값을 직접 쓰지 말고 CSS 변수 var(--이름)이나 이 파일의 상수를 쓴다.
- 본문은 밝게, 색은 '뜻'이 있을 때만 (목표 달성·미달, 경고).
- 글꼴은 IBM Plex Sans KR, 숫자는 같은 폭(tabular) — .streamlit/config.toml 테마와 같은 값.
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

SYSTEM_TITLE = w("장비 가동률 관리 시스템")
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
        "accent": "#2563C9", "accent-hi": "#2563C9", "accent-bg": "#E7EEFA",
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
}
THEME_NAME = os.environ.get("EQUIP_THEME", "navy")
TOKENS = {k: v for k, v in THEMES.get(THEME_NAME, THEMES["dark"]).items() if k not in ("logo", "base")}
T = TOKENS

# 그래프 색 (plotly)
CHART_FONT = dict(family="IBM Plex Sans KR, Noto Sans KR, Malgun Gothic, sans-serif", color=T["ink"], size=12)
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
  __VARS__
  .block-container { padding-top: 3.6rem; padding-bottom: 4rem; max-width: 1400px; }
  [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { font-family: "IBM Plex Sans KR", "Noto Sans KR", "Malgun Gothic", sans-serif; }
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

  /* ---------- 접속 화면 ---------- */
  .st-key-login_card { position: relative; z-index: 1; background: var(--panel); border: 1px solid var(--line); border-top: 3px solid var(--accent);
        border-radius: 8px; padding: 2rem 2rem 1.4rem 2rem; box-shadow: var(--shadow); }
  .login-head img { width: 150px; display: block; margin: 0 0 1.4rem 0; }
  .login-head .t { font-size: 1.6rem; font-weight: 700; color: var(--ink); letter-spacing: -.02em; margin: .25rem 0 1.4rem 0; line-height: 1.25; }
  .login-head .d { font-size: .85rem; color: var(--muted); margin: 0 0 1.2rem 0; line-height: 1.6; word-break: keep-all; }
  .st-key-login_card [data-testid="stForm"] { border: none; padding: 0; }
  .st-key-login_card [data-testid="stFormSubmitButton"], .st-key-login_card [data-testid="stFormSubmitButton"] button { width: 100%; }
  .st-key-login_card [data-testid="stFormSubmitButton"] button { min-height: 2.7rem; }
  .st-key-login_card [data-testid="InputInstructions"] { display: none; }
  .login-foot { font-size: .75rem; color: var(--dim); text-align: center; margin-top: 1rem; border-top: 1px solid var(--line); padding-top: .9rem; }
  .login-bg { position: fixed; inset: 0; z-index: 0; pointer-events: none;
        background: radial-gradient(900px 480px at 50% -10%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 70%),
                    linear-gradient(color-mix(in srgb, var(--muted) 5%, transparent) 1px, transparent 1px) 0 0 / 44px 44px,
                    linear-gradient(90deg, color-mix(in srgb, var(--muted) 5%, transparent) 1px, transparent 1px) 0 0 / 44px 44px; }
  .login-err { font-size: .85rem; color: var(--ng); background: var(--ng-bg); border: 1px solid color-mix(in srgb, var(--ng) 35%, transparent);
        border-radius: 4px; padding: .45rem .7rem; margin: .2rem 0 .4rem 0; }
</style>
""".replace("__VARS__", _VARS)


def apply_style():
    st.markdown(_CSS, unsafe_allow_html=True)


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
    st.markdown(f'<div class="brand">{logo}<p class="brand-title">{html.escape(SYSTEM_TITLE)}</p>'
                '</div>', unsafe_allow_html=True)


def nav_group(name: str):
    st.markdown(f'<div class="nav-group">{html.escape(name)}</div>', unsafe_allow_html=True)


def login_head():
    base = THEMES.get(THEME_NAME, THEMES["dark"])["base"]
    uri = _data_uri(os.path.join(_DIR, "assets", "logo_dark.png" if base == "dark" else "logo_light.png"))
    logo = f'<img src="{uri}" alt="로고">' if uri else ""
    st.markdown('<div class="login-bg"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="login-head">{logo}'
                f'<div class="t">{html.escape(SYSTEM_TITLE)}</div></div>', unsafe_allow_html=True)


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
