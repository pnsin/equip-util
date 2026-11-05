"""장비 정보 › CS활동: 업체 문의·방문·기술지원 같은 고객지원 활동을 카드나 표로 기록합니다.

- 카드: 누르면 오른쪽 입력 카드가 열려 고치기·복사·삭제.
- 표: 엑셀처럼 칸을 바로 고치고, 여러 줄 붙여넣기·행 추가·삭제 체크 후 한 번에 저장.
"""
import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import cs, db
from ui_style import empty_state, page_header
from views.common import new_company_dialog

E = html.escape
WD = "월화수목금토일"
PAGE = 30

CSS = """<style>
.cs-stats {display: flex; gap: 12px; flex-wrap: wrap; margin: .2rem 0 1rem;}
.cs-stat {background: #fff; border-radius: 16px; padding: 12px 18px 11px; min-width: 150px;
  box-shadow: 0 1px 3px rgba(17, 28, 46, .07);}
.cs-stat b {display: block; font-size: 1.6rem; font-weight: 800; line-height: 1.15; color: var(--ink);
  font-variant-numeric: tabular-nums;}
.cs-stat span {font-size: .78rem; color: var(--muted);}
.cs-stat em {font-style: normal; font-size: .72rem; font-weight: 700; color: #D45087; margin-left: 6px;}
.st-key-cs_tools {align-items: center; gap: .5rem; flex-wrap: wrap;}
.st-key-cs_tools [data-testid="stButtonGroup"] button {border-radius: 999px !important; height: 34px; min-height: 0;
  padding: 0 14px; background: #fff; border: 1px solid var(--line) !important;}
.st-key-cs_tools [data-testid="stButtonGroup"] button p {font-size: .84rem; font-weight: 600; color: #4A5670;}
.st-key-cs_tools [data-testid="stButtonGroup"] button[aria-checked="true"] {background: #26324A !important; border-color: #26324A !important;}
.st-key-cs_tools [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
.st-key-cs_tools .st-key-cs_q {flex: 1 1 200px; min-width: 180px;}
.st-key-cs_tools .st-key-cs_new button {background: var(--accent); color: #fff; border: none; border-radius: 12px;
  font-weight: 700; box-shadow: 0 3px 10px rgba(37, 99, 201, .25);}
.st-key-cs_tools .st-key-cs_new button p {color: #fff; font-weight: 700;}
/* 카드 */
.st-key-cs_list {gap: 9px !important;}
div[class*="st-key-cs_card_"] {position: relative; background: #fff; border-radius: 16px; padding: 12px 16px 12px 20px;
  box-shadow: 0 1px 3px rgba(17, 28, 46, .07); transition: box-shadow .12s, transform .12s;}
div[class*="st-key-cs_card_"]:hover {box-shadow: 0 6px 18px rgba(17, 28, 46, .10); transform: translateY(-1px);}
div[class*="st-key-cs_card_"]::before {content: ''; position: absolute; left: 0; top: 12px; bottom: 12px; width: 4px;
  border-radius: 4px; background: var(--kc, #8A97A8);}
div[class*="st-key-cs_card_"].sel, div[class*="st-key-cs_card_"]:has(.cs-sel) {box-shadow: inset 0 0 0 2px var(--accent), 0 6px 18px rgba(37, 99, 201, .12);}
div[class*="st-key-cs_card_"] [data-testid="stMarkdownContainer"] {margin: 0 !important;}
div[class*="st-key-cs_card_"] div[class*="st-key-cs_open_"] {position: absolute !important; inset: 0; z-index: 2; margin: 0;}
div[class*="st-key-cs_card_"] div[class*="st-key-cs_open_"] button {width: 100%; height: 100%; opacity: 0; cursor: pointer;}
.cs-c {display: flex; align-items: center; gap: 16px;}
.cs-d {width: 46px; text-align: center; color: var(--muted); font-size: .74rem; line-height: 1.2; flex: none;}
.cs-d b {display: block; font-size: 1.25rem; font-weight: 800; color: var(--ink); font-variant-numeric: tabular-nums;}
.cs-b {flex: 1; min-width: 0;}
.cs-t {font-weight: 700; font-size: .95rem; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.cs-m {font-size: .8rem; color: var(--muted); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.cs-tag {display: inline-block; font-size: .72rem; font-weight: 700; padding: 1px 9px; border-radius: 999px; margin-right: 7px;
  vertical-align: 1px;}
.cs-eq {display: inline-block; font-size: .72rem; padding: 0 8px; border-radius: 6px; background: #F3F5F8; color: #5A6474; margin-left: 5px;}
.cs-fu {color: var(--accent); font-weight: 600;} .cs-fu.late {color: #D45087;}
.cs-st {font-size: .76rem; font-weight: 700; padding: 4px 11px; border-radius: 999px; flex: none;}
.cs-who {width: 58px; text-align: right; font-size: .78rem; color: var(--muted); flex: none; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;}
.st-key-cs_more button {border: none; background: transparent; color: var(--accent); font-weight: 700;}
/* 입력 카드 */
.st-key-cs_wrap > [data-testid="stHorizontalBlock"] {align-items: flex-start !important;}
.st-key-cs_panel {position: sticky !important; top: 4.2rem; max-height: calc(100vh - 5.2rem); overflow-y: auto !important;
  scrollbar-width: thin; background: #fff; border-radius: 20px; padding: 16px 16px 14px; gap: .55rem;
  box-shadow: 0 2px 4px rgba(30, 50, 90, .04), 0 12px 32px rgba(30, 50, 90, .08); animation: csIn .18s ease-out;}
@keyframes csIn {from {opacity: 0; transform: translateX(10px);} to {opacity: 1; transform: none;}}
@media (max-width: 1300px) {
  .st-key-cs_wrap > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.st-key-cs_panel) {
    position: fixed !important; right: 16px; top: 4.2rem; width: 380px !important; flex: none !important; z-index: 900;}
  .st-key-cs_wrap > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:has(.st-key-cs_panel)) {
    width: 100% !important; flex: 1 1 100% !important;}
  .st-key-cs_panel {box-shadow: 0 18px 48px rgba(15, 30, 60, .25) !important;}
}
.st-key-cs_head {align-items: center !important;}
.cs-ph {font-size: 1.15rem; font-weight: 800; color: var(--ink);} .cs-ph em {font-style: normal; font-size: .85rem; color: #8592A8; margin-left: 4px;}
.st-key-cs_close {width: auto !important;}
.st-key-cs_close button {height: 36px; width: 36px; padding: 0; border-radius: 12px; border: none; background: #F4F6FA;}
.st-key-cs_panel [data-testid="stWidgetLabel"] {margin-bottom: 0; min-height: 0;}
.st-key-cs_panel [data-testid="stWidgetLabel"] p {font-size: .8rem; font-weight: 700; color: #5A6680;}
.st-key-cs_panel [data-baseweb="select"] > div, .st-key-cs_panel [data-baseweb="input"], .st-key-cs_panel [data-baseweb="textarea"] {
  background: #F4F6FA !important; border: 1.5px solid transparent !important; border-radius: 11px !important;}
.st-key-cs_panel [data-baseweb="input"] > div, .st-key-cs_panel [data-baseweb="input"] input,
.st-key-cs_panel [data-baseweb="textarea"] > div, .st-key-cs_panel textarea {background: transparent !important;}
.st-key-cs_panel [data-baseweb="select"] > div:focus-within, .st-key-cs_panel [data-baseweb="input"]:focus-within,
.st-key-cs_panel [data-baseweb="textarea"]:focus-within {border-color: var(--accent) !important; background: #fff !important;}
.st-key-cs_panel [data-testid="stButtonGroup"] button {border-radius: 999px !important; padding: 2px 12px; min-height: 0; height: 31px;
  border: none !important; background: #F4F6FA;}
.st-key-cs_panel [data-testid="stButtonGroup"] button p {font-size: .8rem; font-weight: 600; color: #4A5670;}
.st-key-cs_panel [data-testid="stButtonGroup"] button[aria-checked="true"] {background: var(--accent) !important;}
.st-key-cs_panel [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
.st-key-cs_newcomp {margin-top: -.5rem;}
.st-key-cs_newcomp button {min-height: 0; padding: 0; color: var(--accent);} .st-key-cs_newcomp button p {font-size: .76rem; font-weight: 700;}
.st-key-cs_btns {margin-top: .4rem;}
.st-key-cs_btns > div {width: auto !important;}
.st-key-cs_btns .st-key-cs_save {flex: 1 1 auto; width: auto !important;}
.st-key-cs_save button {height: 44px; border-radius: 13px; font-weight: 800; border: none; box-shadow: 0 4px 12px rgba(37, 99, 201, .25);}
.st-key-cs_copy button {height: 44px; border-radius: 13px; border: none; background: #F3F5F8; color: #4A5670;}
.st-key-cs_del button, .st-key-cs_delok button {height: 44px; border-radius: 13px; color: #E5484D; background: #FFF0F1; border: none;}
.cs-ask {font-size: .85rem; font-weight: 700; color: #C9372C; background: #FFF0F1; border-radius: 12px; padding: 10px 12px;}
</style>"""


