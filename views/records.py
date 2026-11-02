import datetime as dt

import pandas as pd
import streamlit as st

from core import db, rules, seed
from core.calc import period_bounds

# 표 열 이름 → DB 필드
FIELDS = {
    "장비": "equip_label",
    "사용목적": "purpose",
    "활용유형": "usage_type",
    "기업명": "company",
    "사업자번호": "brn",
    "내부부서명": "dept",
    "업종": "industry",
    "품목": "item",
    "세부품목": "sub_item",
    "제품명": "product",
    "시료수": "samples",
    "공개": "disclose",
    "세부지원내용": "detail",
    "시작일": "start_date",
    "종료일": "end_date",
    "휴무포함": "include_holidays",
    "사용시간": "hours",
    "사용료": "fee",
    "사용목적(상세)": "purpose_detail",
    "기타": "etc",
    "작성자": "created_by",
}


def render() -> None:
    st.title("📋 실적 조회·수정")
    saved = st.session_state.pop("records_saved", None)
    if saved:
        st.success(saved)

    logs = db.load_logs()
    eq = db.load_equipment()
    comp = db.load_companies()
    master = {r["name"]: r for r in comp.to_dict("records")}
    label_of = dict(zip(eq["id"], eq["label"]))
    id_of = dict(zip(eq["label"], eq["id"]))

    q_s, q_e, _ = period_bounds("분기", dt.date.today())
    c1, c2, c3, c4 = st.columns([1.4, 2, 1.2, 1])
    rng = c1.date_input("사용시작일 범위", value=(q_s, q_e), format="YYYY-MM-DD")
    sel_eq = c2.multiselect("장비", list(eq["label"]), placeholder="전체")
    comp_q = c3.text_input("기관명 검색", placeholder="일부만 입력해도 됩니다")
    writers = sorted(w for w in logs["created_by"].unique() if w)
    writer = c4.selectbox("작성자", ["전체"] + writers)

    df = logs.copy()
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        df = df[(df["start_date"] >= pd.Timestamp(rng[0])) & (df["start_date"] <= pd.Timestamp(rng[1]))]
    if sel_eq:
        df = df[df["equip_id"].isin([id_of[x] for x in sel_eq])]
    if comp_q:
        df = df[df["company"].str.contains(comp_q, case=False, regex=False)]
    if writer != "전체":
        df = df[df["created_by"] == writer]

    m1, m2, m3 = st.columns(3)
    m1.metric("건수", f"{len(df):,}")
    m2.metric("사용시간 합계", f"{df['hours'].sum():,.0f} h")
    m3.metric("사용료 합계", f"{df['fee'].sum():,.0f} 원")

    if df.empty:
        st.info("조건에 맞는 실적이 없습니다.")
        return

    view = df.copy()
    view["equip_label"] = view["equip_id"].map(label_of)
    view["start_date"] = view["start_date"].dt.date
    view["end_date"] = view["end_date"].dt.date
    view = view.set_index("id")[list(FIELDS.values())].rename(columns={v: k for k, v in FIELDS.items()})
    view.insert(0, "삭제", False)

    st.caption("셀을 직접 고친 뒤 아래 '변경 내용 저장'을 누르세요. 지울 행은 '삭제'에 체크합니다.")
    edited = st.data_editor(
        view, key="records_editor", hide_index=True, width="stretch", height=520,
        disabled=["작성자", "사업자번호"],
        column_config={
            "삭제": st.column_config.CheckboxColumn(width="small"),
            "장비": st.column_config.SelectboxColumn(options=list(eq["label"]), width="large", required=True),
            "사용목적": st.column_config.SelectboxColumn(options=seed.PURPOSES, required=True),
            "활용유형": st.column_config.SelectboxColumn(options=seed.USAGE_TYPES, required=True),
            "기업명": st.column_config.SelectboxColumn(
                options=list(master) + sorted({c for c in view["기업명"] if c and c not in master}),
                help="'업체 관리'에 등록된 업체만 고를 수 있습니다. 사업자번호는 업체 목록에서 자동으로 채워집니다."),
            "사업자번호": st.column_config.TextColumn(help="'업체 관리'에서 고칩니다."),
            "업종": st.column_config.SelectboxColumn(options=seed.INDUSTRIES),
            "품목": st.column_config.SelectboxColumn(options=seed.ALL_ITEMS),
            "세부품목": st.column_config.SelectboxColumn(options=seed.ALL_SUBITEMS),
            "공개": st.column_config.SelectboxColumn(options=seed.YN, width="small"),
            "휴무포함": st.column_config.SelectboxColumn(options=seed.YN, width="small"),
            "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
            "종료일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
            "사용시간": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True),
            "사용료": st.column_config.NumberColumn(min_value=0, step=1000, format="%d"),
            "시료수": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            "세부지원내용": st.column_config.TextColumn(width="large"),
        },
    )

    to_delete = [int(i) for i in edited.index[edited["삭제"].fillna(False).astype(bool)]]
    changed = []
    for i in edited.index:
        if i in to_delete:
            continue
        a = edited.loc[i].drop("삭제").astype(str)
        b = view.loc[i].drop("삭제").astype(str)
        if not a.equals(b):
            changed.append(i)

    confirm = True
    if to_delete:
        confirm = st.checkbox(f"{len(to_delete)}건을 삭제합니다. 되돌릴 수 없습니다.", value=False)
    c1, c2 = st.columns([1, 3])
    if c1.button("변경 내용 저장", type="primary", disabled=not (changed or to_delete) or not confirm):
        errors, updates = [], {}
        for i in changed:
            row = edited.loc[i]
            rec = {FIELDS[col]: row[col] for col in FIELDS if col not in ("장비", "작성자")}
            rec["equip_id"] = id_of.get(row["장비"])
            rec["company"] = db.to_str(rec.get("company"))
            m = master.get(rec["company"])
            if m is not None:  # 사업자번호는 항상 업체 목록 기준
                rec["brn"] = m["brn"]
            elif not rec["company"]:
                rec["brn"] = ""
            errs = rules.validate(rec)
            if rec["equip_id"] is None:
                errs.append("장비를 선택하세요.")
            if errs:
                errors += [f"[{row['시작일']} {row['장비']}] {e}" for e in errs]
            else:
                updates[int(i)] = rec
        if errors:
            for e in errors:
                st.error(e)
        else:
            n_up = db.update_logs(updates) if updates else 0
            n_del = db.delete_logs(to_delete)
            st.session_state.records_saved = f"수정 {n_up}건 · 삭제 {n_del}건 반영했습니다."
            st.session_state.pop("records_editor", None)
            st.rerun()
    c2.caption(f"수정 {len(changed)}건 · 삭제 {len(to_delete)}건 대기 중" if (changed or to_delete) else "")
