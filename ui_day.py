"""밝은 테마 시안 (2026-11-22). EQUIP_THEME=day / day-navy 일 때 slate(다크) 규칙 위에 덮어씀.

배치·크기 규칙은 slate 그대로 두고 색만 바꿈. 화면 파일(views/*)이 자기 CSS 에 직접 쓴 어두운 색도
여기서 .stApp 을 앞에 붙여(더 강한 규칙) 밝은 색으로 바꿈.
KPI 색 01 #3B82F6 · 02 #10B981 · 03 #F59E0B · 04 #8B5CF6 은 그대로.
"""

_LINE = "#CBD5E1"      # 표 선 (다크의 밝은 선 #64748B 자리)
_LINE_SOFT = "#E2E8F0"  # 카드 안 옅은 선
_INK = "#0F172A"
_MUTED = "#475569"
_DIM = "#94A3B8"

DAY_CSS = """<style>
  /* ---------- 바탕 · 머리 ---------- */
  .stApp [data-testid="stAppViewContainer"], .stApp:not(:has(.login-bg, .login-preview-bg)) [data-testid="stAppViewContainer"] { background: #F4F6FA !important; }
  .stApp:not(:has(.login-bg, .login-preview-bg)) [data-testid="stHeader"] { background: rgba(244,246,250,.88) !important; }
  .stApp .ph { border-bottom: 1px solid #E2E8F0 !important; }
  .stApp .ph .t, .stApp .dh .tt, .stApp .ph2 .t2 { color: #0F172A !important; }
  .stApp .ph2 { border-bottom-color: #E2E8F0 !important; }

  /* ---------- 입력칸 · 표 · 버튼 ---------- */
  .stApp [data-baseweb="input"], .stApp [data-baseweb="select"] > div, .stApp [data-baseweb="textarea"] { background: #FFFFFF !important; border-color: #CBD5E1 !important; }
  .stApp [data-testid="stDataFrame"] { background: #FFFFFF; border-color: #CBD5E1; }
  .stApp [data-testid="stAlert"] > div { background: #FFFBEB !important; color: #78350F; }
  .stApp [data-testid="stAlert"] p { color: #78350F !important; }
  .stApp .stButton button[kind="primary"], .stApp .stDownloadButton button[kind="primary"], .stApp .stFormSubmitButton button[kind="primary"] { background: #4F46E5 !important; border-color: #4F46E5 !important; }
  .stApp .stButton button[kind="primary"]:hover { background: #4338CA !important; }
  .stApp .stButton button[kind="secondary"], .stApp .stDownloadButton button[kind="secondary"] { background: #FFFFFF; border-color: #CBD5E1; }
  .stApp .stButton button[kind="primary"]:disabled { background: #E2E8F0 !important; border-color: #CBD5E1 !important; }
  .stApp .stButton button[kind="primary"]:disabled p { color: #94A3B8 !important; }
  .stApp .empty { background: #FFFFFF !important; border-left-color: #4F46E5 !important; box-shadow: 0 1px 2px rgba(15,23,42,.05); }
  .stApp .empty .h { color: #0F172A !important; } .stApp .empty .b { color: #475569 !important; } .stApp .empty .ic { color: #4F46E5 !important; }
  .stApp:not(:has(.login-bg, .login-preview-bg)) [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
        background: #FFFFFF !important; border-color: #E2E8F0 !important; }
  .stApp [data-testid="stMetric"] { background: #FFFFFF; border-color: #E2E8F0; box-shadow: 0 1px 2px rgba(15,23,42,.05); }
  @media (max-width: 640px) {
    .stApp:not(:has(.login-bg, .login-preview-bg)) [data-testid="stHeader"] { background: rgba(244,246,250,.96) !important; } }

  /* ---------- 장비 KPI 현황 ---------- */
  .stApp [class*="st-key-dsec_"] { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; box-shadow: 0 1px 3px rgba(15,23,42,.06); }
  .stApp .st-key-dsec_util { border-top: 4px solid #3B82F6 !important; } .stApp .st-key-dsec_fee { border-top: 4px solid #10B981 !important; }
  .stApp .dtop .k { background: #FFFFFF; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(15,23,42,.06); }
  .stApp .dtop .k.c1 { border-top: 4px solid #3B82F6; } .stApp .dtop .k.c2 { border-top: 4px solid #10B981; }
  .stApp .dtop .k.c3 { border-top: 4px solid #F59E0B; } .stApp .dtop .k.c4 { border-top: 4px solid #8B5CF6; }
  .stApp .dtop .tt { color: #0F172A; border-bottom-color: #EEF2F7; }
  .stApp .dtop .sub { color: #475569; }
  .stApp .dtop .mm b { color: #1E293B; } .stApp .dtop .mm b.z { color: #CBD5E1; } .stApp .dtop .mm span { color: #94A3B8; }
  .stApp .dtop table, .stApp .dtop td { color: #1E293B; }
  .stApp .dtop th { color: #64748B !important; border-bottom-color: #CBD5E1 !important; }
  .stApp .dtop td { border-bottom-color: #EEF2F7 !important; }
  .stApp .dtop tr.sum td { background: #F5F3FF !important; color: #6D28D9; }
  .stApp .dper, .stApp .dh .per { color: #334155; border-color: #CBD5E1; background: #FFFFFF !important; }
  .stApp .dct { color: #0F172A !important; }
  .stApp .dnone, .stApp .dsub { color: #64748B; }
  .stApp .drep, .stApp .dcnt { color: #1E293B; }
  .stApp .drep th, .stApp .dcnt th { color: #64748B !important; border-bottom-color: #CBD5E1 !important; }
  .stApp .drep td, .stApp .dcnt td { border-bottom-color: #EEF2F7 !important; }
  .stApp .drep td.g { color: #475569; }
  .stApp .drep td.na, .stApp .drep td.z { color: #CBD5E1 !important; }
  .stApp .drep td.hit, .stApp .drep tr.rate td.hit { color: #059669; }
  .stApp .drep tr.rate td { color: #0F172A; }
  .stApp .drep tr.sum td { background: #EFF6FF !important; color: #1E3A8A; }
  .stApp .drep.fee tr.sum td { background: #ECFDF5 !important; color: #064E3B; }
  .stApp .drep tr.goal td { color: #047857; background: #F0FDF8 !important; }
  .stApp .drep:not(.fee) tr.goal td { color: #1D4ED8; background: #F5F9FF !important; }
  .stApp .drep .gl { color: #B45309; }
  .stApp .dcnt tr.sum td { background: #FFF7ED !important; color: #B45309; }
  .stApp .dst { background: #F8FAFC !important; border-color: #E2E8F0 !important; }
  .stApp .dst .sv, .stApp .dst.big .sv { color: #0F172A !important; }

  /* ---------- 장비 가동 현황 (충방전기 표 포함) ---------- */
  .stApp .st-key-es_cat [data-testid="stButtonGroup"] button, .stApp .st-key-cb_center [data-testid="stButtonGroup"] button {
        background: #FFFFFF !important; box-shadow: 0 0 0 1px #E2E8F0, 0 1px 2px rgba(15,23,42,.05); }
  .stApp .st-key-es_cat [data-testid="stButtonGroup"] button[aria-checked="true"] { background: #4F46E5 !important; box-shadow: none; }
  .stApp .st-key-cb_center [data-testid="stButtonGroup"] button[aria-checked="true"] { background: #1E293B !important; box-shadow: none; }
  .stApp .cb-k, .stApp .cb-box { background: #FFFFFF; box-shadow: 0 0 0 1px #E2E8F0, 0 1px 3px rgba(15,23,42,.05); }
  .stApp .cb-k:nth-child(1) span { color: #4F46E5 !important; } .stApp .cb-k:nth-child(2) span { color: #E11D48 !important; }
  .stApp .cb-k:nth-child(3) span { color: #059669 !important; }
  .stApp .cb-t th, .stApp .cb-t td.m, .stApp .cb-dash, .stApp .cb-mh span, .stApp .cb-t tr.chx td.n { color: #64748B; }
  .stApp .cb-t th, .stApp .cb-t td { border-bottom-color: #E2E8F0; }
  .stApp .cb-t tr.grp td { border-top-color: #E2E8F0; }
  .stApp .cb-mh span { border-left-color: #E2E8F0; } .stApp .cb-g { background: #E2E8F0; }
  .stApp .cb-t .s5, .stApp .cb-t td.s4[colspan], .stApp .es-t .ec { box-shadow: inset -1px 0 0 #CBD5E1; }
  .stApp .es-t td.ea.sub { color: #475569; } .stApp .es-t td.ea .tw { color: #94A3B8; }
  .stApp .es-t tr.sec td { background: linear-gradient(rgba(79,70,229,.05), rgba(79,70,229,.05)), #FFFFFF; }
  .stApp .es-t tr.sec td.ea span, .stApp .es-t tr.idl td { color: #64748B; }
  .stApp .es-t td.ea .kn { color: #475569; background: #EEF2F7; }
  .stApp .es-t .cb-tl { background-image: repeating-linear-gradient(90deg, rgba(100,116,139,.07) 0 16px, transparent 16px 56px); }
  .stApp .es-hol { background: rgba(100,116,139,.07); }
  .stApp .es-dh span { color: #94A3B8; }
  .stApp .cb-bar .off { background: repeating-linear-gradient(135deg, rgba(255,255,255,.85) 0 3px, rgba(255,255,255,.45) 3px 6px); }
  .stApp .cb-foot i.wk { background: repeating-linear-gradient(135deg, #CBD5E1 0 3px, #FFFFFF 3px 6px); }
  .stApp .cb-bar.cb-soon { background: #FFFBEB; border-color: #F59E0B; color: #B45309; }
  @media (max-width: 640px) { .stApp .es-t .ea, .stApp .cb-t .s0 { box-shadow: inset -1px 0 0 #CBD5E1; } }

  /* ---------- 접속 화면 ---------- */
  .stApp:has(.login-bg, .login-preview-bg) [data-testid="stAppViewContainer"] { background: #EEF2F7 !important; }
  .stApp .st-key-login_card { background: rgba(255,255,255,.94) !important; border: 1px solid #E2E8F0 !important;
        box-shadow: 0 24px 60px rgba(15,23,42,.14), 0 2px 6px rgba(15,23,42,.05) !important; }
  .stApp .st-key-login_card [data-testid="stTextInputRootElement"], .stApp .st-key-login_card [data-testid="stTextInputRootElement"]:focus-within { background: #FFFFFF !important; border-color: #CBD5E1; }
  .stApp .st-key-login_card input { color: #0F172A !important; }
  .stApp .login-head .t { color: #0F172A !important; }
  .stApp .login-head .s, .stApp .login-head p, .stApp .login-head .d { color: #64748B !important; }
  .stApp .login-foot span { background: #ECFDF5 !important; color: #047857 !important; }
</style>"""

