import base64
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

from core import calc, db, itube, report, rules, seed
from views.common import period_picker
from ui_style import empty_state, page_header, section_bar
from core.terms import w

UTIL_PCT = w("가동률(%)")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


NO_CODE = "-"  # i-Tube 번호가 없는 장비의 장비번호 칸
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
    sel = sel.copy()
    has = sel["itube_code"] != ""
    sel.loc[has, "equip_name"] = sel.loc[has, "itube_name"]
    sel.loc[has, "equip_code"] = sel.loc[has, "itube_code"]
    if (~has).any():
        # 2026-11-23: i-Tube에 등록이 안 되는 시설(드라이룸 등)도 기록용으로 넣음.
        # 장비명 = 맨 위 장비 이름 (사용자: 세부장비 이름 말고 상위 이름), 장비번호 '-'
        eq = db.load_equipment()
        root = dict(zip(eq["id"], eq["root_id"])) if "root_id" in eq else {}
        name = dict(zip(eq["id"], eq["name"]))
        top = sel.loc[~has, "equip_id"].map(lambda v: root.get(int(v), int(v)) if pd.notna(v) else v)
        sel.loc[~has, "equip_name"] = [name.get(t) or n for t, n in zip(top, sel.loc[~has, "equip_name"])]
        sel.loc[~has, "equip_code"] = NO_CODE
    # 2026-11-23 사용자: 가동률 시트에는 모두 '주장비' (부장비로 등록된 장비도)
    sel["equip_kind"] = "주장비"
    return fill_from_companies(sel, db.load_companies()), no_code


def _history(logs: pd.DataFrame) -> list[dict]:
    """빈 지원개요·제품명을 채울 때 참고할 전체 실적 (업체·i-Tube 장비·내용만)."""
    cols = [c for c in ("id", "start_date", "itube_code", "company", "dept", "detail", "product") if c in logs]
    return logs[cols].to_dict("records") if not logs.empty else []


def _over_weekday_hours(sel: pd.DataFrame) -> pd.DataFrame:
    """사용시간이 기간 안 평일 수 × 24h 를 넘는 실적 (휴무일자포함 N 으로 올릴 때 걸릴 수 있음)."""
    if sel.empty:
        return sel
    off = calc.kr_holidays({d.year for d in sel["start_date"].dropna()} | {d.year for d in sel["end_date"].dropna()})

    def cap(s, e) -> float:
        if pd.isna(s):
            return float("inf")
        days = pd.date_range(s, e if pd.notna(e) else s)
        return 24.0 * sum(1 for d in days if d.weekday() < 5 and d.date() not in off)
    return sel[[float(db.to_num(h, 0) or 0) > cap(s, e) for h, s, e in zip(sel["hours"], sel["start_date"], sel["end_date"])]]


