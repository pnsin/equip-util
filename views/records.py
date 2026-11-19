import datetime as dt
import json

import pandas as pd
import streamlit as st

from core import db, report, rules, seed
from core.calc import period_bounds
from ui_style import empty_state, page_header
from views.common import pick_done, pick_table, pin_table, unpin

ID = "_id"

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
    "수수료": "fee",
    "사용목적(상세)": "purpose_detail",
    "기타": "etc",
    "담당자": "created_by",
}


DEFAULT_COLS = ["장비", "시작일", "종료일", "업체", "수수료", "사용목적", "활용유형", "사용시간", "시료수", "담당자",
                "세부지원내용", "수정자"]


def _fee_log(v) -> list[dict]:
    try:
        rows = json.loads(db.to_str(v) or "[]")
        return rows if isinstance(rows, list) else []
    except ValueError:
        return []


def render() -> None:
    page_header("수수료 입력", "실적")
    t1, t2 = st.tabs(["실적별 수수료", "재무팀 매출장"])
    with t2:
        _ledger()
    with t1:
        _by_logs()


def _ledger() -> None:
    """재무팀이 보내 주는 매출장 엑셀을 올리면 우리 팀(차세대전지팀·배터리산업팀) 줄만 담음. 겹치는 줄은 다시 안 넣음."""
    from core import fee_ledger as fl
    with st.popover("매출장 엑셀 올리기", icon=":material/upload:"):
        st.caption("재무팀이 보내 준 파일 그대로 올리세요. 우리 팀 줄만 담고, 이미 있는 줄은 다시 넣지 않아요 "
                   "(입금 내역이 바뀐 줄만 고쳐요).")
        up = st.file_uploader("매출장", type=["xlsx"], key="fl_up", label_visibility="collapsed")
        if up is not None and st.button("반영", type="primary", key="fl_go"):
            try:
                new = fl.read_file(up.getvalue())
                add, upd, same = fl.merge(new)
                n_comp = fl.add_companies(new)
                st.toast(f"새로 {add}건 · 입금 고침 {upd}건 · 이미 있음 {same}건"
                         + (f" · 새 업체 {n_comp}곳" if n_comp else ""), icon=":material/check_circle:")
            except ValueError as e:
                st.warning(str(e))
    df = fl.load()
    if df.empty:
        empty_state("아직 올린 매출장이 없어요", "재무팀 매출장 엑셀을 올려 주세요.", icon="⇪")
        return
    years = sorted({d.year for d in df["tax_date"] if d}, reverse=True)
    c1, c2 = st.columns([1, 3])
    yr = c1.selectbox("연도", ["전체"] + years, key="fl_year")
    q = c2.text_input("업체·발행내역", placeholder="검색", key="fl_q")
    if yr != "전체":
        df = df[df["tax_date"].map(lambda d: bool(d) and d.year == yr)]
    if q:
        hay = df["company"].astype(str) + " " + df["item"].astype(str)
        df = df[hay.str.contains(q, case=False, regex=False)]
    m1, m2, m3 = st.columns(3)
    m1.metric("건수", f"{len(df):,}")
    m2.metric("공급가 합계", f"{df['supply'].sum():,.0f} 원")
    m3.metric("미수금", f"{df['unpaid'].sum():,.0f} 원")
    heads = {"tax_date": "세금일자", "company": "업체명", "item": "발행내역", "report_cat": "보고 분류", "supply": "공급가",
             "total": "합계", "paid1_date": "입금일(1차)", "paid1": "입금(1차)", "paid2_date": "입금일(2차)",
             "paid2": "입금(2차)", "unpaid": "미수금", "staff": "담당자", "team": "팀명"}
    # 2026-11-19 보고 분류: 발행내역으로 자동으로 정하고, 틀린 줄만 여기서 바로 고침 (장비 종합 현황 02 수수료 표에 씀)
    view = df.assign(report_cat=report.ledger_cats(df))[["id"] + list(heads)].rename(columns=heads)
    view = view.reset_index(drop=True)
    ed = st.data_editor(view, key=f"fl_tbl_{yr}_{q}_{db.data_version()}", hide_index=True, width="stretch", column_order=list(heads.values()),
                        disabled=[c for c in view.columns if c != "보고 분류"],
                        column_config={"보고 분류": st.column_config.SelectboxColumn(
                                           options=report.CATS, required=True, width=120,
                                           help="장비 종합 현황 수수료 표의 분류. 바꾸면 바로 저장되고, 같은 업체·같은 발행내역 줄(다음에 올릴 매출장 포함)도 같이 바뀌어요."),
                                       **{h: st.column_config.NumberColumn(format="localized")
                                          for h in ("공급가", "합계", "입금(1차)", "입금(2차)", "미수금")}})
    changed = {int(i): c for i, c, o in zip(ed["id"], ed["보고 분류"], view["보고 분류"]) if c and c != o}
    if changed:
        fl.set_cats(changed)
        st.toast(f"보고 분류 {len(changed)}건을 바꿨어요.", icon=":material/check_circle:")
        st.rerun()


