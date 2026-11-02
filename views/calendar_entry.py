"""달력으로 하루 단위 실적을 입력하고, 하루치 입력을 다른 날로 복사하는 화면."""
from __future__ import annotations

import calendar
import datetime as dt

import pandas as pd
import streamlit as st

from core import db, rules, seed
from core.calc import expand_daily, kr_holidays
from ui_style import T, page_header

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
DEFAULT_INDUSTRY = ("전기전자", "이차전지_에너지", "이차전지")

# 표 열 이름 → 내부 키
FIELDS = {
    "장비": "equip_label", "업체": "company", "담당자": "created_by", "활용유형": "usage_type", "사용목적": "purpose",
    "사용시간": "hours", "시료수": "samples", "사용료": "fee",
    "지원개요": "overview", "지원내용": "content", "기타": "etc",
}


CELL_LINES = 4  # 달력 칸에 바로 보여 줄 실적 수 (나머지는 "+N건")
CSS = """<style>
.block-container {padding-top: 2.5rem;}
.st-key-calgrid [data-testid="stHorizontalBlock"] {gap: 0.4rem;}
/* 날짜 칸 */
.st-key-calgrid div[class*="st-key-cell_"] {min-height: 128px; padding: 6px 6px 8px; gap: 3px; border-radius: 10px;}
.st-key-calgrid div[class*="st-key-cell_"]:hover {border-color: var(--accent);}
.st-key-calgrid div[class*="st-key-cell_"] [data-testid="stVerticalBlock"] {gap: 3px;}
.st-key-calgrid button div[data-testid="stMarkdownContainer"] {width: 100%; min-width: 0; text-align: left;}
.st-key-calgrid button div[data-testid="stMarkdownContainer"] p {
  display: block; text-align: left; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
/* 날짜 머리 (누르면 그날 선택 / 붙여넣기) */
.st-key-calgrid div[class*="st-key-day_"] button,
.st-key-calgrid div[class*="st-key-ent_"] button {justify-content: flex-start; text-align: left;}
.st-key-calgrid div[class*="st-key-day_"] button > div,
.st-key-calgrid div[class*="st-key-ent_"] button > div {width: 100%; min-width: 0; justify-content: flex-start;}
.st-key-calgrid div[class*="st-key-day_"] button {min-height: 0; padding: 0 2px;}
.st-key-calgrid div[class*="st-key-day_"] button p {font-size: 0.78rem; opacity: 0.75;}
.st-key-calgrid div[class*="st-key-day_"] button strong {font-size: 0.95rem;}
/* 실적 한 줄 (누르면 이 실적만 복사) */
.st-key-calgrid div[class*="st-key-ent_"] button {
  justify-content: flex-start; min-height: 0; padding: 3px 7px; border: none; border-radius: 6px;
  background: rgba(45, 143, 213, 0.10); border-left: 3px solid var(--accent);}
.st-key-calgrid div[class*="st-key-ent_"] button:hover {background: rgba(45, 143, 213, 0.22);}
.st-key-calgrid div[class*="st-key-ent_"] button p {font-size: 0.72rem; line-height: 1.35;}
.st-key-calgrid div[class*="st-key-more_"] p {font-size: 0.7rem; color: #777; margin: 0 0 0 4px;}
</style>"""


def _cut(text: str, n: int) -> str:
    """n글자보다 길면 잘라서 … 를 붙임."""
    text = str(text).strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _md(text: str) -> str:
    """버튼 글자·툴팁이 마크다운으로 해석되지 않게."""
    for ch in "\\*_[]()#`~<>|":
        text = text.replace(ch, "\\" + ch)
    return text


def _hours(h: float) -> str:
    return f"{h:,.1f}".rstrip("0").rstrip(".") + "h"


def _shift_month(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1)


def _pick_day(day: dt.date) -> None:
    st.session_state.cal_day = day
    st.session_state.cal_month = day.replace(day=1)