def _kind_style(k: str) -> str:
    fg, bg = cs.KIND_COLOR.get(k, ("#5A6474", "#F3F5F8"))
    return f"color:{fg};background:{bg}"


def _status_style(s: str) -> str:
    fg, bg = cs.STATUS_COLOR.get(s, ("#5A6474", "#F3F5F8"))
    return f"color:{fg};background:{bg}"


def _stats(df: pd.DataFrame) -> None:
    s = cs.stats(df)
    late = f"<em>지난 일정 {s['overdue']}</em>" if s["overdue"] else ""
    tiles = [(s["month"], "이번 달 활동", "var(--ink)", ""), (s["open"], "진행 중", "#B5650B", ""),
             (s["follow"], "이번 주 후속 일정", "var(--accent)", late), (s["companies"], "이번 달 만난 업체", "var(--ink)", "")]
    st.markdown('<div class="cs-stats">' + "".join(
        f'<div class="cs-stat"><b style="color:{c}">{n}</b><span>{E(t)}</span>{x}</div>' for n, t, c, x in tiles)
        + "</div>", unsafe_allow_html=True)


def _open(rid: str) -> None:
    st.session_state.cs_open = rid
    st.session_state.pop("cs_delask", None)
    st.session_state.cs_ver = st.session_state.get("cs_ver", 0) + 1


