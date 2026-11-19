import datetime as dt

import pandas as pd
import streamlit as st

from core import db, itube, report
from ui_style import page_header
from core.terms import w

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render() -> None:
    page_header("설정", "관리")
    msg = st.session_state.pop("settings_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    cfg = db.get_settings()

    st.subheader("기본 정보")
    with st.form("basic"):
        c1, c2 = st.columns(2)
        dept = c1.text_input("부서명", value=cfg.get("dept_default", ""))
        team = c2.text_input("팀명", value=cfg.get("team_name") or _team_from(cfg))
        c1, c2 = st.columns(2)
        annual = c1.number_input("연간 기준 가용시간 (h)", min_value=1, step=100, value=int(cfg.get("annual_hours") or 2000),
                                 help="장비별로 다르면 '기준 정보 › 장비'에서 장비마다 따로 지정할 수 있습니다.")
        st.markdown("**대시보드 보기**")
        c1, c2 = st.columns(2)
        kinds = ["주", "월", "분기", "반기", "연"]
        dkind = c1.selectbox("처음 열 때 기간 단위", kinds, index=kinds.index(cfg.get("default_period", "월"))
                             if cfg.get("default_period") in kinds else 1)
        top_n = c2.number_input("장비별 그래프 최대 대수", min_value=5, max_value=100, step=5,
                                value=int(cfg.get("chart_top") or 25))
        if st.form_submit_button("설정 저장", type="primary", icon=":material/save:"):
            dept, team = dept.strip(), team.strip()
            db.save_settings(org_name=" ".join(x for x in (dept, team) if x), org_suffix="",
                             dept_default=dept, team_name=team, annual_hours=annual,
                             alloc_mode="spread", default_period=dkind, chart_top=int(top_n))
            st.session_state.settings_saved = "설정을 저장했습니다."
            st.rerun()
    _kpi(cfg)


FEE_ROW = "수수료 연 목표 (천 원)"
TOTAL_ROW = w("전체 가동률 목표 (%)")


def _kpi(cfg: dict) -> None:
    """2026-11-19: 주간업무보고 KPI 목표. 해마다 바뀌어서 연도별로 저장 (설정 키 'kpi' = {연도: {...}})."""
    st.subheader("KPI 목표")
    this = dt.date.today().year
    saved = {int(y) for y in (cfg.get("kpi") or {}) if str(y).isdigit()}
    years = sorted(saved | {this - 1, this, this + 1}, reverse=True)
    c1, _ = st.columns([1, 3])
    year = c1.selectbox("연도", years, index=years.index(this), key="kpi_year", format_func=lambda y: f"{y}년")
    k = report.kpi(cfg, year)
    rows = [{"구분": FEE_ROW, "목표": k["fee"] / 1000}, {"구분": TOTAL_ROW, "목표": k["util_total"]}]
    rows += [{"구분": c, "목표": k["util"].get(c)} for c in report.CATS if c != report.OTHER]
    with st.form("kpi_form"):
        if not k["year_set"]:
            st.caption(f"{year}년 목표가 아직 없어서 가장 가까운 해의 값을 보여 드려요. 고쳐서 저장하면 {year}년 목표가 돼요.")
        ed = st.data_editor(pd.DataFrame(rows), key=f"kpi_tbl_{year}", hide_index=True, width="stretch",
                            disabled=["구분"], height=38 + 35 * len(rows),
                            column_config={"구분": st.column_config.TextColumn(w("구분 (분류별은 가동률 %)")),
                                           "목표": st.column_config.NumberColumn(format="localized", min_value=0)})
        st.caption("수수료 월·주 목표는 연 목표를 12달 · 52주로 나눠요.")
        if st.form_submit_button("KPI 저장", type="primary", icon=":material/save:"):
            v = dict(zip(ed["구분"], ed["목표"]))
            num = lambda x: None if x is None or pd.isna(x) else float(x)
            rec = {"fee": int(round((num(v.get(FEE_ROW)) or 0) * 1000)), "util_total": num(v.get(TOTAL_ROW)) or 0.0,
                   "util": {c: num(v.get(c)) for c in report.CATS if c != report.OTHER and num(v.get(c)) is not None}}
            table = {str(y): x for y, x in (cfg.get("kpi") or {}).items()}
            table[str(year)] = rec
            db.save_settings(kpi=table)
            st.session_state.settings_saved = f"{year}년 KPI 목표를 저장했습니다."
            st.rerun()


def _team_from(cfg: dict) -> str:
    """예전 '기관·팀명'에서 부서명을 뺀 나머지를 팀명으로."""
    org, dept = cfg.get("org_name", ""), cfg.get("dept_default", "")
    return org[len(dept):].strip() if dept and org.startswith(dept) else org


def render_data() -> None:
    page_header("가져오기 · 백업", "관리")
    msg = st.session_state.pop("settings_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    st.subheader("기존 엑셀 실적 가져오기")
    up = st.file_uploader("i-Tube 장비일지 파일", type=["xlsx"], key="import_file",
                          help="이미 등록된 실적(같은 장비·기간·기관·시간)은 건너뜁니다.")
    if up is not None:
        try:
            rows, master = itube.read_itube_file(up.getvalue())
        except Exception as e:  # 양식이 다른 파일
            st.error(f"파일을 읽지 못했습니다: {e}")
            rows, master = [], []
        if rows:
            hours = sum(r["hours"] for r in rows)
            st.info(f"실적 {len(rows)}건 (총 {hours:,} h)을 찾았습니다.")
            if st.button(f"{len(rows)}건 가져오기", type="primary"):
                with db.undo_group(f"엑셀 가져오기 {len(rows)}건"):
                    res = db.import_parsed(rows, master, "가져오기")
                st.session_state.settings_saved = (
                    f"{res['inserted']}건 등록 · 중복 {res['skipped']}건 건너뜀 · 새 장비 {res['created_equipment']}대 추가")
                st.rerun()
        elif up is not None:
            st.warning("실적 행을 찾지 못했습니다. 3행에 헤더, 4행부터 데이터가 있는 i-Tube 양식인지 확인하세요.")

    st.subheader("백업 · 복원")
    if db.is_local():
        st.warning("구글 시트가 연결되지 않아 앱 서버의 임시 파일에 저장 중입니다. 앱이 재시작되면 지워질 수 있으니 "
                   "README의 안내대로 Secrets에 구글 시트를 연결하세요.")
    else:
        st.caption("구글 시트에 저장 중 · 시트의 1행 열 제목은 바꾸지 마세요.")
    # 백업 파일은 누를 때만 만듭니다 (화면을 고칠 때마다 시트 4개를 다시 읽지 않도록)
    if st.button("백업 파일 만들기", icon=":material/inventory_2:", help="한 달에 한 번쯤 내려받아 팀 드라이브에 보관하세요."):
        st.session_state.backup_file = db.backup_bytes()
    if st.session_state.get("backup_file"):
        st.download_button("전체 데이터 백업 내려받기", data=st.session_state.backup_file, mime=XLSX, icon=":material/download:",
                           file_name=(f"장비관리_백업_{dt.date.today():%Y%m%d}.xlsx"), type="primary")
    with st.expander("백업 파일로 복원 (현재 데이터를 모두 덮어씀)"):
        bk = st.file_uploader("백업 파일", type=["xlsx"], key="restore_file")
        ok = st.checkbox("현재 데이터가 모두 지워지고 백업 내용으로 바뀌는 것을 확인했습니다.")
        if bk is not None and ok and st.button("복원 실행", type="primary"):
            try:
                res = db.restore_bytes(bk.getvalue())
                st.session_state.settings_saved = f"복원했습니다 · 장비 {res['equipment']}대, 실적 {res['usage_log']}건"
                st.rerun()
            except KeyError:
                st.error("이 프로그램에서 내려받은 백업 파일이 아닙니다 (equipment / usage_log 시트가 없음).")
