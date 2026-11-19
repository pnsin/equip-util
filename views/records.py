import datetime as dt
import json

import pandas as pd
import streamlit as st

from core import db, report, seed
from core.calc import period_bounds
from ui_style import empty_state, page_header

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
    c1, c2, c3 = st.columns([1, 1.2, 2.8])
    opts = ["전체"] + years  # 2026-11-19 사용자: 기본은 올해
    yr = c1.selectbox("연도", opts, key="fl_year",
                      index=opts.index(dt.date.today().year) if dt.date.today().year in opts else 0)
    if yr != "전체":
        df = df[df["tax_date"].map(lambda d: bool(d) and d.year == yr)]
    # 2026-11-19 사용자: 애매한 줄(기타)을 찾기 어려움 → 보고 분류로 골라 보기 (기타만 보고 바로 고침)
    df = df.assign(report_cat=report.ledger_cats(df)) if not df.empty else df
    cnt = df["report_cat"].value_counts().to_dict() if not df.empty else {}
    cat = c2.selectbox("보고 분류", ["전체"] + [c for c in [report.CHECK] + report.CATS if cnt.get(c)], key="fl_cat",
                       format_func=lambda c: c if c == "전체" else f"{'🔴 ' if c == report.CHECK else ''}{c} ({cnt.get(c, 0)}건)",
                       help="'확인 필요'를 고르면 자동으로 분류하지 못한 줄만 보여요. 표의 '보고 분류' 칸을 눌러 바로 고칠 수 있어요.")
    if cat != "전체":
        df = df[df["report_cat"] == cat]
    q = c3.text_input("업체·발행내역", placeholder="검색", key="fl_q")
    if q:
        hay = df["company"].astype(str) + " " + df["item"].astype(str)
        df = df[hay.str.contains(q, case=False, regex=False)]
    # 2026-11-19 사용자: 칸에 비해 글씨가 작음 → 크게, 칸마다 색
    cards = [("건수", f"{len(df):,}<small>건</small>", "#818CF8"),
             ("공급가 합계", f"{df['supply'].sum():,.0f}<small>원</small>", "#34D399"),
             ("미수금", f"{df['unpaid'].sum():,.0f}<small>원</small>", "#FBBF24" if df["unpaid"].sum() else "#94A3B8")]
    st.markdown(
        '<style>.flk{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:6px 0 14px}'
        '.flk>div{background:var(--panel,#1E293B);border:1px solid rgba(255,255,255,.08);border-radius:16px;'
        'padding:16px 12px;text-align:center;font-variant-numeric:tabular-nums}'
        '.flk .l{font-size:17px;font-weight:700;color:#E2E8F0;margin-bottom:6px}'
        '.flk .v{font-size:34px;font-weight:800;line-height:1.2}.flk .v small{font-size:20px;margin-left:4px;font-weight:700}'
        '@media(max-width:640px){.flk{grid-template-columns:1fr}.flk .v{font-size:28px}}</style>'
        '<div class="flk">' + "".join(
            f'<div style="border-top:3px solid {c}"><div class="l">{lab}</div><div class="v" style="color:{c}">{v}</div></div>'
            for lab, v, c in cards) + '</div>', unsafe_allow_html=True)
    RC = "보고 분류 ✎"  # 이 칸만 고칠 수 있음
    heads = {"tax_date": "세금일자", "company": "업체명", "item": "발행내역", "report_cat": RC, "supply": "공급가",
             "total": "합계", "paid1_date": "입금일(1차)", "paid1": "입금(1차)", "paid2_date": "입금일(2차)",
             "paid2": "입금(2차)", "unpaid": "미수금", "staff": "담당자", "team": "팀명"}
    # 2026-11-19 보고 분류: 발행내역으로 자동으로 정하고, 틀린 줄만 여기서 바로 고침 (장비 KPI 현황 02 수수료 표에 씀)
    view = df[["id"] + list(heads)].rename(columns=heads)
    # 2026-11-19 사용자: '확인 필요' 줄은 맨 위로, 빨간 글씨로 (기타와 헷갈리지 않게)
    view = view.assign(_k=(view[RC] != report.CHECK)).sort_values("_k", kind="stable").drop(columns="_k")
    view = view.reset_index(drop=True)
    MARK = "🔴 " + report.CHECK  # 표 칸은 글자색을 못 바꿔서 빨간 점으로 표시
    view[RC] = view[RC].replace({report.CHECK: MARK})
    ed = st.data_editor(view, key=f"fl_tbl_{yr}_{cat}_{q}_{db.data_version()}", hide_index=True, width="stretch", column_order=list(heads.values()),
                        disabled=[c for c in view.columns if c != RC],
                        column_config={RC: st.column_config.SelectboxColumn(
                                           options=[MARK] + report.CATS, required=True, width=120,
                                           help="장비 KPI 현황 수수료 표의 분류. 바꾸면 바로 저장되고, 같은 업체·같은 발행내역 줄(다음에 올릴 매출장 포함)도 같이 바뀌어요."),
                                       **{h: st.column_config.NumberColumn(format="localized")
                                          for h in ("공급가", "합계", "입금(1차)", "입금(2차)", "미수금")}})
    changed = {int(i): (report.CHECK if c == MARK else c) for i, c, o in zip(ed["id"], ed[RC], view[RC]) if c and c != o}
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

    # 2026-11-19 사용자: 여기서는 수수료만 넣음 → '선택' 없이 수수료(원) 칸을 바로 고치면 자동 저장
    ed_key = f"records_tbl_{abs(hash((str(rng), tuple(sel_eq), comp_q, writer))) % 10 ** 8}_{db.data_version()}"
    ed = st.data_editor(
        view, key=ed_key, hide_index=True, width="stretch", column_order=order,
        disabled=[c for c in view.columns if c != "수수료"],
        column_config={
            "수정자": st.column_config.TextColumn("마지막 수정", help="이 실적을 마지막으로 고친 사람"),
            "장비": st.column_config.TextColumn(width="large"),
            "시작일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "종료일": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "사용시간": st.column_config.NumberColumn(format="%d"),
            "수수료": st.column_config.NumberColumn(
                "수수료(원) ✎", min_value=0, step=1000, format="localized",
                help="칸을 두 번 눌러 금액을 넣고 Enter를 누르면 바로 저장돼요. 다른 내용은 '장비 사용 등록'에서 고칩니다."),
            "시료수": st.column_config.NumberColumn(format="%d"),
            "세부지원내용": st.column_config.TextColumn(width="large"),
        },
    )
    changed = {int(i): {"fee": int(round(float(n or 0)))}
               for i, n, o in zip(view[ID], ed["수수료"], view["수수료"])
               if (0 if pd.isna(n) else float(n)) != (0 if pd.isna(o) else float(o))}
    if changed:
        with db.undo_group(f"수수료 입력 ({len(changed)}건)"):
            n_up = db.update_logs(changed)
        st.session_state.records_saved = f"수수료 {n_up}건을 저장했어요."
        st.rerun()