def _day_rows(logs: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    """그날 하루짜리 실적 (사용시작일 = 사용종료일 = day)."""
    if logs.empty:
        return logs
    ts = pd.Timestamp(day)
    return logs[(logs["start_date"] == ts) & (logs["end_date"] == ts)]


def _paste_plan(src: list[dict], targets: list[dt.date], logs: pd.DataFrame) -> tuple[list[dict], int]:
    """src 실적을 targets 날짜에 붙여 넣을 목록. 그날 같은 장비·업체가 이미 있으면 건너뜀."""
    plan, skipped = [], 0
    for d in targets:
        there = _day_rows(logs, d)
        have = set(zip(there["equip_id"].astype(int), there["company"]))
        for r in src:
            if (int(r["equip_id"]), r["company"]) in have:
                skipped += 1
                continue
            rec = {k: r.get(k) for k in db.LOG_FIELDS}
            rec.update(start_date=d, end_date=d)
            plan.append(rec)
    return plan, skipped


def _record(row: dict, base: dict, comp_by_name: dict, eq_id: dict, cfg: dict) -> dict:
    """표 한 행 + (수정이면) 원래 실적 → 저장할 실적."""
    company = db.to_str(row.get("업체"))
    master = comp_by_name.get(company)
    rec = dict(base)
    rec.update(
        equip_id=eq_id.get(row.get("장비")),
        company=company,
        usage_type=db.to_str(row.get("활용유형")),
        purpose=db.to_str(row.get("사용목적")),
        hours=db.to_num(row.get("사용시간"), 0),
        samples=db.to_num(row.get("시료수"), 0),
        fee=db.to_num(row.get("사용료"), 0),
        etc=db.to_str(row.get("기타")),
        created_by=db.to_str(row.get("담당자")),
    )
    if master is not None:  # 사업자번호·업종은 항상 업체 목록 기준
        rec["brn"] = master["brn"]
        for k in ("industry", "item", "sub_item"):
            if master[k]:
                rec[k] = master[k]
    elif not company:
        rec["brn"] = ""
    for k, v in zip(("industry", "item", "sub_item"), DEFAULT_INDUSTRY):
        rec.setdefault(k, v)
        if not rec[k]:
            rec[k] = v
    old_ov, method, _ = seed.parse_detail(base.get("detail", ""))
    overview = db.to_str(row.get("지원개요"))
    rec["detail"] = seed.compose_detail(overview, method or "-", db.to_str(row.get("지원내용")))
    if not db.to_str(base.get("purpose_detail")) or db.to_str(base.get("purpose_detail")) == old_ov:
        rec["purpose_detail"] = overview
    rec.setdefault("dept", cfg.get("dept_default", ""))
    rec.setdefault("disclose", "N")
    rec.setdefault("include_holidays", "Y")
    return rec


def _cell_entries(in_month: pd.DataFrame, logs: pd.DataFrame, eq: pd.DataFrame) -> dict[dt.date, list[dict]]:
    """날짜별로 달력 칸에 보여 줄 실적 (장비, 업체, 그날 몫의 시간, 담당자, 기간 여부)."""
    if in_month.empty:
        return {}
    name_of = dict(zip(eq["id"].astype(int), eq["name"]))
    info = logs.set_index("id")
    out: dict[dt.date, list[dict]] = {}
    for r in in_month.itertuples(index=False):
        if r.log_id not in info.index:
            continue
        lg = info.loc[r.log_id]
        multi = lg["start_date"] != lg["end_date"]
        rec = lg.to_dict() | {"id": int(r.log_id)}
        if multi:  # 기간 실적은 그날 몫만 하루짜리로 복사
            rec.update(hours=round(float(r.hours), 1), fee=round(float(r.fee)))
        out.setdefault(r.day.date(), []).append({
            "id": int(r.log_id), "rec": rec,
            "equip": name_of.get(int(r.equip_id), "?"), "company": db.to_str(lg["company"]) or "내부",
            "hours": float(r.hours), "staff": db.to_str(lg["created_by"]),
            "period": f"{lg['start_date']:%m/%d}~{lg['end_date']:%m/%d}" if multi else "",
        })
    for v in out.values():
        v.sort(key=lambda e: (e["period"] != "", -e["hours"]))
    return out


def _day_head(d: dt.date, entries: list[dict], holiday: bool, today: bool) -> tuple[str, str | None]:
    """날짜 머리 글자와, 마우스를 올렸을 때 보일 그날 실적 전체."""
    mark = " 🔴" if holiday else (" 📍" if today else "")
    total = sum(e["hours"] for e in entries)
    head = f"**{d.day}**{mark}" + (f"\u2002{len(entries)}건 · {_hours(total)}" if entries else "")
    if not entries:
        return head, None
    tip = [f"**{d:%m/%d} ({WEEKDAYS[d.weekday()]}) · {len(entries)}건 · {_hours(total)}**", ""]
    for e in entries:
        tip.append(f"- {_entry_text(e)}")
    return head, "\n".join(tip)


def _entry_text(e: dict) -> str:
    extra = " · ".join(x for x in (e["staff"], f"기간 {e['period']}" if e["period"] else "") if x)
    return (f"{_md(e['equip'])} · {_md(e['company'])} · {_hours(e['hours'])}"
            + (f" ({_md(extra)})" if extra else ""))


def _paste(d: dt.date, clip: dict, logs: pd.DataFrame) -> None:
    plan, skipped = _paste_plan(clip["rows"], [d], logs)
    new_ids: list = []
    added = db.insert_logs(plan, ids_out=new_ids) if plan else 0
    if added:  # 같은 복사로 여러 날에 붙여 넣었으면 한꺼번에 되돌릴 수 있게 모음
        prev = st.session_state.get("cal_undo")
        if prev and prev.get("label") == clip["label"]:
            days = prev["days"] + [d]
            new_ids = prev["ids"] + new_ids
        else:
            days = [d]
        st.session_state.cal_undo = {"ids": new_ids, "days": days, "label": clip["label"],
                                     "text": f"붙여넣기({', '.join(f'{x:%m/%d}' for x in days)})"}
    st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
    st.session_state.cal_saved = (f"{d:%m/%d}에 {_cut(clip['label'], 30)} 붙여 넣었습니다" if added else
                                  f"{d:%m/%d}에는 같은 장비·업체가 이미 있어 붙여 넣지 않았습니다")


def _day_cell(col, d: dt.date, entries: list[dict], *, selected: bool, holiday: bool, today: bool,
              clip: dict | None, logs: pd.DataFrame) -> None:
    cell = col.container(border=True, key=f"cell_{d}")
    head, tip = _day_head(d, entries, holiday, today)
    pasting = bool(clip) and d != clip["from"]
    if cell.button(head, key=f"day_{d}", type="tertiary", width="stretch",
                   help=("여기를 누르면 붙여 넣습니다" if pasting else tip)):
        if pasting:
            _paste(d, clip, logs)
        _pick_day(d)
        st.rerun()
    for e in entries[:CELL_LINES]:
        label = f"{_md(e['equip'])}\n\n{_hours(e['hours'])} · {_md(e['company'])}"
        hint = "누르면 여기에 붙여 넣습니다" if pasting else "누르면 이 실적을 복사합니다. 그다음 붙여 넣을 날짜를 누르세요."
        if cell.button(label, key=f"ent_{d}_{e['id']}", width="stretch", help=f"{_entry_text(e)}\n\n{hint}"):
            if pasting:
                _paste(d, clip, logs)
                _pick_day(d)
            else:
                st.session_state.cal_clip = {"from": d, "rows": [e["rec"]],
                                             "label": f"{e['equip']} · {e['company']} · {_hours(e['hours'])}"}
                _pick_day(d)
            st.rerun()
    if len(entries) > CELL_LINES:
        cell.container(key=f"more_{d}").markdown(f"+{len(entries) - CELL_LINES}건 더 · 날짜에 마우스를 올려 보기")


def render() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    page_header("달력 입력", "실적",
                desc="칸 안의 실적을 누르면 복사, 다른 날짜를 누르면 붙여넣기. 날짜 숫자를 누르면 아래에서 그날 입력을 고칩니다.")
    msg = st.session_state.pop("cal_saved", None)
    undo = st.session_state.get("cal_undo")
    if msg or undo:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        if msg:
            c1.success(msg)
        if undo and c2.button("되돌리기", icon=":material/undo:", width="stretch",
                              help=f"방금 한 {undo['text']}를 취소합니다."):
            n = db.delete_logs(undo["ids"])
            st.session_state.pop("cal_undo", None)
            st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
            st.session_state.cal_saved = f"{undo['text']}를 취소했습니다 ({n}건 삭제)."
            st.rerun()

    cfg = db.get_settings()
    eq = db.load_equipment()
    comp = db.load_companies()
    logs = db.load_logs()

    today = dt.date.today()
    day: dt.date = st.session_state.setdefault("cal_day", today)
    month: dt.date = st.session_state.setdefault("cal_month", day.replace(day=1))

    # ── 달력 ──────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([1, 3, 1, 1])
    if c1.button("◀ 이전 달", width="stretch"):
        st.session_state.cal_month = _shift_month(month, -1)
        st.rerun()
    c2.markdown(f"<h4 style='text-align:center;margin:0;padding:0.3rem 0'>{month.year}년 {month.month}월</h4>",
                unsafe_allow_html=True)
    if c3.button("다음 달 ▶", width="stretch"):
        st.session_state.cal_month = _shift_month(month, 1)
        st.rerun()
    if c4.button("오늘", width="stretch"):
        _pick_day(today)
        st.rerun()

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month)
    hol = kr_holidays({weeks[0][0].year, weeks[-1][-1].year, today.year, today.year + 1})
    daily = expand_daily(logs, cfg.get("alloc_mode", "spread"))
    in_month = daily[(daily["day"] >= pd.Timestamp(weeks[0][0])) & (daily["day"] <= pd.Timestamp(weeks[-1][-1]))]
    by_day = _cell_entries(in_month, logs, eq)

    # ── 복사 / 붙여넣기 ─────────────────────────────────────
    clip = st.session_state.get("cal_clip")
    if clip and "label" not in clip:  # 예전 방식(하루 전체)으로 복사해 둔 것은 버림
        st.session_state.pop("cal_clip", None)
        clip = None
    if clip:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        c1.info(f"**{_md(_cut(clip['label'], 28))}** 복사됨 · 붙여 넣을 날짜를 누르세요",
                icon=":material/content_copy:")
        if c2.button("붙여넣기 끝", icon=":material/close:", width="stretch"):
            st.session_state.pop("cal_clip", None)
            st.rerun()

    grid = st.container(key="calgrid")
    sel = (f".st-key-cell_{day} {{border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent);}}")
    if clip:  # 복사한 실적은 진하게 표시
        sel += (f" .st-key-ent_{clip['from']}_{clip['rows'][0]['id']} button "
                "{background: var(--accent) !important;} "
                f".st-key-ent_{clip['from']}_{clip['rows'][0]['id']} button p {{color: #fff;}}")
    grid.markdown(f"<style>{sel}</style>", unsafe_allow_html=True)
    head = grid.columns(7)
    for i, w in enumerate(WEEKDAYS):
        color = T["ng"] if i == 6 else (T["accent-hi"] if i == 5 else "inherit")
        head[i].markdown(f"<div style='text-align:center;font-weight:600;color:{color}'>{w}</div>",
                         unsafe_allow_html=True)
    for week in weeks:
        cols = grid.columns(7)
        for i, d in enumerate(week):
            if d.month != month.month:
                cols[i].write("")
                continue
            _day_cell(cols[i], d, by_day.get(d, []), selected=d == day, holiday=d in hol, today=d == today,
                      clip=clip, logs=logs)
    st.caption("🔴 공휴일 · 📍 오늘 · 실적에 마우스를 올리면 전체 내용이 보입니다.")

    # ── 선택한 날 입력 ─────────────────────────────────────
    st.divider()
    st.subheader(f"{day:%Y-%m-%d} ({WEEKDAYS[day.weekday()]}) 입력")

    ts = pd.Timestamp(day)
    rows = _day_rows(logs, day)
    period = logs[(logs["start_date"] <= ts) & (logs["end_date"] >= ts)] if not logs.empty else logs
    period = period.drop(rows.index) if not period.empty else period

    active = eq[(eq["retired_on"].isna() | (eq["retired_on"] >= ts)) &
                (eq["acquired_on"].isna() | (eq["acquired_on"] <= ts))]
    label_of = dict(zip(eq["id"], eq["label"]))
    eq_id = dict(zip(eq["label"], eq["id"]))
    eq_opts = list(active["label"]) + [label_of[i] for i in rows["equip_id"] if i in label_of
                                       and label_of[i] not in set(active["label"])]
    comp_by_name = {r["name"]: r for r in comp.to_dict("records")}
    comp_opts = list(comp_by_name) + sorted({c for c in rows["company"] if c and c not in comp_by_name})

    staff_opts = db.staff_names(list(rows["created_by"]))
    missing = [name for name, empty in (("장비", eq.empty), ("담당자", not staff_opts)) if empty]
    if missing:
        st.warning(f"등록된 {'·'.join(missing)}이(가) 없어 새로 입력할 수 없습니다. "
                   f"'정보 입력' 메뉴의 {', '.join(m + ' 관리' for m in missing)}에서 먼저 등록하세요.")
    if comp.empty:
        st.caption("등록된 업체가 없습니다. 외부 업체 실적은 '업체 정보 입력'에서 업체를 먼저 등록한 뒤 입력하세요. "
                   "내부 사용은 업체 없이 입력할 수 있습니다.")
    last_staff = st.session_state.get("last_staff")

    view = pd.DataFrame({
        "id": rows["id"].astype("Int64"),
        "장비": rows["equip_id"].map(label_of),
        "업체": rows["company"].replace("", None),
        "담당자": rows["created_by"].replace("", None),
        "활용유형": rows["usage_type"], "사용목적": rows["purpose"],
        "사용시간": rows["hours"].astype(int), "시료수": rows["samples"].astype(int), "사용료": rows["fee"].astype(int),
        "지원개요": [seed.parse_detail(t)[0] for t in rows["detail"]],
        "지원내용": [seed.parse_detail(t)[2] for t in rows["detail"]],
        "기타": rows["etc"],
    }).reset_index(drop=True)
    # 빈 날은 열 형식을 알 수 없어 편집기가 오류를 내므로 형식을 고정
    view = view.astype({c: "string" for c in ("장비", "업체", "담당자", "활용유형", "사용목적", "지원개요", "지원내용", "기타")}
                       | {c: "Int64" for c in ("id", "사용시간", "시료수", "사용료")})

    ver = st.session_state.setdefault("cal_ver", 0)
    edited = st.data_editor(
        view, key=f"cal_ed_{day}_{ver}", num_rows="dynamic", hide_index=True, width="stretch",
        column_order=[c for c in view.columns if c != "id"],
        column_config={
            "장비": st.column_config.SelectboxColumn(options=eq_opts, required=True, width="large"),
            "업체": st.column_config.SelectboxColumn(options=comp_opts, width="medium",
                                                   help="내부 사용이면 비워 두세요. 목록에 없으면 '업체 정보 입력'에서 추가합니다."),
            "담당자": st.column_config.SelectboxColumn(options=staff_opts, required=True,
                                                    default=last_staff if last_staff in staff_opts else None,
                                                    help="목록에 없으면 '담당자 정보 입력'에서 추가합니다."),
            "활용유형": st.column_config.SelectboxColumn(options=seed.USAGE_TYPES, required=True, default="외부"),
            "사용목적": st.column_config.SelectboxColumn(options=seed.PURPOSES, required=True, default="생산"),
            "사용시간": st.column_config.NumberColumn("사용시간(h)", min_value=0, max_value=24, step=1, format="%d",
                                                  required=True),
            "시료수": st.column_config.NumberColumn(min_value=0, step=1, format="%d", default=0),
            "사용료": st.column_config.NumberColumn("사용료(원)", min_value=0, step=1000, format="%d", default=0),
            "지원개요": st.column_config.TextColumn(width="medium"),
            "지원내용": st.column_config.TextColumn(width="medium"),
        },
    )
    st.caption("맨 아래 빈 행에 입력하면 추가, 행 왼쪽을 선택해 휴지통을 누르면 삭제됩니다. 다 고친 뒤 저장을 누르세요.")

    orig = {int(r["id"]): r for r in rows.to_dict("records")}
    view_by_id = {int(r["id"]): r for r in view.to_dict("records")}
    new_rows, changed, kept = [], {}, set()
    for r in edited.to_dict("records"):
        rid = r.get("id")
        if rid is None or pd.isna(rid):
            if db.to_str(r.get("장비")):
                new_rows.append(r)
            continue
        rid = int(rid)
        kept.add(rid)
        a = {k: db.to_str(r.get(k)) for k in FIELDS}
        b = {k: db.to_str(view_by_id[rid].get(k)) for k in FIELDS}
        if a != b:
            changed[rid] = r
    removed = [i for i in orig if i not in kept]

    dirty = bool(new_rows or changed or removed)
    confirm = True
    if removed:
        confirm = st.checkbox(f"{len(removed)}건을 삭제합니다. 되돌릴 수 없습니다.", value=False, key=f"cal_del_{day}_{ver}")
    c1, c2 = st.columns([1, 3])
    if c1.button("💾 저장", type="primary", disabled=not dirty or not confirm, width="stretch"):
        errors, inserts, updates = [], [], {}
        base_new = {"start_date": day, "end_date": day}
        for r in new_rows:
            rec = _record(r, base_new, comp_by_name, eq_id, cfg)
            errors += [f"[새 행 · {r.get('장비')}] {e}" for e in rules.validate(rec)]
            if not rec["created_by"]:
                errors.append(f"[새 행 · {r.get('장비')}] 담당자를 선택하세요.")
            inserts.append(rec)
        for rid, r in changed.items():
            base = {k: orig[rid].get(k) for k in db.LOG_FIELDS if k in orig[rid]}
            base.update(start_date=day, end_date=day)
            rec = _record(r, base, comp_by_name, eq_id, cfg)
            errors += [f"[{r.get('장비')}] {e}" for e in rules.validate(rec)]
            if not rec["created_by"]:
                errors.append(f"[{r.get('장비')}] 담당자를 선택하세요.")
            updates[rid] = rec
        # 같은 장비를 하루 24시간 넘게 쓸 수는 없음 (저장된 행 + 새 행 기준)
        per_equip: dict[int, float] = {}
        for rec in list(inserts) + list(updates.values()):
            per_equip[rec["equip_id"]] = per_equip.get(rec["equip_id"], 0) + db.to_num(rec["hours"], 0)
        for rid, r in orig.items():
            if rid not in updates and rid not in removed:
                per_equip[int(r["equip_id"])] = per_equip.get(int(r["equip_id"]), 0) + db.to_num(r["hours"], 0)
        for eid, h in per_equip.items():
            if h > 24:
                errors.append(f"[{label_of.get(eid, eid)}] 하루 사용시간 합계가 {h:,.0f}h로 24h를 넘습니다.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            n_in = db.insert_logs(inserts)
            if inserts:
                st.session_state.last_staff = inserts[-1]["created_by"]
            n_up = db.update_logs(updates) if updates else 0
            n_del = db.delete_logs(removed)
            st.session_state.cal_ver = ver + 1
            st.session_state.pop("cal_undo", None)
            st.session_state.cal_saved = f"{day:%m/%d} 저장 · 추가 {n_in}건 · 수정 {n_up}건 · 삭제 {n_del}건"
            st.rerun()
    if dirty:
        c2.caption(f"저장 안 된 변경: 추가 {len(new_rows)} · 수정 {len(changed)} · 삭제 {len(removed)}")

    if not period.empty:
        with st.expander(f"이 날이 포함된 기간 실적 {len(period)}건 (여기서는 보기만, 수정은 '실적 조회·수정')"):
            st.dataframe(pd.DataFrame({
                "장비": period["equip_id"].map(label_of), "업체": period["company"],
                "시작일": period["start_date"].dt.date, "종료일": period["end_date"].dt.date,
                "사용시간(전체)": period["hours"].astype(int),
            }), hide_index=True, width="stretch")
