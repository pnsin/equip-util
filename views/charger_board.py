"""실적 입력 › 충방전기: 챔버마다 누가 언제까지 쓰는지 한눈에 (입력은 달력 카드에서 한 번만)."""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd
import streamlit as st

from core import chargers, db
from ui_style import page_header
from views.calendar_entry import CATS, CHARGER_GROUP, PURPOSE_CAT

CSS = """<style>
.st-key-cb_top {align-items: center; margin-bottom: .4rem;}
.st-key-cb_center [data-testid="stButtonGroup"] {gap: 6px;}
.st-key-cb_center [data-testid="stButtonGroup"] button {border-radius: 999px !important; border: none !important;
  background: #fff !important; box-shadow: 0 1px 2px rgba(17, 28, 46, .08); padding: 0 16px !important;}
.st-key-cb_center [data-testid="stButtonGroup"] button p {font-weight: 700; color: var(--muted);}
.st-key-cb_center [data-testid="stButtonGroup"] button[aria-checked="true"] {background: #2A3147 !important;}
.st-key-cb_center [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: #fff !important;}
.cb-kpis {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 4px 0 14px;}
.cb-k {background: #fff; border-radius: 16px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(17, 28, 46, .08);
  display: flex; gap: 12px; align-items: center;}
.cb-k i {width: 38px; height: 38px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  font-style: normal; font-size: 19px; flex: none;}
.cb-k b {display: block; font-size: 1.25rem; color: var(--ink); line-height: 1.25;}
.cb-k span {font-size: .76rem; color: var(--muted);}
.cb-box {background: #fff; border-radius: 20px; box-shadow: 0 1px 3px rgba(17, 28, 46, .08); padding: 6px 0 8px; overflow-x: auto;}
.cb-t {border-collapse: collapse; width: 100%; font-size: .8rem; min-width: 860px;}
.cb-t th {font-size: .72rem; color: #97A1AE; font-weight: 600; text-align: left; padding: 8px 8px; border-bottom: 1px solid #E1E5EB;
  white-space: nowrap;}
.cb-t td {padding: 0 8px; height: 31px; border-bottom: 1px solid #F0F2F5; white-space: nowrap;}
.cb-t td.u {font-weight: 700; color: var(--ink);}
.cb-t td.c {color: var(--muted);}
.cb-t td.m {color: #97A1AE;}
.cb-dash {color: #97A1AE;}
.cb-t td.co {font-weight: 700; color: var(--ink);}
.cb-t td.tl {position: relative; width: 48%; padding: 0;}
.cb-t tr.grp td {border-top: 1px solid #E8ECF1;}
.cb-tl {position: relative; height: 31px;}
.cb-mh {position: relative; height: 16px;}
.cb-mh span {position: absolute; top: 0; font-size: .7rem; color: #97A1AE; font-weight: 600; padding-left: 5px;
  border-left: 1px solid #E8ECF1;}
.cb-g {position: absolute; top: 0; bottom: 0; width: 1px; background: #F0F2F5;}
.cb-now {position: absolute; top: -2px; bottom: -2px; width: 2px; background: #E35D78; border-radius: 2px; z-index: 2;}
.cb-bar {position: absolute; top: 5px; height: 21px; border-radius: 8px; font-size: .7rem; font-weight: 700; padding: 0 8px;
  display: flex; align-items: center; overflow: hidden; white-space: nowrap; border-left: 4px solid var(--fg);
  background: var(--bg); color: var(--fg); z-index: 1;}
.cb-bar.soon {border: 1.5px dashed #E8B04B; background: #FFF8EA; color: #B5650B;}
.cb-mini {display: inline-block; width: 34px; height: 6px; border-radius: 3px; background: #E6F6EE; margin: 0 5px 1px 8px;
  vertical-align: middle; overflow: hidden;}
.cb-mini i {display: block; height: 100%; background: #E35D78; border-radius: 3px;}
.cb-n {font-size: .7rem; font-weight: 700; color: #B8435C;}
.cb-free {position: absolute; top: 8px; left: 6px; font-size: .72rem; font-weight: 700; color: #1E8E5A;}
.cb-sum td {background: #F7F9FC; font-weight: 700; color: var(--muted);}
.cb-foot {display: flex; flex-wrap: wrap; gap: 14px; font-size: .74rem; color: var(--muted); margin-top: 8px;}
.cb-foot i {display: inline-block; width: 11px; height: 11px; border-radius: 4px; margin-right: 5px; vertical-align: -1px;}
@media (max-width: 900px) {.cb-kpis {grid-template-columns: repeat(2, minmax(0, 1fr));}}
</style>"""


