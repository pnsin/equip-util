"""견적서 작성 · 장비 단가.

- 장비 단가 (기준 정보): 장비 목록에 맞춘 시간당 단가표. 의뢰(우리가 운전) · 직접(업체가 직접 사용) 두 가지.
  장비 목록에 없는 시험 종류별 단가·클린룸 같은 항목은 오른쪽 '시험 · 기타 항목'에.
- 견적서 작성: 팀이 쓰던 엑셀 견적서(제조 · 시험) 그대로 PDF 를 만듭니다 (core/quote_doc.py).
  금액은 시간당 단가로 계산하고, 금액 칸에 직접 넣으면 그 값을 그대로 씁니다.
"""
from __future__ import annotations

import datetime as dt
import html
import json

import pandas as pd
import streamlit as st

from core import db, quote_doc, quotes
from core.quote_doc import DISC_LABELS, EXTRA_TITLE, FORMS, MAX_EXTRAS, MAX_LINES, UNITS
from ui_style import page_header

STATUSES = ["예상견적", "시험의뢰", "기진행", "재견적"]
NUM = "localized"


def _clean(v):
    """data_editor 값 → 파이썬 값 (NaN·NA → None)."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def _frame(rows: list[dict], columns: list[str], text: tuple) -> pd.DataFrame:
    """표에 넣을 모양: 글자 칸의 빈 값은 '' (None 이라고 보이지 않게), 숫자 칸은 숫자."""
    df = pd.DataFrame(rows, columns=columns)
    for c in text:
        df[c] = df[c].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    for c in columns:
        if c not in text and c != "manual":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "manual" in df:
        df["manual"] = df["manual"].fillna(False).astype(bool)
    return df


def _won(v) -> str:
    return f"{int(round(v)):,}"


# ══════════════════════════════════════════════════════════════
# 장비 단가
# ══════════════════════════════════════════════════════════════

def render_rates() -> None:
    page_header("장비 단가", "기준 정보")
    msg = st.session_state.pop("rates_saved", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")
    eq = db.load_equipment()
    devices, extras = quotes.rate_table(eq, db.load_rates())
    ver = st.session_state.get("rates_ver", 0)
    ss = st.session_state
    # 고친 내용은 저장 전까지 여기 모아 둠 (대분류를 바꿔 봐도 고친 값이 남게)
    if ss.get("rate_work_ver") != ver:
        ss.rate_work = {int(r["equip_id"]): r for r in _records(devices)}
        ss.rate_work_ver = ver
    work: dict = ss.rate_work
    rows = list(work.values())

    filled = sum(1 for r in rows if not quotes.is_missing(r))
    with st.container(horizontal=True, vertical_alignment="center", key="rate_top"):
        st.markdown(f'<div class="q-tile q-inline"><b style="color:var(--ok)">{filled}</b><span>단가 있음</span></div>'
                    f'<div class="q-tile q-inline"><b style="color:var(--warn)">{len(rows) - filled}</b>'
                    f'<span>비어 있음</span></div>', unsafe_allow_html=True)
    groups = [g for g in dict.fromkeys(r["group"] for r in rows) if g]
    with st.container(horizontal=True, vertical_alignment="center"):
        pick = st.pills("대분류", groups, selection_mode="multi", key="rate_groups", label_visibility="collapsed")
        only_missing = st.toggle("비어 있는 것만", key="rate_missing")
    key = f"rate_dev_{ver}_{'|'.join(pick or [])}_{only_missing}"
    if ss.get("rate_base_key") != key:  # 표 원본은 이 보기에서 처음 그릴 때 한 번만 만듦
        view = pd.DataFrame(rows, columns=list(devices.columns))
        view["확인"] = ["비어 있음" if quotes.is_missing(r) else "" for r in rows]
        if pick:
            view = view[view["group"].isin(pick)]
        if only_missing:
            view = view[view["확인"] != ""]
        for c in ("price_req", "price_self"):
            view[c] = pd.to_numeric(view[c], errors="coerce")
        ss.rate_base, ss.rate_base_key = view.reset_index(drop=True), key
    base = ss.rate_base
    ed_dev = st.data_editor(
        base, key=key, hide_index=True, width="stretch", height=min(700, 38 + 35 * (len(base) + 1)),
        num_rows="fixed",
        column_order=["group", "equip", "name", "spec", "unit", "price_req", "price_self", "note", "확인"],
        disabled=["group", "equip", "확인"],
        column_config={
            "group": st.column_config.TextColumn("대분류", width="small"),
            "equip": st.column_config.TextColumn("장비", width="medium"),
            "name": st.column_config.TextColumn("견적서 장비명", width="medium",
                                                help="견적서에 찍히는 이름. 견적서에서 장비를 고르면 이 이름이 들어가요."),
            "spec": st.column_config.TextColumn("용량", width="small", help="견적서 '용량' 칸 기본값 (예: 50Ah)"),
            "unit": st.column_config.SelectboxColumn("단위", options=UNITS, width="small"),
            "price_req": st.column_config.NumberColumn("의뢰 단가", format=NUM, min_value=0,
                                                       help="우리가 운전할 때 시간당 단가"),
            "price_self": st.column_config.NumberColumn("직접 단가", format=NUM, min_value=0,
                                                        help="업체가 직접 쓸 때 시간당 단가"),
            "note": st.column_config.TextColumn("비고", width="medium"),
            "확인": st.column_config.TextColumn("", width="small"),
        })
    for r in _records(ed_dev):
        cur = work.get(int(r["equip_id"]))
        if cur is not None:
            cur.update({c: r.get(c) for c in ("name", "spec", "unit", "price_req", "price_self", "note")})

    st.markdown('<div class="q-sub" style="margin-top:1rem">시험 · 기타 항목</div>', unsafe_allow_html=True)
    ed_ex = st.data_editor(
        extras, key=f"rate_ex_{ver}", hide_index=True, width="stretch", num_rows="dynamic",
        height=min(560, 38 + 35 * (len(extras) + 2)),
        column_order=["name", "spec", "unit", "price_req", "note"],
        column_config={
            "name": st.column_config.TextColumn("항목", width="large", required=True,
                                                help="장비 목록에 없는 것 (예: 클린룸, 항온항습기 · 고온시험)"),
            "spec": st.column_config.TextColumn("용량", width="small"),
            "unit": st.column_config.SelectboxColumn("단위", options=UNITS, width="small", default="hr"),
            "price_req": st.column_config.NumberColumn("단가", format=NUM, min_value=0, help="시간당 단가"),
            "note": st.column_config.TextColumn("비고", width="large"),
        })
    if st.button("단가 저장", type="primary", icon=":material/save:"):
        name_of = dict(zip(eq["id"].astype(int), eq["name"]))
        out = []
        for eid, r in work.items():
            r = dict(r, equip_id=eid)
            dname = name_of.get(eid, "")
            r["_named"] = quotes._s(r.get("name")) not in ("", dname)
            if not r["_named"]:
                r["name"] = dname
            out.append(r)
        ex_rows = [dict(r, price_self=r.get("price_self")) for r in _records(ed_ex) if quotes._s(r.get("name"))]
        db.save_rates(out + ex_rows)
        ss.rates_saved = "단가를 저장했어요."
        ss.rates_ver = ver + 1
        ss.pop("rate_base_key", None)
        st.rerun()


# ══════════════════════════════════════════════════════════════
# 견적서 작성
# ══════════════════════════════════════════════════════════════

def _staff_map() -> dict[str, dict]:
    return {r["name"]: r for r in db.load_staff().to_dict("records")}


def _last_title(writer: str) -> str:
    """담당자 목록의 직급, 없으면 같은 사람이 지난번 견적서에 쓴 직급 (예: 선임연구원)."""
    own = (_staff_map().get(writer) or {}).get("title", "")
    if own:
        return own
    qs = db.load_quotes()
    for d in qs.loc[qs["writer"] == writer, "data"]:
        try:
            t = json.loads(d).get("writer_title")
        except (TypeError, ValueError):
            continue
        if t:
            return t
    return ""


def _next_no(day: dt.date) -> str:
    seqs = db.quote_seqs(day.year)
    if seqs:
        n = quote_doc.next_seq(seqs)
    else:
        n = int(db.to_num(db.get_settings().get("quote_next_seq"), 1) or 1) if day.year == 2026 else 1
    return quote_doc.make_no(day, n)


# 장비사용료 할인 기준 (고르면 할인율이 들어가고, 숫자는 직접 고칠 수 있음)
DISC_RULES = {
    "제조": {"max": 20, "help": "제조장비 최대 20%",
             "opts": {"지역기업 10%": 10, "회원사 5%": 5, "장기사용 5%": 5}},
    "시험": {"max": 30, "help": "시험평가장비 최대 30% · 지역기업·회원사는 제조장비 할인율을 더해요",
             "opts": {"장기 100~300h 10%": 10, "장기 301~500h 15%": 15, "장기 501h↑ 20%": 20,
                      "지역기업 10%": 10, "회원사 5%": 5}},
}


def _blank(form: str = "제조", writer: str = "") -> dict:
    today = dt.date.today()
    staff = _staff_map()
    return {
        "id": "", "form": form, "no": _next_no(today), "date": today.isoformat(), "company": "", "contact": "",
        "phone": "", "title": "", "writer": writer, "writer_title": _last_title(writer) if writer else "",
        "email": (staff.get(writer) or {}).get("email", ""),
        "lines": [quotes.new_line(form) for _ in range(3)],
        "extras": [dict(quotes.clean_extra(e), key=f"x{i}") for i, e in enumerate(quote_doc.DEFAULT_EXTRAS[form])],
        "disc1": None, "disc2": None, "remarks": quote_doc.DEFAULT_REMARKS[form],
        "status": "예상견적", "equip_text": "", "model": "", "requester": "", "region": "", "note": "",
    }


def _draft() -> dict:
    if "qd" not in st.session_state:
        st.session_state.qd = _blank(writer=st.session_state.get("q_last_writer", ""))
    return st.session_state.qd


def _bump(d: dict) -> None:
    """표를 새로 그림: 지금까지 고친 줄을 표 원본으로 삼고 표 이름(key)을 바꿈."""
    d["lines_base"] = d["lines"]
    d["extras_base"] = d["extras"]
    st.session_state.q_ver = st.session_state.get("q_ver", 0) + 1


def _reset(d: dict) -> None:
    d.pop("lines_base", None)
    d.pop("extras_base", None)
    st.session_state.qd = d
    st.session_state.q_ver = st.session_state.get("q_ver", 0) + 1
    st.session_state.pop("q_files", None)


def _load_saved(rec: dict, copy: bool) -> dict:
    try:
        d = json.loads(rec.get("data") or "{}")
    except (TypeError, ValueError):
        d = {}
    base = _blank(d.get("form", "제조"))
    base.update({k: v for k, v in d.items() if k in base})
    for k in ("status", "equip_text", "model", "requester", "region", "note"):
        base[k] = quotes._s(rec.get(k))
    base["id"] = "" if copy else quotes._s(rec.get("id"))
    if copy:
        base["no"] = _next_no(dt.date.today())
        base["date"] = dt.date.today().isoformat()
        base["status"] = "예상견적"
    return base


def _line_columns(form: str, options: list[str]) -> tuple[list[str], dict]:
    pick = st.column_config.SelectboxColumn("장비 고르기", options=options, width="medium",
                                            help="고르면 장비명·단가가 단가표에서 채워져요. 목록에 없으면 비워 두고 장비명에 직접 써도 돼요.")
    amount = st.column_config.NumberColumn("금액", format=NUM, min_value=0,
                                           help="자동 계산돼요. 직접 고치면 그 금액 그대로 들어가요.")
    manual = st.column_config.CheckboxColumn("직접", width="small", help="금액을 직접 넣은 줄. 끄면 다시 자동 계산")
    price = st.column_config.NumberColumn("단가", format=NUM, min_value=0, help="시간당 단가")
    mode = st.column_config.SelectboxColumn("이용", options=list(quotes.MODES), width="small",
                                            help="의뢰 = 우리가 운전 · 직접 = 업체가 직접 사용")
    if form == "시험":
        order = ["pick", "mode", "spec", "name", "count", "qty", "price", "difficulty", "amount", "manual"]
        cfg = {"pick": pick, "mode": mode,
               "spec": st.column_config.TextColumn("품명", width="medium"),
               "name": st.column_config.TextColumn("장비명/시험명", width="medium"),
               "count": st.column_config.NumberColumn("수량", min_value=0, width="small"),
               "qty": st.column_config.NumberColumn("시험시간", min_value=0, width="small"),
               "price": price,
               "difficulty": st.column_config.NumberColumn("난이도", min_value=0, step=0.1, width="small", format="%.1f"),
               "amount": amount, "manual": manual}
    else:
        order = ["pick", "mode", "name", "spec", "note", "qty", "unit", "price", "amount", "manual"]
        cfg = {"pick": pick, "mode": mode,
               "name": st.column_config.TextColumn("장비명", width="medium"),
               "spec": st.column_config.TextColumn("용량", width="small"),
               "note": st.column_config.TextColumn("비고", width="medium"),
               "qty": st.column_config.NumberColumn("사용량", min_value=0, width="small"),
               "unit": st.column_config.SelectboxColumn("단위", options=UNITS, width="small"),
               "price": price, "amount": amount, "manual": manual}
    return order, cfg


def _totals_html(form: str, t: dict, d: dict) -> str:
    l1, l2 = DISC_LABELS[form]
    rows = [("장비사용료 합계 (할인 전)", t["eq"])]
    if t["d1"]:
        rows.append((f"{l1} {quotes._s(d.get('disc1'))}%", -t["d1"]))
    if form == "제조" and t["d2"]:
        rows.append((f"{l2} {quotes._s(d.get('disc2'))}%", -t["d2"]))
    if t["d1"] or (form == "제조" and t["d2"]):
        rows.append(("장비사용료 합계 (할인 후)", t["after"]))
    rows.append((f"{EXTRA_TITLE[form]} 합계", t["extras"]))
    if form == "시험" and t["d2"]:
        rows.append((f"{l2} {quotes._s(d.get('disc2'))}%", -t["d2"]))
    rows.append(("총계 (천 원 미만 절사)", t["final"]))
    body = "".join(f'<div class="q-tr"><span>{html.escape(a)}</span><b>{_won(b)}</b></div>' for a, b in rows)
    return (f'<div class="q-total">{body}<div class="q-big"><span>견적 금액 (부가세 포함)</span>'
            f'<b>{_won(t["vat"])}원</b></div></div>')


def render_new() -> None:
    page_header("견적서 작성", "견적")
    d = _draft()
    ver = st.session_state.get("q_ver", 0)
    eq = db.load_equipment()
    devices, extras = quotes.rate_table(eq, db.load_rates())
    options = quotes.pick_options(devices, extras)
    comp = db.load_companies()
    companies = {r["name"]: r for r in comp.to_dict("records")}
    staff = _staff_map()

    # 맨 위: 양식 · 불러오기 · 새로
    with st.container(horizontal=True, vertical_alignment="center", key="q_top"):
        form = st.segmented_control("양식", list(FORMS), default=d["form"], key=f"q_form_{ver}",
                                    format_func=lambda f: "제조 · 장비사용" if f == "제조" else "시험",
                                    label_visibility="collapsed") or d["form"]
        saved = db.load_quotes()
        labels = {f"{r['no']} · {r['company']}": r for r in saved.to_dict("records")}
        pick = st.selectbox("불러오기", list(labels), index=None, placeholder="저장한 견적서 불러오기",
                            key=f"q_open_{ver}", label_visibility="collapsed", width=320)
        if pick:
            c1, c2 = st.columns(2, gap="small")
            if c1.button("열기", key=f"q_open_btn_{ver}", help="그 견적서를 고쳐요 (같은 번호)"):
                _reset(_load_saved(labels[pick], copy=False))
                st.rerun()
            if c2.button("복사해서 새로", key=f"q_copy_btn_{ver}", help="내용은 그대로, 새 번호로"):
                _reset(_load_saved(labels[pick], copy=True))
                st.rerun()
        if st.button("새로 쓰기", icon=":material/note_add:", key=f"q_new_{ver}"):
            _reset(_blank(form, d.get("writer", "")))
            st.rerun()
    if form != d["form"]:
        keep = {k: d[k] for k in ("no", "date", "company", "contact", "phone", "title", "writer", "writer_title",
                                  "email", "id", "status")}
        nd = _blank(form, d.get("writer", ""))
        nd.update(keep)
        _reset(nd)
        st.rerun()

    left, right = st.columns([1.75, 1], gap="large")
    with left:
        with st.container(border=True, key="q_head"):
            c1, c2, c3 = st.columns([1.2, 1, 1])
            d["no"] = c1.text_input("견적번호", value=d["no"], key=f"q_no_{ver}")
            day = c2.date_input("일자", value=dt.date.fromisoformat(d["date"][:10]), key=f"q_date_{ver}",
                                format="YYYY-MM-DD")
            d["date"] = day.isoformat()
            names = list(companies)
            cur = d["company"] if d["company"] in names else None
            comp_pick = c3.selectbox("수신", names + ([d["company"]] if d["company"] and not cur else []),
                                     index=(names + [d["company"]]).index(d["company"]) if d["company"] else None,
                                     placeholder="업체 고르기 (새로 써도 돼요)", accept_new_options=True,
                                     key=f"q_comp_{ver}")
            if (comp_pick or "") != d["company"]:
                d["company"] = comp_pick or ""
                info = companies.get(d["company"]) or {}
                if info and not d["contact"]:
                    d["contact"] = (info.get("contact") or "") and f"{info.get('contact')}님"
                if info and not d["phone"]:
                    d["phone"] = info.get("phone") or ""
                _bump(d)
                st.rerun()
            c1, c2, c3 = st.columns([1.2, 1, 1])
            d["title"] = c1.text_input("제목", value=d["title"], key=f"q_title_{ver}", placeholder="예: 전극 장비 사용")
            d["contact"] = c2.text_input("담당자", value=d["contact"], key=f"q_contact_{ver}", placeholder="예: 홍길동 대리님")
            d["phone"] = c3.text_input("전화번호", value=d["phone"], key=f"q_phone_{ver}")
            c1, c2, c3 = st.columns([1.2, 1, 1])
            wnames = list(staff)
            w = c1.selectbox("담당", wnames, index=wnames.index(d["writer"]) if d["writer"] in wnames else None,
                             placeholder="담당자 고르기", key=f"q_writer_{ver}")
            if (w or "") != d["writer"]:
                d["writer"] = w or ""
                d["email"] = (staff.get(d["writer"]) or {}).get("email", "") or d["email"]
                d["writer_title"] = _last_title(d["writer"]) or d["writer_title"]
                st.session_state.q_last_writer = d["writer"]
                _bump(d)
                st.rerun()
            d["writer_title"] = c2.text_input("직급", value=d["writer_title"], key=f"q_wt_{ver}",
                                              placeholder="예: 선임연구원")
            d["email"] = c3.text_input("E-Mail", value=d["email"], key=f"q_email_{ver}")

    with right:
        total_box = st.empty()
        action_box = st.container()

    # 1. 장비사용료
    with st.container(border=True, key="q_lines_box"):
        st.markdown('<div class="q-sub">1. 장비사용료</div>', unsafe_allow_html=True)
        order, cfg = _line_columns(form, list(options))
        # 표에 넣는 원본은 줄을 다시 정리할 때만 바꿈 (원본이 바뀌면 Streamlit 이 표에서 고친 내용을 버림)
        lines_df = _frame(d.setdefault("lines_base", d["lines"]), list(quotes.LINE_KEYS),
                          ("key", "pick", "mode", "name", "spec", "note", "unit"))
        # 보이는 칸 순서대로 열을 둠 (숨긴 열이 사이에 있으면 표에서 고친 값이 다른 열로 들어가는 문제가 있음)
        lines_df = lines_df[order + [c for c in lines_df.columns if c not in order]]
        ed = st.data_editor(lines_df, key=f"q_lines_{ver}", hide_index=True, width="stretch", num_rows="dynamic",
                            column_order=order, column_config=cfg,
                            height=38 + 35 * (len(lines_df) + 1))
        new_lines = quotes.apply_line_edits(form, d["lines"], _records(ed), options)
        if len(new_lines) > MAX_LINES[form]:
            st.caption(f":orange[양식에는 {MAX_LINES[form]}줄까지 들어가요. 그 아래 줄은 PDF에 빠져요.]")
        if _changed(new_lines, _records(ed)):
            d["lines"] = new_lines
            _bump(d)
            st.rerun()
        d["lines"] = new_lines
        l1, l2 = DISC_LABELS[form]
        rules = DISC_RULES[form]
        picked = st.pills("할인 기준", list(rules["opts"]), selection_mode="multi", key=f"q_dpick_{ver}",
                          default=d.get("disc_pick") or [], help=rules["help"])
        if picked != (d.get("disc_pick") or []):
            d["disc_pick"] = picked
            long_ = [rules["opts"][p] for p in picked if p.startswith("장기")]
            rest = [rules["opts"][p] for p in picked if not p.startswith("장기")]
            d["disc1"] = min(rules["max"], sum(rest) + (max(long_) if long_ else 0)) or None
            _bump(d)
            st.rerun()
        c1, c2, _ = st.columns([1, 1, 1.4])
        d["disc1"] = c1.number_input(f"{l1} (%)", min_value=0.0, max_value=100.0, step=1.0, format="%g",
                                     value=float(db.to_num(d.get("disc1"), 0) or 0), key=f"q_d1_{ver}") or None
        if form == "제조":
            d["disc2"] = c2.number_input(f"{l2} (%)", min_value=0.0, max_value=100.0, step=1.0, format="%g",
                                         value=float(db.to_num(d.get("disc2"), 0) or 0), key=f"q_d2_{ver}") or None

    # 2. 재료비 / 기술료
    with st.container(border=True, key="q_extra_box"):
        st.markdown(f'<div class="q-sub">2. {EXTRA_TITLE[form]}</div>', unsafe_allow_html=True)
        ex_df = _frame(d.setdefault("extras_base", d["extras"]),
                       ["key", "name", "qty", "unit", "price", "amount", "manual"], ("key", "name", "unit"))
        ex_cfg = {"name": st.column_config.TextColumn("재료명" if form == "제조" else "항목", width="large"),
                  "qty": st.column_config.NumberColumn("사용량", min_value=0, width="small"),
                  "unit": st.column_config.SelectboxColumn("단위", options=UNITS, width="small"),
                  "price": st.column_config.NumberColumn("단가", format=NUM, min_value=0),
                  "amount": st.column_config.NumberColumn("금액", format=NUM, min_value=0),
                  "manual": st.column_config.CheckboxColumn("직접", width="small")}
        ex_order = ["name", "qty", "unit", "price", "amount", "manual"] if form == "제조" else \
            ["name", "qty", "price", "amount", "manual"]
        ex_df = ex_df[ex_order + [c for c in ex_df.columns if c not in ex_order]]
        ed2 = st.data_editor(ex_df, key=f"q_ex_{ver}", hide_index=True, width="stretch",
                             num_rows="dynamic" if form == "제조" else "fixed",
                             column_order=ex_order, column_config=ex_cfg, height=38 + 35 * (len(ex_df) + 1))
        new_ex = quotes.apply_extra_edits(d["extras"], _records(ed2))
        if len(new_ex) > MAX_EXTRAS[form]:
            st.caption(f":orange[양식에는 {MAX_EXTRAS[form]}줄까지 들어가요.]")
        if _changed(new_ex, _records(ed2)):
            d["extras"] = new_ex
            _bump(d)
            st.rerun()
        d["extras"] = new_ex
        if form == "시험":
            l2 = DISC_LABELS[form][1]
            c1, _ = st.columns([1, 2.4])
            d["disc2"] = c1.number_input(f"{l2} (%)", min_value=0.0, max_value=100.0, step=1.0, format="%g",
                                         value=float(db.to_num(d.get("disc2"), 0) or 0), key=f"q_d2_{ver}") or None

    with st.expander("기타사항 · 발급대장 칸"):
        d["remarks"] = st.text_area("기타사항 (견적서에 찍혀요)", value=d.get("remarks") or "", key=f"q_rem_{ver}",
                                    height=90)
        c1, c2, c3 = st.columns(3)
        d["equip_text"] = c1.text_input("기기명", value=d.get("equip_text") or quotes.equip_text(d["lines"]),
                                        key=f"q_et_{ver}")
        d["model"] = c2.text_input("모델명", value=d.get("model") or "", key=f"q_model_{ver}")
        d["requester"] = c3.text_input("의뢰자", value=d.get("requester") or quotes.requester_of(d["contact"]),
                                       key=f"q_req_{ver}")
        c1, c2, c3 = st.columns(3)
        d["region"] = c1.text_input("광역/도", value=d.get("region") or "", key=f"q_region_{ver}",
                                    placeholder="예: 충북")
        d["status"] = c2.selectbox("진행여부", STATUSES, index=STATUSES.index(d["status"])
                                   if d.get("status") in STATUSES else 0, key=f"q_status_{ver}")
        d["note"] = c3.text_input("비고", value=d.get("note") or "", key=f"q_note_{ver}")

    t = quote_doc.totals(d)
    total_box.markdown(_totals_html(form, t, d), unsafe_allow_html=True)
    with action_box:
        problems = _problems(d)
        for p in problems:
            st.caption(f":orange[{p}]")
        again = bool(d.get("id"))
        if st.button("고친 내용 저장하고 PDF 만들기" if again else "발급하고 PDF 만들기", type="primary",
                     icon=":material/picture_as_pdf:", width="stretch", disabled=bool(problems), key=f"q_issue_{ver}"):
            _issue(d, t)
        st.download_button("엑셀로 받기", data=quote_doc.fill_xlsx(d), width="stretch", icon=":material/download:",
                           file_name=quote_doc.file_name(d, "xlsx"), key=f"q_xlsx_{ver}",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           help="같은 양식의 엑셀 파일 (저장하지 않고 받기만)")
        files = st.session_state.get("q_files")
        if files and files.get("no") == d["no"]:
            for label, data, name in files["pdfs"]:
                st.download_button(label, data=data, file_name=name, mime="application/pdf", width="stretch",
                                   icon=":material/download:", key=f"q_dl_{name}_{ver}")
        elif files and files.get("error"):
            st.caption(f":red[{files['error']}]")
    files = st.session_state.get("q_files")
    if files and files.get("no") == d["no"] and files.get("preview"):
        with st.expander("PDF 미리보기", expanded=True):
            st.image(files["preview"], width=760)

def _changed(new: list[dict], edited: list[dict]) -> bool:
    """정리한 줄이 표에 보이는 값과 달라졌는지 (달라졌으면 표를 다시 그려야 함)."""
    if len(new) != len(edited):
        return True
    for a, b in zip(new, edited):
        for k, v in a.items():
            if not quotes._same(v, b.get(k)) and not (k == "manual" and bool(v) == bool(b.get(k))):
                return True
    return False


def _problems(d: dict) -> list[str]:
    out = []
    if not quotes._s(d.get("company")):
        out.append("수신(업체)을 골라 주세요.")
    if not quotes._s(d.get("no")):
        out.append("견적번호를 넣어 주세요.")
    elif not d.get("id"):
        have = set(db.load_quotes()["no"].map(quotes._s))
        if quotes._s(d["no"]) in have:
            out.append(f"{d['no']}은(는) 이미 발급한 번호예요. 번호를 바꾸거나 '불러오기'로 열어 고쳐 주세요.")
    return out


def _issue(d: dict, t: dict) -> None:
    lines = [ln for ln in d["lines"] if not quote_doc.is_blank_line(ln)]
    data = {k: d.get(k) for k in ("form", "no", "date", "company", "contact", "phone", "title", "writer",
                                  "writer_title", "email", "disc1", "disc2", "remarks")}
    data["lines"] = lines
    data["extras"] = [e for e in d["extras"] if quotes._s(e.get("name")) or e.get("amount")]
    rec = {"id": d.get("id") or "", "seq": quotes.seq_of(d["no"]), "no": d["no"], "issued_on": d["date"],
           "company": d["company"], "equip_text": d.get("equip_text") or quotes.equip_text(lines),
           "model": d.get("model") or "", "requester": d.get("requester") or quotes.requester_of(d["contact"]),
           "region": d.get("region") or "", "amount": t["final"], "amount_vat": t["vat"],
           "status": d.get("status") or "예상견적", "writer": d.get("writer") or "", "note": d.get("note") or "",
           "form": d["form"], "title": d.get("title") or "",
           "data": json.dumps(data, ensure_ascii=False, default=str)}
    with st.spinner("PDF 만드는 중…"):
        d["id"] = db.save_quote(rec)
        files = {"no": d["no"], "pdfs": []}
        try:
            parts = [("customer", "PDF 받기 (업체용)"), ("internal", "PDF 받기 (내부보관용)")] \
                if d["form"] == "시험" else [("all", "PDF 받기")]
            for part, label in parts:
                pdf = quote_doc.to_pdf(quote_doc.fill_xlsx(d, part))
                files["pdfs"].append((label, pdf, quote_doc.file_name(d, "pdf", part)))
            files["preview"] = _preview(files["pdfs"][0][1])
        except quote_doc.PdfError as e:
            files = {"no": "", "error": f"{e} 엑셀로 받아서 PDF로 저장해 주세요."}
    st.session_state.q_files = files
    st.toast(f"{d['no']} 저장했어요.", icon=":material/check_circle:")


def _preview(pdf: bytes) -> bytes | None:
    """PDF 첫 쪽 그림 (pdftoppm 이 있을 때만)."""
    import shutil
    import subprocess
    import tempfile
    exe = shutil.which("pdftoppm")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = f"{tmp}/q.pdf"
        with open(src, "wb") as f:
            f.write(pdf)
        try:
            subprocess.run([exe, "-png", "-r", "110", "-f", "1", "-l", "1", "-singlefile", src, f"{tmp}/p"],
                           check=True, capture_output=True, timeout=30)
            with open(f"{tmp}/p.png", "rb") as f:
                return f.read()
        except Exception:  # noqa: BLE001 - 미리보기는 없어도 됨
            return None
