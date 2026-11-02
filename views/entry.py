import datetime as dt
import hashlib

import pandas as pd
import streamlit as st

from core import db, rules, seed
from core.calc import period_bounds

def _idx(options: list, value, default: int = 0) -> int:
    return options.index(value) if value in options else default


def render() -> None:
    st.title("✍️ 사용실적 입력")
    st.caption("같은 기관·같은 기간에 여러 장비를 썼다면 장비를 여러 개 고르고 장비별 시간만 적으세요. 장비마다 한 건씩 저장됩니다.")

    saved = st.session_state.pop("entry_saved", None)
    if saved:
        st.success(saved)
        st.toast(saved, icon="✅")

    cfg = db.get_settings()
    eq = db.load_equipment()
    logs = db.load_logs()
    if eq.empty:
        st.warning("등록된 장비가 없습니다. '설정 → 기존 엑셀 실적 가져오기'로 i-Tube 장비일지 파일을 올리면 "
                   "장비 목록(Sheet4)과 실적이 함께 등록됩니다. '장비 관리'에서 직접 추가해도 됩니다.")
        return
    ver = st.session_state.setdefault("entry_ver", 0)
    staff_opts = db.staff_names()
    last = st.session_state.get("last_staff")
    user = st.selectbox("담당자", staff_opts, index=staff_opts.index(last) if last in staff_opts else None,
                        placeholder="담당자를 고르세요", key=f"entry_{ver}_staff") or ""
    if not staff_opts:
        st.warning("등록된 담당자가 없습니다. '담당자 관리'에서 먼저 담당자를 등록하세요.")

    def k(name: str) -> str:
        return f"entry_{ver}_{name}"

    # 1. 사용기관 ─ 업체 관리에 등록된 업체 중에서 고름. 사업자번호·업종은 업체 목록, 나머지는 지난 실적에서 채움
    st.subheader("1. 사용기관")
    comp = db.load_companies()
    master = {r["name"]: r for r in comp.to_dict("records")}
    recent = logs.sort_values("id", ascending=False) if not logs.empty else logs
    recent = recent[recent["company"] != ""].drop_duplicates("company") if not recent.empty else recent
    c1, c2, c3 = st.columns([2, 1, 1])
    company = c1.selectbox("사용기관 기업명", list(master), index=None, key=k("comp"),
                           placeholder="업체명을 입력해 검색 (내부 사용이면 비워 두세요)")
    if not master:
        c1.caption("등록된 업체가 없습니다. '업체 관리'에서 먼저 업체를 등록하세요.")
    company = company or ""
    prev: dict = {}
    if company and not recent.empty and (recent["company"] == company).any():
        prev = recent[recent["company"] == company].iloc[0].to_dict()
    m = master.get(company)
    if m is not None:
        prev.update({k: m[k] for k in ("brn", "industry", "item", "sub_item") if m[k]})
    pk = hashlib.md5(company.encode()).hexdigest()[:8]  # 기관을 바꾸면 아래 기본값이 새로 채워지도록

    usage_type = c2.selectbox("활용유형", seed.USAGE_TYPES, index=_idx(seed.USAGE_TYPES, prev.get("usage_type")),
                              key=k(f"utype_{pk}"))
    purpose = c3.selectbox("사용목적", seed.PURPOSES, index=_idx(seed.PURPOSES, prev.get("purpose"), 3),
                           key=k(f"purpose_{pk}"))

    c1, c2, c3 = st.columns(3)
    brn = c1.text_input("사업자등록번호 (업체 관리 기준)", value=prev.get("brn", ""), key=k(f"brn_{pk}"),
                        disabled=True, help="사업자등록번호는 '업체 관리'에서 고칩니다.")
    dept = c2.text_input("내부부서명", value=prev.get("dept") or cfg.get("dept_default", ""), key=k(f"dept_{pk}"))
    product = c3.text_input("제품명", value=prev.get("product", ""), key=k(f"product_{pk}"))

    c1, c2, c3 = st.columns(3)
    ind = c1.selectbox("업종", seed.INDUSTRIES,
                       index=_idx(seed.INDUSTRIES, prev.get("industry"), _idx(seed.INDUSTRIES, "전기전자")),
                       key=k(f"ind_{pk}"))
    items = seed.ITEMS[ind]
    item = c2.selectbox("품목", items, index=_idx(items, prev.get("item"), _idx(items, "이차전지_에너지")),
                        key=k(f"item_{pk}_{ind}"))
    subs = seed.SUBITEMS.get(item, [])
    sub = c3.selectbox("세부품목", subs, index=_idx(subs, prev.get("sub_item")), key=k(f"sub_{pk}_{item}"))

    # 2. 사용 기간
    st.subheader("2. 사용 기간")
    today = dt.date.today()
    m_start, m_end, _ = period_bounds("월", today)
    c1, c2, c3, c4 = st.columns(4)
    start = c1.date_input("사용시작일", value=m_start, key=k("start"), format="YYYY-MM-DD")
    end = c2.date_input("사용종료일", value=m_end, key=k("end"), format="YYYY-MM-DD")
    hol = c3.radio("휴무일자포함", seed.YN, horizontal=True, key=k("hol"),
                   help="N이면 대시보드에서 주·월별로 나눌 때 주말·공휴일을 빼고 나눕니다.")
    disclose = c4.radio("세부지원공개여부", ["N", "Y"], horizontal=True, key=k("disc"))
    if start and end and end >= start:
        st.caption(f"사용기간 {(end - start).days + 1}일 · i-Tube 규칙: 같은 해, 2개월 이내")

    # 3. 장비와 시간
    st.subheader("3. 사용 장비와 시간")
    active = eq[eq["retired_on"].isna() | (eq["retired_on"] >= pd.Timestamp(start or today))]
    picked = st.multiselect("장비 선택 (여러 개 가능)", list(active["label"]), key=k("equip"),
                            placeholder="장비명이나 장비번호로 검색")
    table = None
    if picked:
        cache = st.session_state.setdefault(k("cache"), {})
        base = pd.DataFrame({
            "장비": picked,
            "사용시간(h)": [cache.get(p, (0, 0, 1))[0] for p in picked],
            "사용료(원)": [cache.get(p, (0, 0, 1))[1] for p in picked],
            "시료수": [cache.get(p, (0, 0, 1))[2] for p in picked],
        })
        sig = hashlib.md5("|".join(picked).encode()).hexdigest()[:8]
        table = st.data_editor(
            base, key=k(f"tbl_{sig}"), hide_index=True, width="stretch", disabled=["장비"],
            column_config={
                "장비": st.column_config.TextColumn(width="large"),
                "사용시간(h)": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
                "사용료(원)": st.column_config.NumberColumn(min_value=0, step=1000, format="%d"),
                "시료수": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            },
        )
        for r in table.to_dict("records"):
            cache[r["장비"]] = (r["사용시간(h)"], r["사용료(원)"], r["시료수"])
        st.caption(f"합계 {db.to_num(table['사용시간(h)'].sum(), 0):,.0f} h · "
                   f"{db.to_num(table['사용료(원)'].sum(), 0):,.0f} 원")

    # 4. 세부지원내용
    st.subheader("4. 세부지원내용")
    ov, me, co = seed.parse_detail(prev.get("detail", ""))
    c1, c2, c3 = st.columns(3)
    overview = c1.text_input("지원개요", value=ov, key=k(f"ov_{pk}"))
    method = c2.text_input("인증/인정/시험법", value=me or "-", key=k(f"me_{pk}"))
    content = c3.text_input("지원내용", value=co, key=k(f"co_{pk}"))
    c1, c2 = st.columns(2)
    purpose_detail = c1.text_input("사용목적 (상세, 양식 U열)", value=prev.get("purpose_detail", ""),
                                   placeholder="비워 두면 지원개요가 들어갑니다", key=k(f"pd_{pk}"))
    etc = c2.text_input("기타", key=k("etc"))

    if st.button("💾 저장", type="primary", width="stretch", disabled=not picked):
        common = {
            "purpose": purpose, "usage_type": usage_type, "company": company, "brn": brn, "dept": dept,
            "industry": ind, "item": item, "sub_item": sub, "product": product, "disclose": disclose,
            "detail": seed.compose_detail(overview, method, content),
            "start_date": start, "end_date": end, "include_holidays": hol,
            "purpose_detail": purpose_detail or overview, "etc": etc,
        }
        errors = [] if user else ["담당자를 선택하세요."]
        common_errs = rules.validate(dict(common, hours=1, fee=0))
        errors += common_errs
        label_to_id = dict(zip(eq["label"], eq["id"]))
        existing = {
            (int(e), db.to_date(s), db.to_date(f), c)
            for e, s, f, c in zip(logs["equip_id"], logs["start_date"], logs["end_date"], logs["company"])
        }
        recs = []
        for r in table.to_dict("records"):
            rec = dict(common, equip_id=int(label_to_id[r["장비"]]), hours=db.to_num(r["사용시간(h)"], 0),
                       fee=db.to_num(r["사용료(원)"], 0), samples=db.to_num(r["시료수"], 0))
            errors += [f"[{r['장비']}] {e}" for e in rules.validate(rec) if e not in common_errs]
            if (rec["equip_id"], start, end, company) in existing:
                errors.append(f"[{r['장비']}] 같은 기관·기간의 실적이 이미 있습니다. '실적 조회·수정'에서 확인하세요.")
            recs.append(rec)
        if errors:
            for e in errors:
                st.error(e)
        else:
            n = db.insert_logs(recs, user)
            st.session_state.last_staff = user
            st.session_state.entry_ver = ver + 1
            st.session_state.entry_saved = f"{n}건 저장했습니다 · 총 {sum(r['hours'] for r in recs):,.0f} h"
            st.rerun()

    st.divider()
    st.subheader(f"{user} 님의 최근 실적" if user else "최근 실적")
    mine = (logs[logs["created_by"] == user] if user else logs).sort_values("id", ascending=False).head(10)
    if mine.empty:
        st.caption("아직 입력한 실적이 없습니다.")
    else:
        st.dataframe(
            mine[["start_date", "end_date", "equip_name", "company", "purpose", "hours", "fee"]].rename(columns={
                "start_date": "시작일", "end_date": "종료일", "equip_name": "장비", "company": "기관",
                "purpose": "목적", "hours": "시간(h)", "fee": "사용료"}),
            hide_index=True, width="stretch",
            column_config={"시작일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                           "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                           "사용료": st.column_config.NumberColumn(format="%d")},
        )