def _close() -> None:
    st.session_state.pop("cs_open", None)
    st.session_state.pop("cs_prefill", None)
    st.session_state.pop("cs_delask", None)


def _new(prefill: dict | None = None) -> None:
    _open("new")
    if prefill:
        st.session_state.cs_prefill = prefill
    else:
        st.session_state.pop("cs_prefill", None)


def _filter(df: pd.DataFrame, kind: str, status: str, q: str, label_of: dict) -> pd.DataFrame:
    if kind and kind != "전체":
        df = df[df["kind"] == kind]
    if status == "진행 중":
        df = df[df["status"] != "완료"]
    elif status == "완료":
        df = df[df["status"] == "완료"]
    if q:
        hay = (df["title"] + " " + df["company"] + " " + df["contact"] + " " + df["staff"] + " " + df["content"]
               + " " + df["action"] + " " + df["equip_list"].map(lambda ids: " ".join(label_of.get(i, "") for i in ids)))
        df = df[hay.str.contains(q, case=False, regex=False)]
    return df


def _card(r: dict, label_of: dict, sel: bool) -> None:
    d = r["date"]
    day = f"<b>{d:%d}</b>{d.month}월" if pd.notna(d) else "<b>-</b>"
    fg, _ = cs.KIND_COLOR.get(r["kind"], ("#8A97A8", ""))
    meta = [E(x) for x in (r["company"], r["contact"]) if x]
    fu = r["follow_up"]
    if pd.notna(fu) and r["status"] != "완료":
        late = fu.date() < dt.date.today()
        meta.append(f'<span class="cs-fu{" late" if late else ""}">후속 {fu:%m/%d}</span>')
    elif r["action"]:
        meta.append(E(r["action"][:40]))
    eqs = "".join(f'<span class="cs-eq">{E(label_of[i])}</span>' for i in r["equip_list"][:3] if i in label_of)
    with st.container(key=f"cs_card_{r['id']}"):
        st.markdown(
            f'<div class="cs-c{" cs-sel" if sel else ""}" style="--kc:{fg}"><div class="cs-d">{day}</div><div class="cs-b">'
            f'<div class="cs-t"><span class="cs-tag" style="{_kind_style(r["kind"])}">{E(r["kind"])}</span>'
            f'{E(r["title"] or r["content"][:40] or "(제목 없음)")}</div>'
            f'<div class="cs-m">{" · ".join(meta) or "&nbsp;"}{eqs}</div></div>'
            f'<span class="cs-st" style="{_status_style(r["status"])}">{E(r["status"])}</span>'
            f'<div class="cs-who">{E(r["staff"])}</div></div>', unsafe_allow_html=True)
        st.button("열기", key=f"cs_open_{r['id']}", on_click=_open, args=(r["id"],))


