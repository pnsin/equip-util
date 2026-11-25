"""데이터 점검: 시트에 있는 실적이 화면·가동률·i-Tube 파일에서 빠지거나 틀어지는 경우를 모아 보여 줌 (2026-11-20)."""
import datetime as dt
import html

import streamlit as st

from core import db, health
from ui_style import page_header

CSS = """<style>
.hc-sum {display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin: .2rem 0 1rem;}
.hc-sum span {padding: 6px 14px; border-radius: 999px; font-size: .85rem; font-weight: 700;}
.hc-sum .s-chk {background: rgba(200,75,49,.14); color: #C84B31;}
.hc-sum .s-note {background: rgba(107,104,96,.14); color: #3A3833;}
.hc-sum .s-ok {background: rgba(74,107,93,.14); color: #4A6B5D;}
.hc-h {display: flex; align-items: center; justify-content: center; gap: 8px; margin: 1.1rem 0 .15rem; font-weight: 800; font-size: .98rem;}
.hc-h .lv {font-size: .72rem; padding: 2px 9px; border-radius: 999px;}
.hc-h .lv.chk {background: rgba(200,75,49,.16); color: #C84B31;}
.hc-h .lv.note {background: rgba(107,104,96,.16); color: #3A3833;}
.hc-h .n {color: #55514A; font-weight: 700; font-size: .85rem;}
.hc-why {text-align: center; color: #55514A; font-size: .82rem; margin-bottom: .45rem;}
</style>"""


@st.cache_data(show_spinner=False, max_entries=2)
def _run(ver: int) -> list[dict]:  # ver(데이터 번호)가 바뀌면 다시 셈 — 이름이 '_'로 시작하면 캐시 키에서 빠져 안 바뀜
    eq = db.load_equipment()
    ch = db.load_channels()
    from core import fee_ledger
    return health.run(db.load_logs(), eq, ch, db.load_companies(), db.charger_ids(eq, ch), ledger=fee_ledger.load())


def _split() -> tuple[list[dict], list[dict]]:
    return health.split_confirmed(_run(db.data_version()), db.get_settings().get("health_ok") or {})


def findings() -> list[dict]:
    """아직 볼 것만 ('확인'한 참고 실적은 빼고). 메뉴의 건수도 이것으로 셈."""
    return _split()[0]


def _ver() -> int:
    return st.session_state.get("hc_ver", 0)


def _done() -> None:
    st.session_state["hc_ver"] = _ver() + 1
    st.rerun()


def _brn_box(found: list[dict]) -> None:
    """업체별로 사업자등록번호를 바로 적는 칸. 저장하면 업체 목록에 들어가 그 업체 실적 전부에 적용."""
    need = health.brn_needed(found)
    if need.empty:
        return
    view = need.assign(사업자등록번호="")
    ed = st.data_editor(view, key=f"hc_brn_{_ver()}", hide_index=True, width="stretch", disabled=["업체", "실적"],
                        height=min(38 + 35 * len(view), 360),
                        column_config={"실적": st.column_config.NumberColumn("실적", format="%d건", width="small"),
                                       "사업자등록번호": st.column_config.TextColumn(
                                           "사업자등록번호", help="숫자 10자리 ('-'는 있어도 되고 없어도 돼요)")})
    typed = {r["업체"]: db.to_str(r["사업자등록번호"]) for r in ed.to_dict("records") if db.to_str(r["사업자등록번호"])}
    bad = [n for n, b in typed.items() if len(db.digits(b)) != 10 or db.digits(b) != b.replace("-", "").replace(" ", "")]
    if bad:
        st.error("사업자등록번호는 숫자 10자리예요: " + ", ".join(bad))
    with st.container(horizontal=True, horizontal_alignment="center"):
        if st.button(f"업체 목록에 저장 ({len(typed)})" if typed else "업체 목록에 저장", type="primary",
                     icon=":material/save:", key=f"hc_brn_go_{_ver()}", disabled=not typed or bool(bad)):
            db.set_company_brn(typed)
            _done()