DASH = "<span class='cb-dash'>—</span>"


def _book_new() -> None:
    """'충방전기 예약': 달력 화면에서 오늘 입력 카드를 '시험(충방전기)' 장비로 엶."""
    st.session_state.cb_go_input = True
    st.session_state.cal_open = True
    st.session_state.cal_lane = CHARGER_GROUP
    st.session_state.pop("cal_pick", None)
    st.session_state.cal_day = dt.date.today()
    st.session_state.cal_month = dt.date.today().replace(day=1)


def _edit(b: dict) -> None:
    """현황판에서 고른 예약을 달력 입력 카드로 열어 고침 (기간·챔버·업체 등)."""
    d = b["start"]
    st.session_state.cb_go_input = True
    st.session_state.cal_open = True
    st.session_state.pop("cal_lane", None)
    st.session_state.cal_day = d
    st.session_state.cal_month = d.replace(day=1)
    st.session_state.cal_pick = {"day": d, "id": int(b["log_ids"][0]), "rec": {}, "period": True,
                                 "label": b["company"]}


def _bar(b: dict, w0: dt.date, w1: dt.date, soon: bool, lane: int = 0) -> str:
    span = (w1 - w0).days + 1
    a, z = max(b["start"], w0), min(b["end"], w1)
    if z < a:
        return ""
    left = (a - w0).days / span * 100
    width = max(((z - a).days + 1) / span * 100, 1.2)
    bg, fg = CATS.get(PURPOSE_CAT.get(b["purpose"], "시험"), CATS["시험"])
    text = " · ".join(x for x in (b["company"], b["overview"], b["ch_part"] and f"ch {b['ch_part']}") if x)
    tip = f"{b['company']} · {b['start']:%Y-%m-%d} ~ {b['end']:%Y-%m-%d}" + (f" · {b['staff']}" if b["staff"] else "")
    return (f"<div class='cb-bar{' soon' if soon else ''}' title='{html.escape(tip)}' "
            f"style='left:{left:.2f}%;width:{width:.2f}%;top:{5 + lane * 26}px;--bg:{bg};--fg:{fg}'>{html.escape(text)}</div>")


