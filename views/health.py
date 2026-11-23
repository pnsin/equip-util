"""데이터 점검: 시트에 있는 실적이 화면·가동률·i-Tube 파일에서 빠지거나 틀어지는 경우를 모아 보여 줌 (2026-11-20)."""
import html

import streamlit as st

from core import db, health
from ui_style import page_header

CSS = """<style>
.hc-sum {display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin: .2rem 0 1rem;}
.hc-sum span {padding: 6px 14px; border-radius: 999px; font-size: .85rem; font-weight: 700;}
.hc-sum .s-chk {background: rgba(200,75,49,.14); color: #C84B31;}
.hc-sum .s-note {background: rgba(107,104,96,.14); color: #4A4741;}
.hc-sum .s-ok {background: rgba(74,107,93,.14); color: #4A6B5D;}
.hc-h {display: flex; align-items: center; justify-content: center; gap: 8px; margin: 1.1rem 0 .15rem; font-weight: 800; font-size: .98rem;}
.hc-h .lv {font-size: .72rem; padding: 2px 9px; border-radius: 999px;}
.hc-h .lv.chk {background: rgba(200,75,49,.16); color: #C84B31;}
.hc-h .lv.note {background: rgba(107,104,96,.16); color: #4A4741;}
.hc-h .n {color: #6B6860; font-weight: 700; font-size: .85rem;}
.hc-why {text-align: center; color: #6B6860; font-size: .82rem; margin-bottom: .45rem;}
</style>"""


@st.cache_data(show_spinner=False, max_entries=2)
def _run(_ver: int) -> list[dict]:
    eq = db.load_equipment()
    ch = db.load_channels()
    return health.run(db.load_logs(), eq, ch, db.load_companies(), db.charger_ids(eq, ch))


def findings() -> list[dict]:
    return _run(db.data_version())


def render() -> None:
    page_header("데이터 점검", "관리")
    st.markdown(CSS, unsafe_allow_html=True)
    found = findings()
    n_chk, n_note = health.summary(found)
    if not found:
        st.markdown("<div class='hc-sum'><span class='s-ok'>문제 없음</span></div>", unsafe_allow_html=True)
        return
    st.markdown("<div class='hc-sum'>" + (f"<span class='s-chk'>확인 필요 {n_chk:,}건</span>" if n_chk else "")
                + (f"<span class='s-note'>참고 {n_note:,}건</span>" if n_note else "") + "</div>", unsafe_allow_html=True)
    e = html.escape
    for f in sorted(found, key=lambda f: f["level"] != health.CHECK):
        cls = "chk" if f["level"] == health.CHECK else "note"
        st.markdown(f"<div class='hc-h'><span class='lv {cls}'>{e(f['level'])}</span>{e(f['title'])}"
                    f"<span class='n'>{len(f['rows']):,}건</span></div><div class='hc-why'>{e(f['why'])}</div>",
                    unsafe_allow_html=True)
        rows = f["rows"].copy()
        rows["ID"] = rows["ID"].astype(str)
        rows = rows[[c for c in rows.columns if c != "ID"] + ["ID"]]  # 휴대폰에서 장비가 먼저 보이게
        st.dataframe(rows, hide_index=True, width="stretch", height=min(38 + 35 * len(rows), 360),
                     column_config={"시간": st.column_config.NumberColumn(format="%g")})