def _cards(view: pd.DataFrame, label_of: dict) -> None:
    if view.empty:
        empty_state("아직 기록이 없어요", "오른쪽 위 '새 활동'으로 첫 기록을 남겨 보세요.", "🤝")
        return
    limit = st.session_state.get("cs_limit", PAGE)
    cur = st.session_state.get("cs_open")
    # 카드 왼쪽 색 막대 (유형별)
    st.markdown("<style>" + "".join(
        f'.st-key-cs_card_{r["id"]} {{--kc:{cs.KIND_COLOR.get(r["kind"], ("#8A97A8",))[0]};}}'
        for r in view.head(limit).to_dict("records")) + "</style>", unsafe_allow_html=True)
    with st.container(key="cs_list"):
        for r in view.head(limit).to_dict("records"):
            _card(r, label_of, r["id"] == cur)
    if len(view) > limit:
        st.button(f"더 보기 ({len(view) - limit}건 더)", key="cs_more",
                  on_click=lambda: st.session_state.update(cs_limit=limit + PAGE))


# ── 표 보기 (엑셀처럼) ─────────────────────────────────────────

TCOLS = {"date": "활동일", "kind": "유형", "title": "제목", "company": "업체", "contact": "업체 담당자", "staff": "TP담당자",
         "equip": "관련 장비", "content": "내용", "action": "조치·결과", "status": "상태", "follow_up": "후속 일정"}