def _by_logs() -> None:
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
    comp_q = ""  # 대시보드에서 업체를 눌러 들어온 경우만 그 업체로 거름 (2026-11-10 업체 검색칸 없앰)
    if pre:  # 대시보드·장비 상세에서 눌러 들어온 경우 그 조건으로 채움
        if pre.get("start") and pre.get("end"):
            st.session_state.rec_range = (pre["start"], pre["end"])
        pe = id_of.get(pre.get("equip"))
        tid = int(eq.loc[eq["id"] == pe, "root_id"].iloc[0]) if pe is not None else None
        st.session_state.rec_eq = [dict(zip(eq["id"], eq["short"]))[tid]] if tid is not None else []
        comp_q = pre.get("company") or ""
        st.session_state.rec_writer = "전체"
    st.session_state.setdefault("rec_range", (q_s, q_e))
    tops = eq[eq["parent_id"].isna()] if "parent_id" in eq else eq  # 주장비만 고름 (세부장비 실적도 함께 나옴)
    top_of = dict(zip(tops["short"], tops["id"]))
    if any(x not in top_of for x in st.session_state.get("rec_eq", [])):
        st.session_state.rec_eq = [x for x in st.session_state.rec_eq if x in top_of]
    # 2026-11-17 거르기 줄: 상자·제목 없이 한 줄 (기간 · 장비 · 담당자)
    c1, c2, c4 = st.columns([1.5, 2.6, 1.2], gap="small", vertical_alignment="center")
    rng = c1.date_input("사용시작일 범위", format="YYYY-MM-DD", key="rec_range", label_visibility="collapsed")
    sel_eq = c2.multiselect("장비", list(top_of), placeholder="장비 전체", key="rec_eq", label_visibility="collapsed")
    writers = sorted(w for w in logs["created_by"].unique() if w)
    writer = c4.selectbox("담당자", ["전체"] + writers, key="rec_writer", label_visibility="collapsed",
                          format_func=lambda w: "담당자 전체" if w == "전체" else w)
    no_fee = False

    df = logs.copy()
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        df = df[(df["start_date"] >= pd.Timestamp(rng[0])) & (df["start_date"] <= pd.Timestamp(rng[1]))]
    if sel_eq:
        fam = db.descendants(eq)
        df = df[df["equip_id"].isin([k for x in sel_eq for k in fam.get(int(top_of[x]), [int(top_of[x])])])]
    if comp_q:
        df = df[df["company"].str.contains(comp_q, case=False, regex=False)]
    if writer != "전체":
        df = df[df["created_by"] == writer]
    if no_fee:
        df = df[(df["fee"].fillna(0) <= 0) & (df["company"].fillna("") != "")]

    if df.empty:
        empty_state("조건에 맞는 실적이 없습니다", icon="⌕")
        return



    view = df.copy()
    view["equip_label"] = view["equip_id"].map(label_of)
    view["start_date"] = view["start_date"].dt.date
    view["end_date"] = view["end_date"].dt.date
    view = view.set_index("id")[list(FIELDS.values())].rename(columns={v: k for k, v in FIELDS.items()})
    view["수정자"] = df.set_index("id")["updated_by"] if "updated_by" in df else ""
    view["사용목적"] = view["사용목적"].map(seed.purpose_label)  # 달력과 같은 이름 (제조·지원)
    view.insert(0, ID, view.index.astype("int64"))  # 저장·삭제·복제는 ID로 (화면엔 안 보임)
    view = view.reset_index(drop=True)
    order = DEFAULT_COLS  # 2026-11-17 보이는 열 고르기 없앰

    ed_key = f"records_tbl_{abs(hash((str(rng), tuple(sel_eq), comp_q, writer, no_fee))) % 10 ** 8}"
    view, _ = pin_table(ed_key, view)  # 고치는 중에 다른 분이 저장해도 칸이 엉뚱한 줄로 가지 않게 (저장은 ID로)

    def copy_day():
        st.date_input("복제할 시작일", value=dt.date.today(), format="YYYY-MM-DD", key="rec_copy_day", width=220,
                      help="'복제'를 누르면 고른 행을 이 날부터 시작하도록 복사합니다 (기간 실적은 같은 길이).")

    action, out, _ = pick_table(
        view, ed_key, name_col="장비", can_add=False, column_order=order,
        disabled=["사업자번호", "업종", "품목", "세부품목", "수정자"],
        extra_actions=[("copy", "복제", ":material/content_copy:")], extra_ui=copy_day,
        column_config={
            "수정자": st.column_config.TextColumn("마지막 수정", help="이 실적을 마지막으로 고친 사람"),
            "담당자": st.column_config.SelectboxColumn(options=db.staff_names(list(df["created_by"])), required=True),
            "장비": st.column_config.SelectboxColumn(options=list(eq["label"]), width="large", required=True),
            "사용목적": st.column_config.SelectboxColumn(options=list(dict.fromkeys(seed.purpose_label(p) for p in seed.PURPOSES)),
                                                     required=True),
            "활용유형": st.column_config.SelectboxColumn(options=seed.USAGE_TYPES, required=True),
            "업체": st.column_config.SelectboxColumn(
                options=list(master) + sorted({c for c in view["업체"] if c and c not in master}),
                help="'기준 정보 › 업체'에 등록된 업체만 고를 수 있습니다. 사업자번호는 업체 목록에서 자동으로 채워집니다."),
            "사업자번호": st.column_config.TextColumn(help="'기준 정보 › 업체'에서 고칩니다."),
            "업종": st.column_config.TextColumn(help="'기준 정보 › 업체 목록'에서 고칩니다."),
            "품목": st.column_config.TextColumn(help="'기준 정보 › 업체 목록'에서 고칩니다."),
            "세부품목": st.column_config.TextColumn(help="'기준 정보 › 업체 목록'에서 고칩니다."),
            "공개": st.column_config.SelectboxColumn(options=seed.YN, width="small"),
            "휴무포함": st.column_config.SelectboxColumn(options=seed.YN, width="small"),
            "시작일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
            "종료일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True),
            "사용시간": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True),
            "수수료": st.column_config.NumberColumn("수수료(원)", min_value=0, step=1000, format="localized",
                                                help="시험이 끝난 뒤 매긴 수수료."),
            "시료수": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
            "세부지원내용": st.column_config.TextColumn(width="large"),
        },
    )

    def done(msg):
        st.session_state.records_saved = msg
        pick_done(ed_key)
        unpin(ed_key)
        st.rerun()

    if action == "save":
        errors, updates = [], {}
        for i in range(len(view)):
            row = out.loc[i]
            if row.drop(ID).astype(str).equals(view.loc[i].drop(ID).astype(str)):
                continue
            rec = {FIELDS[col]: row[col] for col in FIELDS if col != "장비"}
            rec["equip_id"] = id_of.get(row["장비"])
            rec["purpose"] = {v: k for k, v in seed.PURPOSE_LABEL.items()}.get(rec.get("purpose"), rec.get("purpose"))
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
                updates[int(row[ID])] = rec
        for e in errors:
            st.error(e)
        if not errors:
            with db.undo_group(f"수수료 입력 저장 (수정 {len(updates)})"):
                n_up = db.update_logs(updates) if updates else 0
            done(f"{n_up}건을 고쳤습니다.")
    elif action == "delete":
        ids = [int(i) for i in set(view[ID]) - set(out[ID])]
        with db.undo_group(f"수수료 입력 삭제 ({len(ids)})"):
            n_del = db.delete_logs(ids)
        done(f"{n_del}건을 지웠습니다.")
    elif action == "copy":
        new_start = st.session_state.get("rec_copy_day") or dt.date.today()
        errors, recs = [], []
        for i in out[ID]:
            src = df[df["id"] == i].iloc[0].to_dict()
            length = (src["end_date"] - src["start_date"]).days
            rec = {k: src.get(k) for k in db.LOG_FIELDS}
            rec.update(start_date=new_start, end_date=new_start + dt.timedelta(days=length),
                       created_by=st.session_state.get("me") or src.get("created_by"))
            errs = rules.validate(rec)
            errors += [f"[{label_of.get(src['equip_id'], '')}] {e}" for e in errs]
            recs.append(rec)
        for e in errors:
            st.error(e)
        if not errors:
            with db.undo_group(f"실적 {len(recs)}건 복제 ({new_start:%m/%d})"):
                n = db.insert_logs(recs)
            done(f"{n}건을 {new_start:%m/%d}로 복제했습니다. '장비 일정 등록' 달력에서도 바로 보여요.")
