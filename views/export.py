import base64
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

from core import calc, db, itube, rules, seed
from views.common import period_picker
from ui_style import empty_state, page_header, section_bar
from core.terms import w

UTIL_PCT = w("가동률(%)")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "itube_template.xlsx"


def itube_template(cfg: dict) -> bytes | None:
    """설정에서 올린 공식 양식, 없으면 앱에 들어 있는 i-Tube 양식(equip_log_template)."""
    if cfg.get("template_b64"):
        return base64.b64decode(cfg["template_b64"])
    return TEMPLATE_PATH.read_bytes() if TEMPLATE_PATH.exists() else None


def itube_selection(logs: pd.DataFrame, s: dt.date, e: dt.date, *, start_only: bool = True,
                    types: list[str] | None = None, labels: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """i-Tube 양식에 넣을 실적과, ITUBE번호가 없어 뺀 실적.

    start_only: 사용시작일이 기간 안에 있는 실적만 (아니면 기간과 겹치는 실적 모두).
    세부장비 실적은 ITUBE번호가 있는 상위 장비 이름으로 올립니다.
    """
    if logs.empty:
        return logs, logs
    if start_only:
        sel = logs[(logs["start_date"] >= pd.Timestamp(s)) & (logs["start_date"] <= pd.Timestamp(e))]
    else:
        sel = logs[(logs["start_date"] <= pd.Timestamp(e)) & (logs["end_date"] >= pd.Timestamp(s))]
    if types:
        sel = sel[sel["usage_type"].isin(types)]
    if labels:
        sel = sel[sel["purpose"].map(seed.purpose_label).isin(labels)]
    sel = sel.sort_values(["start_date", "equip_name", "id"]).copy()
    no_code = sel[sel["itube_code"] == ""]
    sel = sel[sel["itube_code"] != ""].copy()
    sel["equip_name"], sel["equip_code"], sel["equip_kind"] = sel["itube_name"], sel["itube_code"], sel["itube_kind"]
    return sel, no_code


def _itube_filename(cfg: dict, s: dt.date, e: dt.date) -> str:
    months = f"{s.month:02d}" if (s.year, s.month) == (e.year, e.month) else f"{s.month:02d}~{e.month:02d}"
    name = f"equip_log_template_{cfg.get('org_name', '')}_{s:%y}.{months}월 장비실적"
    if cfg.get("org_suffix"):
        name += f"_{cfg['org_suffix']}"
    return name + ".xlsx"


def _common(title: str, key: str):
    page_header(title, "실적")
    cfg = db.get_settings()
    logs = db.load_logs()
    eq = db.load_equipment()
    years = sorted({d.year for d in logs["start_date"].dropna()}) if not logs.empty else []

    s, e, label, _ = period_picker(key, ["월", "분기", "반기", "연", "직접 지정"], "분기",
                                   completed=True, years=years)
    section_bar(label, sub=f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", first=True)
    return cfg, logs, eq, s, e, label


def render_itube() -> None:
    cfg, logs, eq, s, e, label = _common("i-Tube 장비일지", "itube")
    c1, c2 = st.columns(2)
    basis = c1.radio("포함 기준", ["사용시작일이 기간 안에 있는 실적", "기간과 겹치는 실적 모두"], horizontal=False)
    types = c2.multiselect("활용유형", sorted(t for t in logs["usage_type"].unique() if t), placeholder="전체")
    sel, no_code = itube_selection(logs, s, e, start_only=basis.startswith("사용시작일"), types=types)
    m1, m2, m3 = st.columns(3)
    m1.metric("건수", f"{len(sel):,}")
    m2.metric("사용시간", f"{sel['hours'].sum():,.0f} h")
    m3.metric("사용료", f"{sel['fee'].sum():,.0f} 원")

    if not no_code.empty:
        names = ", ".join(sorted(set(no_code["equip_name"])))
        st.caption(f"ITUBE번호가 없는 장비 실적 {len(no_code)}건은 넣지 않았습니다: {names}")
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
    template = itube_template(cfg)
    if records:
        data = itube.make_itube_file(records, [(n, c) for n, c in zip(eq["name"], eq["code"]) if c], template)
        st.download_button("i-Tube 장비일지 내려받기", data=data, file_name=fname, mime=XLSX,
                           type="primary", width="stretch", icon=":material/download:")
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


def render_report() -> None:
    cfg, logs, eq, s, e, label = _common(w("가동률 분석 보고서"), "report")
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(cfg.get("target_util") or 0)
    cutoff = dt.date.today()
    daily = calc.expand_daily(logs, cfg.get("alloc_mode", "spread"), db.charger_caps())
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


# ── 실적 내려받기 (i-Tube 업로드 양식 equip_log_template) ──────────────

LABELS = ["시험", "제조", "분석", "교육", "지원"]


def _download_body(key: str) -> None:
    """기간을 고르면 그 기간 실적을 i-Tube 장비일지 양식에 채워 내려받습니다."""
    cfg = db.get_settings()
    logs = db.load_logs()
    eq = db.load_equipment()
    years = sorted({d.year for d in logs["start_date"].dropna()}) if not logs.empty else []
    s, e, label, _ = period_picker(key, ["월", "분기", "반기", "연", "직접 지정"], "월", years=years)
    if e < s:
        s, e = e, s
    labs = st.pills("구분", LABELS, selection_mode="multi", default=LABELS, key=f"{key}_labs",
                    help="고른 구분의 실적만 넣습니다.") or LABELS
    sel, no_code = itube_selection(logs, s, e, start_only=True, labels=labs)
    if sel.empty and no_code.empty:
        empty_state("이 기간에는 실적이 없어요", f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", icon="🗓️")
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("실적", f"{len(sel):,}건")
    m2.metric("사용시간", f"{sel['hours'].sum():,.0f} h")
    m3.metric("장비", f"{sel['equip_code'].nunique():,}대")
    if not no_code.empty:
        names = ", ".join(sorted(set(no_code["equip_name"])))
        st.caption(f"ITUBE번호가 없는 장비 실적 {len(no_code)}건은 빠져요: {names}")
    if len(sel) > 1000:
        st.warning("i-Tube는 한 번에 1000건까지 올릴 수 있어요. 기간을 나눠 주세요.", icon=":material/info:")
    if sel.empty:
        return
    data = itube.make_itube_file(sel.to_dict("records"), [(n, c) for n, c in zip(eq["name"], eq["code"]) if c],
                                 itube_template(cfg))
    st.download_button("엑셀로 내려받기", data=data, file_name=_itube_filename(cfg, s, e), mime=XLSX,
                       type="primary", width="stretch", icon=":material/download:", key=f"{key}_btn")


@st.dialog("실적 내려받기", width="large")
def download_dialog() -> None:
    _download_body("dl")


def render_download() -> None:
    page_header("실적 내려받기", "실적")
    _download_body("dlpage")