def _table(view: pd.DataFrame, label_of: dict, id_of: dict, companies: list[str], staff: list[str]) -> None:
    t = pd.DataFrame({
        "삭제": False, "활동일": view["date"].dt.date, "유형": view["kind"], "제목": view["title"],
        "업체": view["company"], "업체 담당자": view["contact"], "TP담당자": view["staff"],
        "관련 장비": view["equip_list"].map(lambda ids: [label_of[i] for i in ids if i in label_of]),
        "내용": view["content"], "조치·결과": view["action"], "상태": view["status"],
        "후속 일정": view["follow_up"].dt.date,
    })
    t.insert(0, "_id", list(view["id"].astype(str)))
    t = t.reset_index(drop=True)
    t = t.astype({c: "string" for c in ("제목", "업체 담당자", "내용", "조치·결과")})
    comp_opts = companies + sorted({c for c in view["company"] if c and c not in companies})
    staff_opts = staff + sorted({s for s in view["staff"] if s and s not in staff})
    edited = st.data_editor(
        t, key="cs_editor", num_rows="dynamic", hide_index=True, width="stretch", column_order=[c for c in t.columns if c != "_id"],
        height=min(640, 40 + 35 * (len(t) + 2)),
        column_config={
            "삭제": st.column_config.CheckboxColumn(width="small", default=False, help="지울 행에 체크한 뒤 저장"),
            "활동일": st.column_config.DateColumn(format="YYYY-MM-DD", required=True, default=dt.date.today()),
            "유형": st.column_config.SelectboxColumn(options=cs.KINDS, required=True, default=cs.KINDS[0]),
            "제목": st.column_config.TextColumn(width="medium"),
            "업체": st.column_config.SelectboxColumn(options=comp_opts, width="medium"),
            "TP담당자": st.column_config.SelectboxColumn(options=staff_opts),
            "관련 장비": st.column_config.MultiselectColumn(options=list(id_of), width="medium"),
            "내용": st.column_config.TextColumn(width="large"),
            "조치·결과": st.column_config.TextColumn(width="medium"),
            "상태": st.column_config.SelectboxColumn(options=cs.STATUSES, required=True, default="접수", width="small"),
            "후속 일정": st.column_config.DateColumn(format="YYYY-MM-DD"),
        },
    )

    def rec(row) -> dict:
        return {"date": row["활동일"], "kind": row["유형"], "title": row["제목"], "company": row["업체"],
                "contact": row["업체 담당자"], "staff": row["TP담당자"],
                "equip_ids": [id_of[x] for x in (row["관련 장비"] or []) if x in id_of],
                "content": row["내용"], "action": row["조치·결과"], "status": row["상태"], "follow_up": row["후속 일정"]}

    def same(a, b) -> bool:
        def norm(v):
            if isinstance(v, (list, tuple)) or hasattr(v, "tolist"):
                return ",".join(map(str, list(v)))
            return db.to_str(v)
        return all(norm(a[c]) == norm(b[c]) for c in t.columns if c not in ("삭제", "_id"))

    orig = t.set_index("_id")
    known = set(orig.index)
    dels, ups, adds, kept = [], {}, [], set()
    for row in edited.to_dict("records"):  # 새 행은 _id 가 비어 있음
        rid = db.to_str(row.get("_id")) or None
        rid = rid if rid in known else None
        if rid:
            kept.add(rid)
        if bool(row.get("삭제")):
            if rid:
                dels.append(rid)
        elif rid:
            if not same(row, orig.loc[rid]):
                ups[rid] = rec(row)
        elif any(db.to_str(row.get(c)) for c in ("제목", "내용", "업체")):
            adds.append(rec(row))
    dels += [i for i in known if i not in kept]  # 행 머리에서 지운 행
    n = len(ups) + len(adds) + len(dels)
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    if c1.button("변경 내용 저장", type="primary", icon=":material/save:", disabled=not n, width="stretch", key="cs_tsave"):
        errors = [f"[{r['date'] or '날짜 없음'} {db.to_str(r['title'])[:12]}] {e}" for r in list(ups.values()) + adds
                  for e in cs.check(r)]
        if errors:
            for e in errors:
                st.error(e)
        else:
            with db.undo_group(f"CS활동 표 저장 (추가 {len(adds)} · 수정 {len(ups)} · 삭제 {len(dels)})"):
                cs.insert(adds)
                cs.update(ups)
                cs.delete(dels)
            st.session_state.pop("cs_editor", None)
            st.rerun()
    if n:
        c2.caption(f"추가 {len(adds)} · 수정 {len(ups)} · 삭제 {len(dels)} 저장 대기"
                   + (" · 지운 것은 '되돌리기'나 휴지통에서 살릴 수 있어요" if dels else ""))


