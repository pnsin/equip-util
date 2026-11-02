import base64
import datetime as dt

import pandas as pd
import streamlit as st

from core import calc, db, itube, rules
from views.common import period_picker
from ui_style import empty_state, page_header, section_bar
from core.terms import w

UTIL_PCT = w("가동률(%)")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _itube_filename(cfg: dict, s: dt.date, e: dt.date) -> str:
    months = f"{s.month:02d}" if (s.year, s.month) == (e.year, e.month) else f"{s.month:02d}~{e.month:02d}"
    name = f"equip_log_template_{cfg.get('org_name', '')}_'{s:%y}.{months}월 장비실적"
    if cfg.get("org_suffix"):
        name += f"_{cfg['org_suffix']}"
    return name + ".xlsx"


def render() -> None:
    page_header("엑셀 내려받기", "실적")
    cfg = db.get_settings()
    logs = db.load_logs()
    eq = db.load_equipment()
    years = sorted({d.year for d in logs["start_date"].dropna()}) if not logs.empty else []

    s, e, label, _ = period_picker("export", ["월", "분기", "반기", "연", "직접 지정"], "분기",
                                   completed=True, years=years)
    section_bar(label, sub=f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", first=True)

    tab1, tab2 = st.tabs(["i-Tube 제출용 장비일지", w("가동률 분석 보고서")])

    with tab1:
        c1, c2 = st.columns(2)
        basis = c1.radio("포함 기준", ["사용시작일이 기간 안에 있는 실적", "기간과 겹치는 실적 모두"], horizontal=False)
        types = c2.multiselect("활용유형", sorted(t for t in logs["usage_type"].unique() if t), placeholder="전체")
        if basis.startswith("사용시작일"):
            sel = logs[(logs["start_date"] >= pd.Timestamp(s)) & (logs["start_date"] <= pd.Timestamp(e))]
        else:
            sel = logs[(logs["start_date"] <= pd.Timestamp(e)) & (logs["end_date"] >= pd.Timestamp(s))]
        if types:
            sel = sel[sel["usage_type"].isin(types)]
        sel = sel.sort_values(["start_date", "equip_name", "id"])

        m1, m2, m3 = st.columns(3)
        m1.metric("건수", f"{len(sel):,}")
        m2.metric("사용시간", f"{sel['hours'].sum():,.0f} h")
        m3.metric("사용료", f"{sel['fee'].sum():,.0f} 원")

        records = sel.to_dict("records")
        issues = []
        for r in records:
            for msg in rules.validate(r):
                issues.append({"시작일": r["start_date"].date(), "장비": r["equip_name"], "기관": r["company"], "문제": msg})
        if len(records) > 1000:
            st.warning("i-Tube는 한 번에 1000건까지만 올릴 수 있습니다. 기간을 나눠서 내려받으세요.")
        if issues:
            st.warning(f"i-Tube 규칙에 맞지 않는 항목 {len(issues)}개",
                       icon=":material/warning:")
            st.dataframe(pd.DataFrame(issues), hide_index=True, width="stretch")
        elif records:
            st.success("i-Tube 업로드 규칙 통과", icon=":material/verified:")

        fname = st.text_input("파일 이름", value=_itube_filename(cfg, s, e))
        template = base64.b64decode(cfg["template_b64"]) if cfg.get("template_b64") else None
        if records:
            data = itube.make_itube_file(records, list(zip(eq["name"], eq["code"])), template)
            st.download_button("i-Tube 장비일지 내려받기", data=data, file_name=fname, mime=XLSX,
                               type="primary", width="stretch", icon=":material/download:")
            if template:
                st.caption("등록된 공식 양식에 채워 넣습니다.")
            with st.expander("미리보기"):
                st.dataframe(sel[["purpose", "usage_type", "company", "equip_name", "equip_code", "start_date",
                                  "end_date", "hours", "fee"]].rename(columns={
                    "purpose": "사용목적", "usage_type": "활용유형", "company": "기업명", "equip_name": "장비명",
                    "equip_code": "장비번호", "start_date": "시작일", "end_date": "종료일", "hours": "사용시간",
                    "fee": "사용료"}), hide_index=True, width="stretch",
                    column_config={"시작일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                                   "종료일": st.column_config.DateColumn(format="YYYY-MM-DD")})
        else:
            empty_state("이 기간에 실적이 없습니다")

    with tab2:
        annual = float(cfg.get("annual_hours") or 2000)
        target = float(cfg.get("target_util") or 0)
        cutoff = dt.date.today()
        daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"))
        e_eff = calc.effective_end(s, e, cutoff)
        summary = calc.equipment_summary(daily, eq, s, e_eff, annual)
        tot = calc.totals(summary)

        months = []
        cur = dt.date(s.year, s.month, 1)
        while cur <= e_eff:
            _, me, _ = calc.period_bounds("월", cur)
            t = calc.totals(calc.equipment_summary(daily, eq, max(cur, s), min(me, e_eff), annual))
            months.append({"월": f"{cur:%Y-%m}", "사용시간": t["used"], "가용시간": t["avail"],
                           UTIL_PCT: t["util"], "사용료": t["fee"]})
            cur = me + dt.timedelta(days=1)
        monthly = pd.DataFrame(months)
        in_period = logs[(logs["start_date"] <= pd.Timestamp(e)) & (logs["end_date"] >= pd.Timestamp(s))]
        by_purpose = calc.breakdown(daily, logs, s, e_eff, "purpose").rename(columns={"purpose": "사용목적"})
        by_type = calc.breakdown(daily, logs, s, e_eff, "usage_type").rename(columns={"usage_type": "활용유형"})

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(w("평균 가동률"), f"{tot['util']:.1f}%")
        m2.metric("사용시간", f"{tot['used']:,.0f} h")
        m3.metric("가용시간", f"{tot['avail']:,.0f} h")
        m4.metric("사용료", f"{tot['fee']:,.0f} 원")
        if e_eff < e:
            st.caption(f"{cutoff:%m/%d}까지 집계")
        st.dataframe(monthly, hide_index=True, width="stretch",
                     column_config={UTIL_PCT: st.column_config.NumberColumn(format="%.1f"),
                                    "사용시간": st.column_config.NumberColumn(format="%.1f"),
                                    "가용시간": st.column_config.NumberColumn(format="%.1f"),
                                    "사용료": st.column_config.NumberColumn(format="%d")})
        data = itube.make_report(label, summary, tot, monthly, by_purpose, by_type, in_period, target, annual)
        st.download_button(w("가동률 분석 보고서 내려받기"), data=data, mime=XLSX, type="primary", icon=":material/download:",
                           file_name=w(f"장비가동률_분석_{label.replace(' ', '')}.xlsx"), width="stretch")
