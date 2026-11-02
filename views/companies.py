"""업체(사용기관) 목록 관리. 실적을 입력할 때는 여기 등록된 업체 중에서만 고릅니다."""
import streamlit as st

from core import db, seed
from ui_style import note, page_header
from views.common import (confirm_delete, delete_config, filtered_editor, search_box, split_deleted,
                          with_delete_column)

COLS = {
    "id": "id", "name": "기업명", "brn": "사업자등록번호", "contact": "담당자", "phone": "연락처",
    "industry": "업종", "item": "품목", "sub_item": "세부품목", "note": "비고",
}


def render() -> None:
    page_header("업체 정보", "정보 입력",
                desc="실적을 입력할 때는 여기 등록된 업체만 고를 수 있습니다. 같은 회사가 다른 이름으로 집계되지 않게 한 곳에서 관리합니다.")
    msg = st.session_state.pop("company_saved", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")
        st.toast(msg, icon="✅")
    comp = db.load_companies()
    view = comp[list(COLS)].rename(columns=COLS)

    q = search_box("company_q", "🔍  기업명·사업자등록번호·담당자로 찾기")
    note(f"등록 업체 <b>{len(view)}곳</b> · 업종·품목·세부품목을 적어 두면 실적 입력 때 자동으로 채워집니다. "
         "사업자등록번호는 숫자 10자리로, '-'는 넣어도 되고 빼도 됩니다.")
    mask = None
    if q:
        mask = (view["기업명"].str.contains(q, case=False, regex=False)
                | view["사업자등록번호"].str.contains(db.digits(q) or q, regex=False)
                | view["담당자"].astype(str).str.contains(q, case=False, regex=False))

    edited, shown = filtered_editor(
        with_delete_column(view), mask, key=f"company_editor_{q}", num_rows="dynamic", hide_index=True,
        width="stretch", height=min(620, 38 + 35 * (len(view) + 2)),
        column_order=["삭제"] + [c for c in COLS.values() if c != "id"],
        column_config=delete_config() | {
            "기업명": st.column_config.TextColumn(required=True, width="medium"),
            "사업자등록번호": st.column_config.TextColumn(help="숫자 10자리 (- 는 넣어도 되고 빼도 됩니다)"),
            "업종": st.column_config.SelectboxColumn(options=seed.INDUSTRIES),
            "품목": st.column_config.SelectboxColumn(options=seed.ALL_ITEMS),
            "세부품목": st.column_config.SelectboxColumn(options=seed.ALL_SUBITEMS),
            "비고": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption((f"검색 결과 {shown}곳 (검색 중에도 바로 고칠 수 있습니다) · " if q else "")
               + "지울 행은 '삭제'에 체크하고, 맨 아래 빈 행에 입력하면 업체가 추가됩니다.")
    edited, deleted = split_deleted(edited, "기업명")
    ok = confirm_delete(deleted, "company_editor_del", "곳")
    if st.button("변경 내용 저장", type="primary", disabled=not ok, icon=":material/save:"):
        raw = edited.rename(columns={v: k for k, v in COLS.items()})
        errors = db.check_companies(raw)
        for e in errors:
            st.error(e)
        if not errors:
            db.save_companies(raw)
            st.session_state.company_saved = "업체 목록을 저장했습니다." + (f" ({len(deleted)}곳 삭제)" if deleted else "")
            st.session_state.pop(f"company_editor_{q}", None)
            st.session_state.pop("company_editor_del", None)
            st.rerun()