# ── 입력 카드 ────────────────────────────────────────────────

def _panel(df: pd.DataFrame, label_of: dict, id_of: dict, companies: list[str], staff: list[str]) -> None:
    rid = st.session_state.get("cs_open")
    cur = None
    if rid != "new":
        hit = df[df["id"] == rid]
        if hit.empty:
            _close()
            st.rerun()
        cur = hit.iloc[0].to_dict()
    pre = cur or st.session_state.get("cs_prefill") or {}
    k = f"{rid}_{st.session_state.get('cs_ver', 0)}"
    d0 = pre.get("date")
    d0 = d0.date() if isinstance(d0, pd.Timestamp) and pd.notna(d0) else (d0 if isinstance(d0, dt.date) else dt.date.today())
    with st.container(key="cs_panel"):
        with st.container(key="cs_head", horizontal=True, vertical_alignment="center"):
            title = "새 활동" if cur is None else "활동 고치기"
            st.markdown(f'<div class="cs-ph">{title}</div>', unsafe_allow_html=True)
            st.space("stretch")
            st.button("", icon=":material/close:", key="cs_close", help="닫기", on_click=_close)
        v_date = st.date_input("활동일", value=d0, format="YYYY-MM-DD", key=f"cs_d_{k}")
        kind0 = pre.get("kind") if pre.get("kind") in cs.KINDS else cs.KINDS[0]
        v_kind = st.segmented_control("유형", cs.KINDS, default=kind0, key=f"cs_k_{k}") or kind0
        v_title = st.text_input("제목", pre.get("title", ""), placeholder="예: 충방전기 장기 시험 일정 문의", key=f"cs_t_{k}")
        comp0 = pre.get("company") or None
        opts = companies + ([comp0] if comp0 and comp0 not in companies else [])
        v_comp = st.selectbox("업체", opts, index=opts.index(comp0) if comp0 in opts else None,
                              placeholder="업체 이름을 입력해 찾기", key=f"cs_c_{k}")
        if st.button("새 업체 등록", icon=":material/add:", key="cs_newcomp", type="tertiary"):
            new_company_dialog()
        c1, c2 = st.columns(2)
        v_contact = c1.text_input("업체 담당자", pre.get("contact", ""), placeholder="예: 김OO 과장", key=f"cs_ct_{k}")
        staff0 = pre.get("staff") or st.session_state.get("me") or None
        sopts = staff + ([staff0] if staff0 and staff0 not in staff else [])
        v_staff = c2.selectbox("TP담당자", sopts, index=sopts.index(staff0) if staff0 in sopts else None,
                               placeholder="선택", key=f"cs_s_{k}")
        eq0 = [label_of[i] for i in (pre.get("equip_list") or []) if i in label_of]
        v_eq = st.multiselect("관련 장비", list(id_of), default=eq0, placeholder="여러 대 골라도 돼요", key=f"cs_e_{k}")
        v_content = st.text_area("내용", pre.get("content", ""), height=90, key=f"cs_m_{k}")
        v_action = st.text_area("조치 · 결과", pre.get("action", ""), height=68, key=f"cs_a_{k}")
        st0 = pre.get("status") if pre.get("status") in cs.STATUSES else "접수"
        v_status = st.segmented_control("상태", cs.STATUSES, default=st0, key=f"cs_st_{k}") or st0
        fu0 = pre.get("follow_up")
        fu0 = fu0.date() if isinstance(fu0, pd.Timestamp) and pd.notna(fu0) else None
        v_fu = st.date_input("후속 일정", value=fu0, format="YYYY-MM-DD", key=f"cs_f_{k}",
                             help="다시 연락하거나 결과를 알려 줄 날 (없으면 비워 두기)")

        rec = {"date": v_date, "kind": v_kind, "title": v_title, "company": v_comp or "", "contact": v_contact,
               "staff": v_staff or "", "equip_ids": [id_of[x] for x in v_eq], "content": v_content,
               "action": v_action, "status": v_status, "follow_up": v_fu}
        if st.session_state.get("cs_delask"):
            st.markdown('<div class="cs-ask">이 활동을 삭제할까요? 휴지통에서 다시 살릴 수 있어요.</div>',
                        unsafe_allow_html=True)
            with st.container(horizontal=True, gap="small", key="cs_btns"):
                if st.button("삭제", icon=":material/delete:", key="cs_delok", width="stretch"):
                    cs.delete([rid])
                    _close()
                    st.rerun()
                st.button("취소", key="cs_delno", width="stretch", on_click=lambda: st.session_state.pop("cs_delask", None))
            return
        with st.container(horizontal=True, gap="small", key="cs_btns"):
            save = st.button("저장" if cur is not None else "추가", icon=":material/check:", type="primary",
                             key="cs_save", width="stretch")
            if cur is not None:
                st.button("", icon=":material/content_copy:", key="cs_copy", help="이 내용으로 새 활동 만들기 (오늘 날짜)",
                          on_click=_new, args=({**cur, "date": dt.date.today(), "status": "접수", "follow_up": None},))
                st.button("", icon=":material/delete:", key="cs_del", help="삭제",
                          on_click=lambda: st.session_state.update(cs_delask=True))
        if save:
            errors = cs.check(rec)
            if errors:
                for e in errors:
                    st.error(e)
                return
            if cur is not None:
                cs.update({rid: rec})
            else:
                ids = cs.insert([rec])
                if ids:
                    st.session_state.pop("cs_prefill", None)
                    _open(ids[0])
            st.session_state.cs_ver = st.session_state.get("cs_ver", 0) + 1
            st.rerun()