# 시안 1 '전부 밝게': 왼쪽 메뉴도 흰색 (시안 2 는 메뉴를 지금 남색 그대로 둠)
DAY_SIDE_CSS = """<style>
  .stApp [data-testid="stSidebar"] { background: #FFFFFF !important; border-right: 1px solid #E2E8F0 !important; }
  .stApp [data-testid="stSidebar"] .brand { border-bottom-color: #EEF2F7 !important; }
  .stApp [data-testid="stSidebar"] .cbtp-header-equip, .stApp [data-testid="stSidebar"] .cbtp-foot-logo { background: #FFFFFF !important; }
  .stApp [data-testid="stSidebar"] .cbtp-header-equip { border-bottom-color: #EEF2F7 !important; }
  .stApp [data-testid="stSidebar"] .cbtp-foot-logo { border-top-color: #EEF2F7 !important; }
  .stApp [data-testid="stSidebar"] .cbtp-dept-label { color: #64748B !important; }
  .stApp [data-testid="stSidebar"] .cbtp-sys-title { color: #0F172A !important; }
  .stApp [data-testid="stSidebar"] .nav-group { color: #94A3B8 !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a span { color: #334155 !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: #F1F5F9 !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover span { color: #0F172A !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] { background: #EEF2FF !important; box-shadow: none !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] span,
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"] span { color: #4338CA !important; font-weight: 700 !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a::before { background: #CBD5E1 !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"]::before,
  .stApp [data-testid="stSidebar"] [data-testid="stPageLink"] a[data-active="true"]::before { background: #4F46E5 !important; box-shadow: 0 0 0 3px rgba(79,70,229,.18) !important; }
  .stApp [data-testid="stSidebar"] [data-testid="stIconMaterial"] { color: #64748B !important; }
</style>"""
