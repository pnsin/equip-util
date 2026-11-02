import base64
import datetime as dt

import streamlit as st

from core import db, itube

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render() -> None:
    st.title("⚙️ 설정")
    msg = st.session_state.pop("settings_saved", None)
    if msg:
        st.success(msg)
    cfg = db.get_settings()

    st.subheader("기본 정보")
    with st.form("basic"):
        c1, c2, c3 = st.columns(3)
        org = c1.text_input("기관·팀명 (파일 이름에 사용)", value=cfg.get("org_name", ""))
        suffix = c2.text_input("파일 이름 끝 문구", value=cfg.get("org_suffix", ""))
        dept = c3.text_input("내부부서명 기본값", value=cfg.get("dept_default", ""))
        c1, c2, c3 = st.columns(3)
        annual = c1.number_input("연간 기준 가용시간 (h)", min_value=1, step=100, value=int(cfg.get("annual_hours") or 2000),
                                 help="장비별로 다르면 '장비 관리'에서 장비마다 따로 지정할 수 있습니다.")
        target = c2.number_input("목표 가동률 (%)", min_value=0.0, max_value=100.0, step=5.0,
                                 value=float(cfg.get("target_util") or 0))
        modes = {"spread": "사용기간에 고르게 나눔 (권장)", "start": "사용시작일에 전부 반영"}
        mode = c3.selectbox("기간별 집계 방식", list(modes), format_func=modes.get,
                            index=list(modes).index(cfg.get("alloc_mode", "spread")),
                            help="예: 7/25~8/10 실적 20시간을 7월·8월에 일수만큼 나눌지, 7월에 모두 넣을지")
        members = st.text_area("팀원 명단 (한 줄에 한 명)", value="\n".join(cfg.get("members") or []), height=120)
        if st.form_submit_button("저장", type="primary"):
            db.save_settings(org_name=org.strip(), org_suffix=suffix.strip(), dept_default=dept.strip(),
                             annual_hours=annual, target_util=target, alloc_mode=mode,
                             members=[m.strip() for m in members.splitlines() if m.strip()])
            st.session_state.settings_saved = "설정을 저장했습니다."
            st.rerun()

    st.subheader("기존 엑셀 실적 가져오기")
    st.caption("지금까지 작성한 i-Tube 장비일지 파일(예: '26.07~09월 장비실적)을 올리면 실적을 한 번에 등록합니다. "
               "이미 등록된 실적(같은 장비·기간·기관·시간)은 건너뜁니다.")
    up = st.file_uploader("i-Tube 장비일지 파일", type=["xlsx"], key="import_file")
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
                res = db.import_parsed(rows, master, st.session_state.get("user", "") or "가져오기")
                st.session_state.settings_saved = (
                    f"{res['inserted']}건 등록 · 중복 {res['skipped']}건 건너뜀 · 새 장비 {res['created_equipment']}대 추가")
                st.rerun()
        elif up is not None:
            st.warning("실적 행을 찾지 못했습니다. 3행에 헤더, 4행부터 데이터가 있는 i-Tube 양식인지 확인하세요.")

    st.subheader("i-Tube 공식 빈 양식")
    if cfg.get("template_b64"):
        st.success("공식 양식이 등록되어 있습니다. 내려받는 장비일지는 이 파일에 채워집니다.")
        if st.button("등록된 양식 지우기 (기본 재현 양식 사용)"):
            db.save_settings(template_b64="")
            st.rerun()
    else:
        st.caption("등록하지 않아도 같은 구조의 양식으로 내려받을 수 있습니다. i-Tube에서 받은 빈 양식을 올리면 그 파일에 그대로 채웁니다.")
    tpl = st.file_uploader("i-Tube에서 받은 빈 양식 (.xlsx)", type=["xlsx"], key="tpl_file")
    if tpl is not None and st.button("이 파일을 양식으로 등록"):
        db.save_settings(template_b64=base64.b64encode(tpl.getvalue()).decode())
        st.session_state.settings_saved = "공식 양식을 등록했습니다."
        st.rerun()

    st.subheader("백업 · 복원")
    if db.is_local():
        st.warning("구글 시트가 연결되지 않아 앱 서버의 임시 파일에 저장 중입니다. 앱이 재시작되면 지워질 수 있으니 "
                   "README의 안내대로 Secrets에 구글 시트를 연결하세요.")
    else:
        st.caption("구글 시트에 저장 중입니다 (탭: 장비 / 사용실적 / 설정). 시트의 1행 열 제목은 바꾸지 마세요.")
    st.download_button("⬇️ 전체 데이터 백업 내려받기", data=db.backup_bytes(), mime=XLSX,
                       file_name=f"가동률관리_백업_{dt.date.today():%Y%m%d}.xlsx")
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
