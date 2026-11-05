import datetime as dt
import json

import pandas as pd
import streamlit as st

from core import db, rules, seed
from core.calc import period_bounds
from ui_style import empty_state, page_header
from views.common import pin_table, unpin

# 표 열 이름 → DB 필드
FIELDS = {
    "장비": "equip_label",
    "사용목적": "purpose",
    "활용유형": "usage_type",
    "업체": "company",
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
    "담당자": "created_by",
}


DEFAULT_COLS = ["장비", "시작일", "종료일", "업체", "사용료", "사용목적", "활용유형", "사용시간", "시료수", "담당자",
                "세부지원내용", "수정자"]


def _fee_log(v) -> list[dict]:
    try:
        rows = json.loads(db.to_str(v) or "[]")
        return rows if isinstance(rows, list) else []
    except ValueError:
        return []


def _payments(df: pd.DataFrame, label_of: dict) -> None:
    """수수료를 나눠 받거나 늦게 받은 시험: 받은 날 · 금액을 여러 번 적으면 합계가 사용료(수수료)로 들어감."""
    paid = df[df["company"].fillna("") != ""]
    if paid.empty:
        return
    with st.expander("나눠 받거나 늦게 받은 수수료 적기", icon=":material/payments:"):
        opts = {int(r["id"]): f"{r['start_date']:%m/%d} {label_of.get(r['equip_id'], '?')} · {r['company']}"
                + (f" · {r['fee']:,.0f}원" if r["fee"] else "") for r in paid.to_dict("records")}
        lid = st.selectbox("시험", list(opts), format_func=opts.get, index=None, placeholder="시험 고르기",
                           key="fee_pick")
        if lid is None:
            return
        row = paid[paid["id"] == lid].iloc[0]
        rows = _fee_log(row.get("fee_log"))
        if not rows and row["fee"]:
            rows = [{"date": "", "amount": int(row["fee"]), "memo": "이전에 넣은 금액"}]
        base = pd.DataFrame(rows, columns=["date", "amount", "memo"])
        base["date"] = pd.to_datetime(base["date"], errors="coerce").dt.date
        base["amount"] = pd.to_numeric(base["amount"], errors="coerce")
        base["memo"] = base["memo"].astype("string")
        ed = st.data_editor(base, key=f"fee_rows_{lid}", num_rows="dynamic", hide_index=True, width="stretch",
                            column_config={
                                "date": st.column_config.DateColumn("받은 날", format="YYYY-MM-DD",
                                                                    default=dt.date.today()),
                                "amount": st.column_config.NumberColumn("금액(원)", min_value=0, step=10000,
                                                                        format="localized"),
                                "memo": st.column_config.TextColumn("메모", width="large")})
        ed = ed[ed["amount"].fillna(0) > 0]
        total = int(ed["amount"].sum())
        c1, c2 = st.columns([1, 2], vertical_alignment="center")
        c2.caption(f"합계 {total:,}원 · 저장하면 이 시험의 수수료가 합계로 바뀌고, 실적 내려받기에 그대로 들어가요.")
        if c1.button("받은 내역 저장", type="primary", key=f"fee_save_{lid}", width="stretch"):
            log = [{"date": d.isoformat() if pd.notna(d) and d else "", "amount": int(a), "memo": db.to_str(m)}
                   for d, a, m in zip(ed["date"], ed["amount"], ed["memo"])]
            with db.undo_group("수수료 받은 내역 저장"):
                db.update_logs({lid: {"fee": total, "fee_log": json.dumps(log, ensure_ascii=False)}})
            st.session_state.records_saved = f"수수료 {total:,}원을 저장했어요."
            st.session_state.pop(f"fee_rows_{lid}", None)
            st.rerun()