def fill_from_companies(sel: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    """실적에 비어 있는 사업자등록번호·업종·품목을 업체 목록(같은 이름)에서 채움.

    실적을 먼저 넣고 업체 번호를 나중에 알게 된 경우에도 i-Tube 파일에 번호가 들어가게 (2026-11-20).
    """
    if sel.empty or comp.empty:
        return sel
    by_name = {db.to_str(r["name"]): r for r in comp.to_dict("records") if db.to_str(r.get("name"))}
    sel = sel.copy()
    for col in ("brn", "industry", "item", "sub_item"):
        if col not in sel or col not in comp:
            continue
        cur = sel[col].map(db.to_str)
        sel[col] = [c if c else db.to_str(by_name.get(db.to_str(n), {}).get(col))
                    for c, n in zip(cur, sel["company"])]
    return sel


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
    m3.metric("수수료", f"{sel['fee'].sum():,.0f} 원")

    if not no_code.empty:
        names = ", ".join(sorted(set(no_code["equip_name"])))
        st.caption(f"ITUBE번호가 없는 장비 실적 {len(no_code)}건은 장비번호 '-'로 들어가요: {names}")
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
        pairs = [(n, c) for n, c in zip(eq["name"], eq["code"]) if c]
        hist = _history(logs)
        data = lambda records=records, pairs=pairs, template=template, hist=hist: itube.make_itube_file(  # noqa: E731 - 누를 때만 만듦
            records, pairs, template, hist)
        st.download_button("i-Tube 장비일지 내려받기", data=data, file_name=fname, mime=XLSX,
                           type="primary", width="stretch", icon=":material/download:")
        with st.expander("미리보기"):
            st.dataframe(sel[["purpose", "usage_type", "company", "equip_name", "equip_code", "start_date",
                              "end_date", "hours", "fee"]].rename(columns={
                "purpose": "사용목적", "usage_type": "활용유형", "company": "기업명", "equip_name": "장비명",
                "equip_code": "장비번호", "start_date": "시작일", "end_date": "종료일", "hours": "사용시간",
                "fee": "수수료"}), hide_index=True, width="stretch",
                column_config={"시작일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                               "종료일": st.column_config.DateColumn(format="YYYY-MM-DD")})
    else:
        empty_state("이 기간에 실적이 없습니다")


def render_report() -> None:
    cfg, logs, eq, s, e, label = _common(w("가동률 분석 보고서"), "report")
    annual = float(cfg.get("annual_hours") or 2000)
    target = float(report.kpi(cfg, s.year)["util_total"] or 0)  # 2026-11-19 설정 › KPI 목표
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
                       UTIL_PCT: t["util"], "수수료": t["fee"]})
        cur = me + dt.timedelta(days=1)
    monthly = pd.DataFrame(months)
    in_period = logs[(logs["start_date"] <= pd.Timestamp(e)) & (logs["end_date"] >= pd.Timestamp(s))]
    by_purpose = calc.breakdown(daily, logs, s, e_eff, "purpose").rename(columns={"purpose": "사용목적"})
    by_type = calc.breakdown(daily, logs, s, e_eff, "usage_type").rename(columns={"usage_type": "활용유형"})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(w("평균 가동률"), f"{tot['util']:.1f}%")
    m2.metric("사용시간", f"{tot['used']:,.0f} h")
    m3.metric("가용시간", f"{tot['avail']:,.0f} h")
    m4.metric("수수료", f"{tot['fee']:,.0f} 원")
    if e_eff < e:
        st.caption(f"{cutoff:%m/%d}까지 집계")
    st.dataframe(monthly, hide_index=True, width="stretch",
                 column_config={UTIL_PCT: st.column_config.NumberColumn(format="%.1f"),
                                "사용시간": st.column_config.NumberColumn(format="%.1f"),
                                "가용시간": st.column_config.NumberColumn(format="%.1f"),
                                "수수료": st.column_config.NumberColumn(format="%d")})
    args = (label, summary, tot, monthly, by_purpose, by_type, in_period, target, annual)
    data = lambda args=args: itube.make_report(*args)  # noqa: E731 - 누를 때만 만듦
    st.download_button(w("가동률 분석 보고서 내려받기"), data=data, mime=XLSX, type="primary", icon=":material/download:",
                       file_name=w(f"장비가동률_분석_{label.replace(' ', '')}.xlsx"), width="stretch")


# ── 실적 내려받기 (i-Tube 업로드 양식 equip_log_template) ──────────────

LABELS = ["시험", "제조", "분석", "교육", "지원"]
# 2026-11-23 사용자: 분야를 담당자(센터)별로 나눔. 충방전기만 센터 셋으로, 제조는 오창(제조검증·MV)·문백.
# 항목이 많아 버튼 대신 목록에서 여러 개 고름.
# 2026-11-23 사용자: 이름이 눈에 잘 들어오게 "무엇 · 지역.센터명" (정확한 센터 이름으로).
_OC, _MV, _MB = "오창.배터리제조검증지원센터", "오창.MV배터리안전성평가센터", "문백.배터리연구지원센터"
ENV_OC, ENV_MB = "환경시험 · 오창.배터리제조검증지원센터·MV배터리안전성평가센터", f"환경시험 · {_MB}"  # 문백 = 실환경모사·안전시험 챔버
CH_MV, CH_OC, CH_MB = f"충방전 · {_MV}", f"충방전 · {_OC}", f"충방전 · {_MB}"
MF_OC, MF_MB, AN_OC = f"제조 · {_OC}", f"제조 · {_MB}", f"분석 · {_OC}"
# 내려받는 파일 이름에 붙일 짧은 이름
FIELD_TAG = {ENV_OC: "환경시험-오창", ENV_MB: "환경시험-문백", CH_MV: "충방전-MV", CH_OC: "충방전-제조검증",
             CH_MB: "충방전-문백", MF_OC: "제조-오창", MF_MB: "제조-문백", AN_OC: "분석-오창"}
FIELDS = [ENV_OC, ENV_MB, CH_MV, CH_OC, CH_MB, MF_OC, MF_MB, AN_OC, "기타"]


def equip_fields(eq: pd.DataFrame) -> dict[int, str]:
    """장비 ID → 분야. 구분(시험·충방전·제조·분석)은 장비 가동 현황과 같은 규칙, 충방전·제조는 센터로 한 번 더 나눔.

    세부장비는 맨 위 장비의 구분을 따름 (예: 충방전기 시스템 아래 에이징 챔버 → 충방전, 분석기 아래 항온항습기 → 분석)."""
    from core import status
    grp = status.device_group(eq, db.load_channels())
    cen = db.equip_centers(eq)
    root = {int(i): int(r) for i, r in zip(eq["id"], eq["root_id"]) if pd.notna(r) and int(r)} if "root_id" in eq else {}
    out = {}
    for i in eq["id"].astype(int):
        g = grp.get(root.get(i, i), grp.get(i, "기타"))
        c = db.center_short(cen.get(i, ""))
        if g == status.CHARGER:
            out[i] = CH_MB if c == "문백" else CH_MV if c == "MV" else CH_OC
        elif g == "제조":
            out[i] = MF_MB if c == "문백" else MF_OC  # 제조검증·MV = 오창
        elif g == "시험":
            out[i] = ENV_MB if c == "문백" else ENV_OC
        elif g == "분석":
            out[i] = AN_OC
        else:
            out[i] = g if g in FIELDS else "기타"
    return out


def _tidy_fields(k: str) -> None:
    """'전체'와 다른 분야를 같이 고르지 않게: 방금 고른 쪽만 남김."""
    cur = list(st.session_state.get(k) or [])
    prev = st.session_state.get(f"_{k}_prev", ["전체"])
    if "전체" in cur and len(cur) > 1:
        cur = ["전체"] if "전체" not in prev else [f for f in cur if f != "전체"]
    st.session_state[k] = cur
    st.session_state[f"_{k}_prev"] = cur


_CNT_JS = """<script>
(() => {
  const w = window.parent || window;
  w.__itubeCnt = %s;
  if (w.__itubeCntObs) { w.__itubeCntObs(); return; }
  const doc = w.document;
  const st = doc.createElement('style');
  st.textContent = `[role=option][data-cnt]{display:flex;align-items:center}
[role=option][data-cnt]::after{content:attr(data-cnt);margin-left:auto;padding-left:24px;font-size:.78rem;color:#94A3B8}
[role=option][data-zero]{opacity:.4}`;
  doc.head.appendChild(st);
  const hide = () => doc.querySelectorAll('[data-testid=stHtml] > script').forEach(sc => {
    if (sc.textContent.includes('__itubeCnt')) sc.closest('[data-testid=stElementContainer]').style.display = 'none';
  });
  const run = () => { hide(); doc.querySelectorAll('[role=option]').forEach(o => {
    const n = w.__itubeCnt[o.textContent.trim()];
    if (n === undefined) { o.removeAttribute('data-cnt'); o.removeAttribute('data-zero'); return; }
    o.setAttribute('data-cnt', n.toLocaleString() + '건');
    if (n) o.removeAttribute('data-zero'); else o.setAttribute('data-zero', '');
  }); };
  w.__itubeCntObs = run;
  new w.MutationObserver(run).observe(doc.body, {childList: true, subtree: true});
  run();
})();
</script>"""


def _option_counts(cnt: dict[str, int]) -> None:
    """분야 목록: 이름은 그대로, 건수는 오른쪽에 작게, 0건은 흐리게 (2026-11-23 사용자)."""
    import json
    st.html(_CNT_JS % json.dumps(cnt, ensure_ascii=False), unsafe_allow_javascript=True)


def _download_body(key: str) -> None:
    """기간을 고르면 그 기간 실적을 i-Tube 장비일지 양식에 채워 내려받습니다."""
    cfg = db.get_settings()
    logs = db.load_logs()
    eq = db.load_equipment()
    years = sorted({d.year for d in logs["start_date"].dropna()}) if not logs.empty else []
    s, e, label, _ = period_picker(key, ["월", "분기", "반기", "연", "직접 지정"], "월", years=years)
    if e < s:
        s, e = e, s
    # 2026-11-10: 분야는 입력할 때 고른 '사용목적'이 아니라 장비의 '장비용도'(제조·시험·분석)로 나눔.
    # 장비마다 분야가 하나라 각 담당자가 자기 분야만 내려받아도 겹치거나 빠지는 실적이 없음.
    field_of = equip_fields(eq)
    all_sel, _ = itube_selection(logs, s, e, start_only=True)
    cnt = all_sel["equip_id"].map(lambda v: field_of.get(int(v), "기타")).value_counts() if not all_sel.empty else {}
    opts = ["전체"] + [f for f in FIELDS if f in cnt or f != "기타"]
    total = len(all_sel)
    from views import common as _cm
    with _cm.LAST_ROW:  # 기간 단위·연도·월과 같은 줄 (2026-11-10)
        k = f"{key}_fields"
        st.session_state[k] = [f for f in st.session_state.get(k, ["전체"]) if f in opts] or ["전체"]
        picked = st.multiselect("분야", opts, key=f"{key}_fields", placeholder="분야 고르기",
                                on_change=_tidy_fields, args=(f"{key}_fields",))
    _option_counts({f: total if f == "전체" else int(cnt.get(f, 0)) for f in opts})
    if "전체" in picked:  # 전체를 고르면 나머지는 무시
        picked = []
    sel, no_code = itube_selection(logs, s, e, start_only=True)
    if picked:
        sel = sel[sel["equip_id"].map(lambda v: field_of.get(int(v), "기타")).isin(picked)]
        no_code = no_code[no_code["equip_id"].map(lambda v: field_of.get(int(v), "기타")).isin(picked)]
    if sel.empty and no_code.empty:
        empty_state("이 기간에는 실적이 없어요", f"{s:%Y-%m-%d} ~ {e:%Y-%m-%d}", icon="🗓️")
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("실적", f"{len(sel):,}건")
    m2.metric("사용시간", f"{sel['hours'].sum():,.0f} h")
    m3.metric("장비", f"{sel['equip_code'].nunique():,}대")
    if not no_code.empty:
        names = ", ".join(sorted(set(no_code["equip_name"])))
        st.caption(f"ITUBE번호가 없는 장비 실적 {len(no_code)}건은 장비번호 '-'로 들어가요: {names}")
    if len(sel) > 1000:
        st.warning("i-Tube는 한 번에 1000건까지 올릴 수 있어요. 기간을 나눠 주세요.", icon=":material/info:")
    over = _over_weekday_hours(sel)
    if not over.empty:  # 휴무일자포함을 모두 N으로 내보내서 (2026-11-23)
        st.caption(f"주말·공휴일까지 쓴 실적 {len(over)}건은 사용시간이 평일 시간(평일 수 × 24h)보다 많아 "
                   f"i-Tube에서 걸릴 수 있어요: " + ", ".join(sorted(set(over["equip_name"]))))
    if sel.empty:
        return
    args = (sel.to_dict("records"), [(n, c) for n, c in zip(eq["name"], eq["code"]) if c], itube_template(cfg),
            _history(logs))
    data = lambda args=args: itube.make_itube_file(*args)  # noqa: E731 - 누를 때만 만듦
    fname = _itube_filename(cfg, s, e)
    if picked:
        tag = "_".join(FIELD_TAG.get(f, f) for f in picked)
        fname = fname.replace(".xlsx", f"_{tag}.xlsx")
    st.download_button("엑셀로 내려받기", data=data, file_name=fname, mime=XLSX,
                       type="primary", width="stretch", icon=":material/download:", key=f"{key}_btn")


@st.dialog("i-Tube 제출", width="large")
def download_dialog() -> None:
    _download_body("dl")


def render_download() -> None:
    page_header("i-Tube 제출", "실적")
    _download_body("dlpage")