def render() -> None:
    from views import common
    if st.session_state.pop("cb_go_input", False) and "input" in common.PAGES:
        st.switch_page(common.PAGES["input"])  # 예약·고치기는 실적 입력 달력 카드에서
    page_header("충방전기 현황", "현황")
    st.markdown(CSS, unsafe_allow_html=True)
    ch = db.load_channels()
    logs = db.load_logs()
    eq = db.load_equipment()
    today = dt.date.today()

    centers = list(dict.fromkeys(c for c in ch["center"] if c)) if not ch.empty else []
    bk = chargers.bookings(logs)
    stt = chargers.status(ch, bk, today) if not ch.empty else ch
    with st.container(key="cb_top", horizontal=True, gap="small", vertical_alignment="center"):
        center = None
        if centers:
            order = [k for k in db.CENTER_SHORT if k in centers] + [c for c in centers if c not in db.CENTER_SHORT]
            center = st.segmented_control("건물", ["전체"] + order, default="전체", key="cb_center",
                                          format_func=lambda c: db.CENTER_SHORT.get(c, c),
                                          label_visibility="collapsed") or "전체"
        st.space("stretch")
        if centers:
            st.download_button("현황표 엑셀로", chargers.to_excel(stt, today), icon=":material/download:",
                               file_name=f"충방전기_현황표_{today:%y%m%d}.xlsx", key="cb_dl",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.button("충방전기 예약", icon=":material/add:", key="cb_new", on_click=_book_new, type="primary")

    if not centers:
        st.info("챔버 구성이 아직 없어요. 아래 '챔버 구성 고치기'에서 건물 · 장비명 · 싸이클러 · 챔버 · 채널을 넣어 주세요.")
    else:
        g = stt if center == "전체" else stt[stt["center"] == center]
        total = int(g["ch_count"].sum())
        used = int(g["used"].sum())
        free_ch = [c for c, b in zip(g["chamber"], g["now"]) if not b]
        ending = sum(1 for b in g["now"] if b and b["end"] <= today + dt.timedelta(days=7))
        waiting = sum(1 for n, b in zip(g["now"], g["next"]) if not n and b)
        pct = f" · {used / total:.0%}" if total else ""
        st.markdown(
            "<div class='cb-kpis'>"
            f"<div class='cb-k'><i style='background:#EEF0FF'>🔋</i><div><b>{total} ch</b><span>전체 채널</span></div></div>"
            f"<div class='cb-k'><i style='background:#FDEEF1'>⚡</i><div><b>{used} ch{pct}</b><span>오늘 사용 중</span></div></div>"
            f"<div class='cb-k'><i style='background:#E6F6EE'>🌱</i><div><b>{total - used} ch</b>"
            f"<span>오늘 비어 있음 · 챔버 {len(free_ch)}개</span></div></div>"
            f"<div class='cb-k'><i style='background:#FFF8EA'>⏳</i><div><b>{ending}건</b>"
            f"<span>7일 안에 끝남 · 예약 {waiting}건</span></div></div></div>", unsafe_allow_html=True)

        # 타임라인: 지난달 1일 ~ 5개월 뒤
        w0 = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        m, w1 = w0, w0
        months = []
        for _ in range(6):
            months.append(m)
            m = (m + dt.timedelta(days=32)).replace(day=1)
        w1 = m - dt.timedelta(days=1)
        span = (w1 - w0).days + 1
        pos = lambda d: (d - w0).days / span * 100  # noqa: E731
        grid = "".join(f"<div class='cb-g' style='left:{pos(x):.2f}%'></div>" for x in months[1:])
        now_line = f"<div class='cb-now' style='left:{pos(today):.2f}%'></div>"
        mh = "".join(f"<span style='left:{pos(x):.2f}%'>{x.month}월</span>" for x in months)
        rows, prev_u, prev_c = [], None, None
        all_bk = {cid: b for cid, b in bk.groupby("chamber_id")} if not bk.empty else {}
        for r in g.to_dict("records"):
            b = r["now"] or r["next"]
            new_u = r["unit"] != prev_u
            u = html.escape(r["unit"]) if new_u else ""
            c = html.escape(r["cycler"]) if (new_u or r["cycler"] != prev_c) else ""
            prev_u, prev_c = r["unit"], r["cycler"]
            bars, lanes = "", []  # 기간이 겹치는 예약(채널 일부씩)은 줄을 나눠 그림
            for bb in sorted(all_bk.get(int(r["id"]), pd.DataFrame()).to_dict("records"), key=lambda x: x["start"]):
                ln = next((j for j, e in enumerate(lanes) if e < bb["start"]), len(lanes))
                lanes[ln:ln + 1] = [bb["end"]]
                bars += _bar(bb, w0, w1, soon=bb["start"] > today, lane=ln)
            if not bars:
                bars = "<div class='cb-free'>비어 있음</div>"
            h = 31 + 26 * max(len(lanes) - 1, 0)
            cos = list(dict.fromkeys(x["company"] for x in r["nows"])) or ([b["company"]] if b else [])
            who = (f"<td class='co'>{html.escape(cos[0])}" + (f" <span class='m'>외 {len(cos) - 1}</span>" if len(cos) > 1 else "")
                   + "</td>" if cos else "<td class='m'>—</td>")
            n_all = int(r["ch_count"]) or len(chargers.chamber_chs(r["channels"], 0))
            mini = (f"<span class='cb-mini' title='오늘 {r['used']}/{n_all}ch 사용'><i style='width:{r['used'] / n_all * 100:.0f}%'></i></span>"
                    f"<span class='cb-n'>{r['used']}/{n_all}</span>") if r["used"] and n_all and r["used"] < n_all else ""
            when = chargers.span_text(b["start"], b["end"], today) + ("" if r["now"] else " 예약") if b else ""
            rows.append(f"<tr class='{'grp' if new_u and rows else ''}'><td class='u'>{u}</td><td class='c'>{c}</td>"
                        f"<td>{html.escape(r['chamber']) or DASH}</td><td class='m'>{html.escape(r['channels'])}{mini}</td>{who}"
                        f"<td class='m'>{html.escape(when)}</td>"
                        f"<td class='tl'><div class='cb-tl' style='height:{h}px'>{grid}{now_line}{bars}</div></td></tr>")
        rows.append(f"<tr class='cb-sum'><td colspan='3'>{html.escape(db.CENTER_SHORT.get(center, center))} 합계</td><td>{total} ch</td>"
                    f"<td colspan='3'>사용 중 {used} · 비어 있음 {total - used}</td></tr>")
        st.markdown(
            "<div class='cb-box'><table class='cb-t'><tr><th>장비</th><th>싸이클러</th><th>챔버</th><th>채널</th>"
            f"<th>업체</th><th>기간</th><th class='tl'><div class='cb-mh'>{mh}</div></th></tr>"
            + "".join(rows) + "</table></div>"
            "<div class='cb-foot'>"
            + "".join(f"<span><i style='background:{CATS[k][1]}'></i>{k}</span>" for k in ("시험", "제조", "분석", "지원"))
            + "<span><i style='border:1.5px dashed #E8B04B;background:#FFF8EA'></i>아직 시작 전 (예약)</span>"
            "<span style='color:#E35D78'>│ 오늘</span></div>", unsafe_allow_html=True)

        mine = bk[bk["chamber_id"].isin(set(g["id"].astype(int)))] if not bk.empty else bk
        if not mine.empty:
            name_of = dict(zip(g["id"].astype(int), g["chamber"]))
            uniq = mine.sort_values("start").drop_duplicates("key")
            opts = uniq.to_dict("records")
            with st.container(key="cb_edit", horizontal=True, gap="small", vertical_alignment="center"):
                pick = st.selectbox(
                    "예약 고치기", range(len(opts)), index=None, placeholder="고칠 예약 고르기 (기간 · 챔버 · 업체)",
                    label_visibility="collapsed", key="cb_pick", width=420,
                    format_func=lambda i: " · ".join([
                        ", ".join(name_of.get(int(c), "?") for c in mine.loc[mine["key"] == opts[i]["key"], "chamber_id"]),
                        opts[i]["company"], chargers.span_text(opts[i]["start"], opts[i]["end"], today)]))
                st.button("고치기", icon=":material/edit:", key="cb_edit_go", disabled=pick is None,
                          on_click=_edit, args=(opts[pick] if pick is not None else {},))

    _config_editor(ch, eq)


def _config_editor(ch: pd.DataFrame, eq: pd.DataFrame) -> None:
    with st.expander("챔버 구성 고치기", icon=":material/tune:", expanded=ch.empty):
        names = {int(i): s for i, s in zip(eq["id"], eq["short"])}
        cands = sorted(db.charger_ids(eq, ch) | set(names), key=lambda i: (i not in db.charger_ids(eq, ch), names.get(i, "")))
        opts = [names[i] for i in cands if i in names]
        by_name = {names[i]: i for i in cands if i in names}
        view = pd.DataFrame({
            "id": ch["id"] if not ch.empty else pd.Series(dtype="int64"),
            "건물": ch["center"] if not ch.empty else pd.Series(dtype=str),
            "장비명": ch["unit"] if not ch.empty else pd.Series(dtype=str),
            "싸이클러": ch["cycler"] if not ch.empty else pd.Series(dtype=str),
            "챔버": ch["chamber"] if not ch.empty else pd.Series(dtype=str),
            "채널 no.": ch["channels"] if not ch.empty else pd.Series(dtype=str),
            "채널수": ch["ch_count"] if not ch.empty else pd.Series(dtype="int64"),
            "연결 장비": [names.get(int(e)) if pd.notna(e) else None for e in ch["equip_id"]] if not ch.empty else pd.Series(dtype=str),
        })
        ed = st.data_editor(view, num_rows="dynamic", hide_index=True, width="stretch", key="cb_cfg",
                            column_config={
                                "id": None,
                                "채널수": st.column_config.NumberColumn(min_value=0, step=1, help="비우면 채널 no.로 셈"),
                                "연결 장비": st.column_config.SelectboxColumn(
                                    options=opts, width="large",
                                    help="입력 카드에서 이 장비를 고르면 이 챔버가 나와요"),
                            })
        if st.button("저장", icon=":material/save:", type="primary", key="cb_cfg_save"):
            out = ed.rename(columns={"건물": "center", "장비명": "unit", "싸이클러": "cycler", "챔버": "chamber",
                                     "채널 no.": "channels", "채널수": "ch_count"})
            out["equip_id"] = out["연결 장비"].map(lambda v: by_name.get(v) if isinstance(v, str) else None)
            db.save_channels(out)
            st.toast("챔버 구성을 저장했어요.")
            st.rerun()