def render() -> None:
    page_header("수수료 입력", "실적")
    saved = st.session_state.pop("records_saved", None)
    if saved:
        st.toast(saved, icon=":material/check_circle:")

    logs = db.load_logs()
    eq = db.load_equipment()
    comp = db.load_companies()
    master = {r["name"]: r for r in comp.to_dict("records")}
    label_of = dict(zip(eq["id"], eq["label"]))
    id_of = dict(zip(eq["label"], eq["id"]))

    q_s, q_e, _ = period_bounds("분기", dt.date.today())
    pre = st.session_state.pop("records_prefilter", None)
    if pre:  # 대시보드·장비 상세에서 눌러 들어온 경우 그 조건으로 채움
        if pre.get("start") and pre.get("end"):
            st.session_state.rec_range = (pre["start"], pre["end"])
        st.session_state.rec_eq = [pre["equip"]] if pre.get("equip") in set(eq["label"]) else []
        st.session_state.rec_comp = pre.get("company") or ""
        st.session_state.rec_writer = "전체"
    st.session_state.setdefault("rec_range", (q_s, q_e))
    c1, c2, c3, c4 = st.container(border=True).columns([1.4, 2, 1.2, 1])
    rng = c1.date_input("사용시작일 범위", format="YYYY-MM-DD", help="기본값은 이번 분기입니다.", key="rec_range")
    sel_eq = c2.multiselect("장비", list(eq["label"]), placeholder="전체", key="rec_eq")
    comp_q = c3.text_input("업체", placeholder="검색", key="rec_comp")
    writers = sorted(w for w in logs["created_by"].unique() if w)
    writer = c4.selectbox("담당자", ["전체"] + writers, key="rec_writer")
    no_fee = st.toggle("수수료 안 넣은 것만", key="rec_nofee", help="수수료가 0원인 업체 실적만 보여 줍니다.")

    df = logs.copy()
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        df = df[(df["start_date"] >= pd.Timestamp(rng[0])) & (df["start_date"] <= pd.Timestamp(rng[1]))]
    if sel_eq:
        df = df[df["equip_id"].isin([id_of[x] for x in sel_eq])]
    if comp_q:
        df = df[df["company"].str.contains(comp_q, case=False, regex=False)]
    if writer != "전체":
        df = df[df["created_by"] == writer]
    if no_fee:
        df = df[(df["fee"].fillna(0) <= 0) & (df["company"].fillna("") != "")]

    m1, m2, m3 = st.columns(3)
    m1.metric("건수", f"{len(df):,}")
    m2.metric("사용시간 합계", f"{df['hours'].sum():,.0f} h")
    m3.metric("수수료 합계", f"{df['fee'].sum():,.0f} 원")

    if df.empty:
        empty_state("조건에 맞는 실적이 없습니다", icon="⌕")
        return

    _payments(df, label_of)

    view = df.copy()
    view["equip_label"] = view["equip_id"].map(label_of)
    view["start_date"] = view["start_date"].dt.date
    view["end_date"] = view["end_date"].dt.date
    view = view.set_index("id")[list(FIELDS.values())].rename(columns={v: k for k, v in FIELDS.items()})
    view["수정자"] = df.set_index("id")["updated_by"] if "updated_by" in df else ""
    view.insert(0, "복제", False)
    view.insert(0, "삭제", False)
    all_cols = list(FIELDS) + ["수정자"]
    st.session_state.setdefault("rec_cols", DEFAULT_COLS)
    t2, t1 = st.columns([1.2, 5], vertical_alignment="center")
    t1.caption("칸을 눌러 바로 고치고 '변경 내용 저장'. 지울 행은 '삭제', 다른 날로 복사할 행은 '복제'에 체크하세요.")
    with t2.popover("보이는 열", icon=":material/view_column:", width="stretch"):
        shown = st.multiselect("보이는 열", all_cols, key="rec_cols", label_visibility="collapsed")
        st.button("기본값으로", key="rec_cols_reset", type="tertiary",
                  on_click=lambda: st.session_state.update(rec_cols=DEFAULT_COLS))
    shown = shown or DEFAULT_COLS

    ed_key = f"records_editor_{abs(hash((str(rng), tuple(sel_eq), comp_q, writer, no_fee))) % 10 ** 8}"
    view, _ = pin_table(ed_key, view)  # 고치는 중에 다른 분이 저장해도 칸이 엉뚱한 줄로 가지 않게 (저장은 ID로)
    edited = st.data_editor(
        view, key=ed_key, hide_index=True, width="stretch", height=520,
        disabled=["사업자번호", "수정자"],
        column_order=["삭제", "복제"] + list(dict.fromkeys(c for c in DEFAULT_COLS + all_cols if c in shown)),
        column_config={
            "복제": st.column_config.CheckboxColumn(width="small", help="체크한 행을 아래에서 고른 날짜로 복사합니다."),
            "수정자": st.column_config.TextColumn("마지막 수정", help="이 실적을 마지막으로 고친 사람"),
            "담당자": st.column_config.SelectboxColumn(options=db.staff_names(list(df["created_by"])), required=True),
            "삭제": st.column_config.CheckboxColumn(width="small"),
            "장비": st.column_config.SelectboxColumn(options=list(eq["label"]), width="large", required=True),
            "사용목적": st.column_config.SelectboxColumn(options=seed.PURPOSES, required=True),
            "활용유형": st.column_config.SelectboxColumn(options=seed.USAGE_TYPES, required=True),
            "업체": st.column_config.SelectboxColumn(
                options=list(master) + sorted({c for c in view["업체"] if c and c not in master}),
                help="'기준 정보 › 업체'에 등록된 업체만 고를 수 있습니다. 사업자번호는 업체 목록에서 자동으로 채워집니다."),
            "사업자번호": st.column_config.TextColumn(help="'기준 정보 › 업체'에서 고칩니다."),
            "업종": st.column_config.SelectboxColumn(options=seed.INDUSTRIES),
            "품목": st.column_config.SelectboxColumn(options=seed.ALL_ITEMS),
            "세부품목": st.column_config.SelectboxColumn(options=seed.ALL_SUBITEMS),
            "공개": st.column_config.SelectboxColumn(options=seed.YN, width="small"),
            "휴무포함": st.column_config.SelectboxColumn(options=seed.YN, width="small"),
            "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
            "종료일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
            "사용시간": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True),
            "사용료": st.column_config.NumberColumn("수수료(원)", min_value=0, step=1000, format="localized",
                                                help="시험이 끝난 뒤 매긴 수수료. 칸을 눌러 바로 입력하세요."),
            "시료수": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            "세부지원내용": st.column_config.TextColumn(width="large"),
        },
    )

    to_delete = [int(i) for i in edited.index[edited["삭제"].fillna(False).astype(bool)]]
    changed = []
    for i in edited.index:
        if i in to_delete:
            continue
        a = edited.loc[i].drop(["삭제", "복제"]).astype(str)
        b = view.loc[i].drop(["삭제", "복제"]).astype(str)
        if not a.equals(b):
            changed.append(i)

    confirm = True
    c1, c2 = st.columns([1, 3])
    if c1.button("변경 내용 저장", type="primary", disabled=not (changed or to_delete) or not confirm,
                 icon=":material/save:", width="stretch"):
        errors, updates = [], {}
        for i in changed:
            row = edited.loc[i]
            rec = {FIELDS[col]: row[col] for col in FIELDS if col != "장비"}
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
            with db.undo_group(f"수수료 입력 저장 (수정 {len(updates)} · 삭제 {len(to_delete)})"):
                n_up = db.update_logs(updates) if updates else 0
                n_del = db.delete_logs(to_delete)
            st.session_state.records_saved = f"수정 {n_up}건 · 삭제 {n_del}건 반영했습니다."
            st.session_state.pop(ed_key, None)
            unpin(ed_key)
            st.rerun()
    c2.caption(f"수정 {len(changed)}건 · 삭제 {len(to_delete)}건 저장 대기" if (changed or to_delete) else "")

    to_copy = [int(i) for i in edited.index[edited["복제"].fillna(False).astype(bool)]]
    if to_copy:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.3, 1.2, 2], vertical_alignment="bottom")
            new_start = c1.date_input("복제할 시작일", value=dt.date.today(), format="YYYY-MM-DD", key="rec_copy_day",
                                      help="기간 실적은 같은 길이를 유지해 이 날부터 시작하도록 복사합니다.")
            if c2.button(f"{len(to_copy)}건 복제", type="primary", icon=":material/content_copy:", width="stretch"):
                errors, recs = [], []
                for i in to_copy:
                    src = df[df["id"] == i].iloc[0].to_dict()
                    length = (src["end_date"] - src["start_date"]).days
                    rec = {k: src.get(k) for k in db.LOG_FIELDS}
                    rec.update(start_date=new_start, end_date=new_start + dt.timedelta(days=length),
                               created_by=st.session_state.get("me") or src.get("created_by"))
                    errs = rules.validate(rec)
                    errors += [f"[{label_of.get(src['equip_id'], '')}] {e}" for e in errs]
                    recs.append(rec)
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    with db.undo_group(f"실적 {len(recs)}건 복제 ({new_start:%m/%d})"):
                        n = db.insert_logs(recs)
                    st.session_state.records_saved = f"{n}건을 {new_start:%m/%d}로 복제했습니다."
                    st.session_state.pop("records_editor", None)
                    st.rerun()
            c3.caption("복제한 실적은 '실적 입력' 달력에서도 바로 보입니다.")