def render() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    page_header("CS활동", "장비 정보")
    df = cs.load()
    eq = db.load_equipment()
    label_of = dict(zip(eq["id"].astype(int), eq["label"]))
    id_of = {v: k for k, v in label_of.items()}
    companies = list(db.load_companies()["name"])
    staff = db.staff_names()
    added = st.session_state.pop("company_added", None)
    if added and st.session_state.get("cs_open"):  # 새 업체 등록 후 바로 골라 둠
        st.session_state[f"cs_c_{st.session_state['cs_open']}_{st.session_state.get('cs_ver', 0)}"] = added

    _stats(df)
    with st.container(key="cs_tools", horizontal=True, vertical_alignment="center"):
        kind = st.segmented_control("유형", ["전체"] + cs.KINDS, default="전체", key="cs_kind",
                                    label_visibility="collapsed") or "전체"
        status = st.segmented_control("상태", ["진행 중", "완료"], key="cs_status", label_visibility="collapsed",
                                      help="한 번 더 누르면 모두 보기") or "전체"
        q = st.text_input("검색", placeholder="업체·장비·내용으로 찾기", key="cs_q", label_visibility="collapsed",
                          icon=":material/search:")
        mode = st.segmented_control("보기", ["카드", "표"], default="카드", key="cs_mode",
                                    label_visibility="collapsed") or "카드"
        view = _filter(df, kind, status, q.strip(), label_of)
        st.download_button("", cs.to_excel(view), file_name=f"CS활동_{dt.date.today():%y%m%d}.xlsx",
                           icon=":material/download:", key="cs_xlsx", help="보이는 목록을 엑셀로 내려받기",
                           disabled=view.empty)
        if mode == "카드":
            st.button("새 활동", icon=":material/add:", key="cs_new", on_click=_new)

    if mode == "표":
        _close()
        _table(view, label_of, id_of, companies, staff)
        return
    with st.container(key="cs_wrap"):
        if st.session_state.get("cs_open"):
            left, right = st.columns([2.5, 1.05], gap="medium")
            with left:
                _cards(view, label_of)
            with right:
                _panel(df, label_of, id_of, companies, staff)
        else:
            _cards(view, label_of)
