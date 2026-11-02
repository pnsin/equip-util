"""달력으로 하루 단위 실적을 입력하고, 하루치 입력을 다른 날로 복사하는 화면."""
from __future__ import annotations

import calendar
import datetime as dt

import pandas as pd
import streamlit as st

from core import db, rules, seed
from core.calc import expand_daily, kr_holidays

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
DEFAULT_INDUSTRY = ("전기전자", "이차전지_에너지", "이차전지")

# 표 열 이름 → 내부 키
FIELDS = {
    "장비": "equip_label", "업체": "company", "활용유형": "usage_type", "사용목적": "purpose",
    "사용시간": "hours", "시료수": "samples", "사용료": "fee",
    "지원개요": "overview", "지원내용": "content", "기타": "etc",
}


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


def _next_workday(d: dt.date, hol: set[dt.date]) -> dt.date:
    d += dt.timedelta(days=1)
    while d.weekday() >= 5 or d in hol:
        d += dt.timedelta(days=1)
    return d


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


def render() -> None:
    st.title("🗓️ 달력 입력")
    st.caption("날짜를 눌러 그날 사용한 장비를 입력하세요. 장비와 업체는 목록에서 고릅니다. "
               "비슷한 작업이 이어지면 아래 '다른 날로 복사'로 하루치를 그대로 옮길 수 있습니다.")
    msg = st.session_state.pop("cal_saved", None)
    if msg:
        st.success(msg)
        st.toast(msg, icon="✅")

    user = st.session_state.get("user", "")
    if not user:
        st.info("왼쪽 사이드바에서 작성자를 먼저 선택하세요.")
    cfg = db.get_settings()
    eq = db.load_equipment()
    comp = db.load_companies()
    logs = db.load_logs()
    if eq.empty:
        st.warning("등록된 장비가 없습니다. '장비 관리'에서 먼저 장비를 등록하세요.")
        return
    if comp.empty:
        st.info("등록된 업체가 없습니다. 외부 업체 실적을 입력하려면 '업체 관리'에서 업체를 먼저 등록하세요. "
                "내부 사용은 업체 없이 입력할 수 있습니다.")

    today = dt.date.today()
    day: dt.date = st.session_state.setdefault("cal_day", today)
    month: dt.date = st.session_state.setdefault("cal_month", day.replace(day=1))

    # ── 달력 ──────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([1, 3, 1, 1])
    if c1.button("◀ 이전 달", width="stretch"):
        st.session_state.cal_month = _shift_month(month, -1)
        st.rerun()
    c2.markdown(f"<h3 style='text-align:center;margin:0'>{month.year}년 {month.month}월</h3>", unsafe_allow_html=True)
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
    hours_by_day = in_month.groupby(in_month["day"].dt.date)["hours"].sum().to_dict()
    count_by_day = in_month.groupby(in_month["day"].dt.date)["log_id"].nunique().to_dict()

    head = st.columns(7)
    for i, w in enumerate(WEEKDAYS):
        color = "#d33" if i == 6 else ("#36c" if i == 5 else "inherit")
        head[i].markdown(f"<div style='text-align:center;font-weight:600;color:{color}'>{w}</div>",
                         unsafe_allow_html=True)
    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            if d.month != month.month:
                cols[i].write("")
                continue
            n, h = count_by_day.get(d, 0), hours_by_day.get(d, 0)
            mark = "🔴 " if d in hol else ("📍 " if d == today else "")
            label = f"{mark}{d.day}" + (f"  \n{n}건 · {h:,.0f}h" if n else "  \n·")
            if cols[i].button(label, key=f"cal_{d}", width="stretch",
                              type="primary" if d == day else "secondary"):
                _pick_day(d)
                st.rerun()
    st.caption("🔴 공휴일 · 📍 오늘 · 칸의 시간은 여러 날에 걸친 실적을 나눠 담은 시간까지 포함합니다.")

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

    view = pd.DataFrame({
        "id": rows["id"].astype("Int64"),
        "장비": rows["equip_id"].map(label_of),
        "업체": rows["company"].replace("", None),
        "활용유형": rows["usage_type"], "사용목적": rows["purpose"],
        "사용시간": rows["hours"].astype(int), "시료수": rows["samples"].astype(int), "사용료": rows["fee"].astype(int),
        "지원개요": [seed.parse_detail(t)[0] for t in rows["detail"]],
        "지원내용": [seed.parse_detail(t)[2] for t in rows["detail"]],
        "기타": rows["etc"],
    }).reset_index(drop=True)
    # 빈 날은 열 형식을 알 수 없어 편집기가 오류를 내므로 형식을 고정
    view = view.astype({c: "string" for c in ("장비", "업체", "활용유형", "사용목적", "지원개요", "지원내용", "기타")}
                       | {c: "Int64" for c in ("id", "사용시간", "시료수", "사용료")})

    ver = st.session_state.setdefault("cal_ver", 0)
    edited = st.data_editor(
        view, key=f"cal_ed_{day}_{ver}", num_rows="dynamic", hide_index=True, width="stretch",
        column_order=[c for c in view.columns if c != "id"],
        column_config={
            "장비": st.column_config.SelectboxColumn(options=eq_opts, required=True, width="large"),
            "업체": st.column_config.SelectboxColumn(options=comp_opts, width="medium",
                                                   help="내부 사용이면 비워 두세요. 목록에 없으면 '업체 관리'에서 추가합니다."),
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
    if c1.button("💾 저장", type="primary", disabled=not dirty or not confirm or not user, width="stretch"):
        errors, inserts, updates = [], [], {}
        base_new = {"start_date": day, "end_date": day}
        for r in new_rows:
            rec = _record(r, base_new, comp_by_name, eq_id, cfg)
            errors += [f"[새 행 · {r.get('장비')}] {e}" for e in rules.validate(rec)]
            inserts.append(rec)
        for rid, r in changed.items():
            base = {k: orig[rid].get(k) for k in db.LOG_FIELDS if k in orig[rid]}
            base.update(start_date=day, end_date=day)
            rec = _record(r, base, comp_by_name, eq_id, cfg)
            rec.pop("created_by", None)
            errors += [f"[{r.get('장비')}] {e}" for e in rules.validate(rec)]
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
            n_in = db.insert_logs(inserts, user)
            n_up = db.update_logs(updates) if updates else 0
            n_del = db.delete_logs(removed)
            st.session_state.cal_ver = ver + 1
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

    # ── 다른 날로 복사 ─────────────────────────────────────
    st.divider()
    st.subheader("📋 다른 날로 복사")
    if rows.empty:
        st.caption("이 날 저장된 입력이 없어 복사할 것이 없습니다.")
        return
    if dirty:
        st.warning("저장하지 않은 변경이 있습니다. 복사는 저장된 내용 기준이니 먼저 저장하세요.")

    names = {int(r["id"]): f"{label_of.get(r['equip_id'], '?')} · {r['company'] or '내부'} · {int(r['hours'])}h"
             for r in rows.to_dict("records")}
    pick = st.multiselect("복사할 항목", list(names), default=list(names), format_func=names.get,
                          key=f"cal_copy_pick_{day}_{ver}")
    mode = st.radio("붙여 넣을 날짜", ["다음 날", "다음 평일", "기간 지정"], horizontal=True, key="cal_copy_mode")
    if mode == "다음 날":
        targets = [day + dt.timedelta(days=1)]
    elif mode == "다음 평일":
        targets = [_next_workday(day, hol)]
    else:
        c1, c2 = st.columns([2, 1])
        nd = day + dt.timedelta(days=1)
        rng = c1.date_input("기간", value=(nd, nd + dt.timedelta(days=4)), format="YYYY-MM-DD",
                            key=f"cal_copy_rng_{day}")
        skip = c2.checkbox("주말·공휴일 빼기", value=True, key="cal_copy_skip")
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            s, e = rng
            targets = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
            if skip:
                hol_t = kr_holidays({s.year, e.year})
                targets = [d for d in targets if d.weekday() < 5 and d not in hol_t]
        else:
            targets = []
        targets = [d for d in targets if d != day]
        if len(targets) > 62:
            st.error("한 번에 62일까지 복사할 수 있습니다.")
            targets = []

    src = [orig[i] for i in pick]
    plan, skipped = [], 0
    for d in targets:
        there = _day_rows(logs, d)
        have = set(zip(there["equip_id"].astype(int), there["company"]))
        for r in src:
            if (int(r["equip_id"]), r["company"]) in have:
                skipped += 1
                continue
            rec = {k: r.get(k) for k in db.LOG_FIELDS if k != "created_by"}
            rec.update(start_date=d, end_date=d)
            plan.append(rec)
    if targets:
        shown = ", ".join(f"{d:%m/%d}({WEEKDAYS[d.weekday()]})" for d in targets[:8]) + (" …" if len(targets) > 8 else "")
        st.caption(f"{shown} · {len(targets)}일 × {len(src)}건 → {len(plan)}건 추가"
                   + (f" (같은 장비·업체가 이미 있는 {skipped}건은 건너뜀)" if skipped else ""))
    if st.button("📋 복사", type="primary", disabled=not plan or dirty or not user):
        n = db.insert_logs(plan, user)
        if len(targets) == 1:
            _pick_day(targets[0])
        st.session_state.cal_ver = ver + 1
        st.session_state.cal_saved = f"{n}건을 {len(targets)}일에 복사했습니다."
        st.rerun()