def _confirm_box(f: dict) -> None:
    """참고 항목: 줄마다 '확인' 체크 → 목록에서 내림 (맨 아래 '확인한 실적'에 남음)."""
    rows = f["rows"].copy()
    rows["ID"] = rows["ID"].astype(str)
    rows = rows[[c for c in rows.columns if c != "ID"] + ["ID"]]
    rows.insert(0, "확인", False)
    ed = st.data_editor(rows, key=f"hc_ok_{f['key']}_{_ver()}", hide_index=True, width="stretch",
                        disabled=[c for c in rows.columns if c != "확인"], height=min(38 + 35 * len(rows), 360),
                        column_config={"확인": st.column_config.CheckboxColumn("확인", width=64, default=False),
                                       "시간": st.column_config.NumberColumn(format="%g")})
    picked = list(ed.loc[ed["확인"].fillna(False).astype(bool), "ID"])
    with st.container(horizontal=True, horizontal_alignment="center"):
        go = st.button(f"확인 ({len(picked)})" if picked else "확인", type="primary", icon=":material/check:",
                       key=f"hc_ok_go_{f['key']}_{_ver()}", disabled=not picked)
        go_all = st.button(f"모두 확인 ({len(rows)})", key=f"hc_ok_all_{f['key']}_{_ver()}")
    if go or go_all:
        _mark(f["key"], list(rows["ID"]) if go_all else picked, True)


def _mark(key: str, ids: list[str], on: bool) -> None:
    ok = {k: dict(v) for k, v in (db.get_settings().get("health_ok") or {}).items()}
    cur = ok.setdefault(key, {})
    stamp = " ".join(x for x in (dt.date.today().isoformat(), db.who()) if x)
    for i in ids:
        if on:
            cur[str(i)] = stamp
        else:
            cur.pop(str(i), None)
    db.save_settings(health_ok={k: v for k, v in ok.items() if v})
    _done()


def _confirmed(done: list[dict]) -> None:
    """확인해서 내린 참고 실적. 숨긴 채로 잊히지 않게 언제든 열어 보고 되돌릴 수 있음."""
    n = sum(len(f["rows"]) for f in done)
    if not n:
        return
    with st.expander(f"확인한 실적 {n:,}건", icon=":material/task_alt:"):
        for f in done:
            st.markdown(f"<div class='hc-h'>{html.escape(f['title'])}<span class='n'>{len(f['rows']):,}건</span></div>",
                        unsafe_allow_html=True)
            rows = f["rows"].copy()
            rows["ID"] = rows["ID"].astype(str)
            rows = rows.rename(columns={"확인": "확인한 날"})
            rows = rows[[c for c in rows.columns if c not in ("ID", "확인한 날")] + ["확인한 날", "ID"]]
            rows.insert(0, "되돌리기", False)
            ed = st.data_editor(rows, key=f"hc_undo_{f['key']}_{_ver()}", hide_index=True, width="stretch",
                                disabled=[c for c in rows.columns if c != "되돌리기"],
                                height=min(38 + 35 * len(rows), 360),
                                column_config={"되돌리기": st.column_config.CheckboxColumn("되돌리기", width=80, default=False),
                                               "시간": st.column_config.NumberColumn(format="%g")})
            picked = list(ed.loc[ed["되돌리기"].fillna(False).astype(bool), "ID"])
            if picked:
                with st.container(horizontal=True, horizontal_alignment="center"):
                    if st.button(f"목록으로 되돌리기 ({len(picked)})", icon=":material/undo:",
                                 key=f"hc_undo_go_{f['key']}_{_ver()}"):
                        _mark(f["key"], picked, False)


def render() -> None:
    page_header("데이터 점검", "관리")
    st.markdown(CSS, unsafe_allow_html=True)
    found, done = _split()
    n_chk, n_note = health.summary(found)
    if not found:
        st.markdown("<div class='hc-sum'><span class='s-ok'>문제 없음</span></div>", unsafe_allow_html=True)
        _confirmed(done)
        return
    st.markdown("<div class='hc-sum'>" + (f"<span class='s-chk'>확인 필요 {n_chk:,}건</span>" if n_chk else "")
                + (f"<span class='s-note'>참고 {n_note:,}건</span>" if n_note else "") + "</div>", unsafe_allow_html=True)
    e = html.escape
    for f in sorted(found, key=lambda f: f["level"] != health.CHECK):
        cls = "chk" if f["level"] == health.CHECK else "note"
        st.markdown(f"<div class='hc-h'><span class='lv {cls}'>{e(f['level'])}</span>{e(f['title'])}"
                    f"<span class='n'>{len(f['rows']):,}건</span></div><div class='hc-why'>{e(f['why'])}</div>",
                    unsafe_allow_html=True)
        if f["key"] == "ext_no_brn":
            _brn_box(found)
        if f["level"] == health.NOTE:
            _confirm_box(f)
            continue
        rows = f["rows"].copy()
        rows["ID"] = rows["ID"].astype(str)
        rows = rows[[c for c in rows.columns if c != "ID"] + ["ID"]]  # 휴대폰에서 장비가 먼저 보이게
        st.dataframe(rows, hide_index=True, width="stretch", height=min(38 + 35 * len(rows), 360),
                     column_config={"시간": st.column_config.NumberColumn(format="%g")})
    _confirmed(done)
