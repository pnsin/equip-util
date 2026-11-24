"""장비 가동 현황 (2026-11-21): 어느 장비가 언제 돌고 있는지 한눈에 (예전 '충방전기 현황'을 넓힘).

- 줄 = 장비 목록 순서의 장비 (주장비 아래 세부장비는 들여 씀). 구분은 장비용도(시험·제조·분석), 충방전기는 '시험(충방전)'.
- 막대 = 실적 (달마다 나눠 저장한 기간 실적은 묶음ID로 한 막대). 주말·공휴일에도 시험이 이어지면 막대는 이어서 보이고,
  '휴무일 제외' 실적의 주말·공휴일은 흐리게 (가동률에는 넣지 않음).
- 엑셀의 날짜별 시간 = 가동률(장비 KPI 현황)과 같은 계산 (calc.expand_daily + 충방전기 하루 최대).
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd

from core import calc, db
from core.db import to_date, to_str

CHARGER = "시험(충방전기)"  # views.calendar_entry.CHARGER_GROUP 과 같은 이름
GROUPS = ["시험", CHARGER, "제조", "분석"]
GROUP_LABEL = {"시험": "시험(환경)", CHARGER: "시험(충방전)", "제조": "제조", "분석": "분석"}
PURPOSE_CAT = {"시험": "시험", "생산": "제조", "분석": "분석", "계측": "분석", "교육": "교육", "기타": "지원"}


def window(today: dt.date) -> tuple[dt.date, dt.date]:
    """보는 기간 = 이번 달 1일 ~ 두 달 뒤 말일 (충방전기 현황과 같음)."""
    d0 = today.replace(day=1)
    d1 = (d0 + dt.timedelta(days=95)).replace(day=1) - dt.timedelta(days=1)
    return d0, d1


def device_group(eq: pd.DataFrame, ch: pd.DataFrame | None = None) -> dict[int, str]:
    """장비 ID → 구분 (시험 / 시험(충방전기) / 제조 / 분석 / 기타)."""
    out = {}
    for i, u in zip(eq["id"].astype(int), eq.get("use", pd.Series([""] * len(eq)))):
        u = to_str(u)
        out[i] = "제조" if u in ("생산", "제조") else (u if u in ("시험", "분석") else "기타")
    for i in db.charger_family(eq, ch):  # 충방전기 + 충방전기를 세부장비로 둔 상위 장비
        out[int(i)] = CHARGER
    return out


def bars(logs: pd.DataFrame, w0: dt.date, w1: dt.date) -> pd.DataFrame:
    """보는 기간에 걸친 실적 → 막대 (장비 · 묶음마다 한 줄)."""
    cols = ["equip_id", "key", "start", "end", "company", "purpose", "cat", "skip_off", "staff", "log_ids"]
    if logs.empty:
        return pd.DataFrame(columns=cols)
    lg = logs[logs["start_date"].notna()].copy()
    lg["end_date"] = lg["end_date"].fillna(lg["start_date"])
    lg = lg[(lg["start_date"] <= pd.Timestamp(w1)) & (lg["end_date"] >= pd.Timestamp(w0))]
    if lg.empty:
        return pd.DataFrame(columns=cols)
    ser = lg["series"] if "series" in lg else pd.Series([""] * len(lg), index=lg.index)
    lg["key"] = [to_str(s) or f"#{i}" for s, i in zip(ser, lg["id"])]
    recs = []
    for (eid, key), g in lg.groupby(["equip_id", "key"], sort=False):
        g = g.sort_values("start_date")
        first = g.iloc[0]
        p = to_str(first["purpose"])
        recs.append({"equip_id": int(eid), "key": key, "start": to_date(g["start_date"].min()),
                     "end": to_date(g["end_date"].max()), "company": to_str(first["company"]) or "내부",
                     "purpose": p, "cat": PURPOSE_CAT.get(p, "지원"),
                     "skip_off": all(to_str(v) == "N" for v in g["include_holidays"]),
                     "staff": to_str(first.get("created_by", "")), "log_ids": [int(i) for i in g["id"]]})
    return pd.DataFrame(recs, columns=cols).sort_values(["equip_id", "start"]).reset_index(drop=True)


def rows(eq: pd.DataFrame, groups: dict[int, str], bk: pd.DataFrame, w0: dt.date, w1: dt.date,
         want: str = "전체", center: str = "전체", busy_first: bool = True) -> list[dict]:
    """화면·엑셀에 보일 장비 줄 (장비 목록 순서, 구분 → 주장비 묶음; 기간에 실적이 있는 묶음을 위로).

    줄 = 실적을 넣는 맨 아래 장비 + 실적이 직접 붙은 상위 장비 + 그 위 주장비(묶음 머리). 기간에 없던 장비(도입 전·불용)는 뺌.
    """
    if eq.empty:
        return []
    ts0, ts1 = pd.Timestamp(w0), pd.Timestamp(w1)
    act = eq[(eq["retired_on"].isna() | (eq["retired_on"] >= ts0)) & (eq["acquired_on"].isna() | (eq["acquired_on"] <= ts1))]
    cen = db.equip_centers(eq)
    parent = {int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)}
    has_kids = {int(p) for p in act["parent_id"].dropna()}
    with_bars = set(bk["equip_id"].astype(int)) if not bk.empty else set()
    info = {int(r["id"]): r for r in act.to_dict("records")}
    keep = [i for i in info if i not in has_kids or i in with_bars]
    for i in list(keep):  # 세부장비가 보이면 그 위 장비들도 묶음 머리로
        p, seen = parent.get(i), set()
        while p is not None and p in info and p not in seen:
            seen.add(p)
            keep.append(p)
            p = parent.get(p)
    keep = set(keep)
    def root_of(i: int) -> int:
        root, p = i, parent.get(i)
        while p is not None and p in info:
            root, p = p, parent.get(p)
        return root

    def group_of(i: int) -> str:
        """세부장비는 주장비 구분을 따름 (2026-11-21: 주장비가 다른 구분이면 세부장비만 떨어져 보이던 문제)."""
        rg = groups.get(root_of(i), "기타")
        return rg if rg in GROUPS else groups.get(i, "기타")

    # 주장비 구분이 GROUPS 밖이면 세부장비 구분으로: 그 묶음의 첫 세부장비 구분을 묶음 전체에 씀
    first_g: dict[int, str] = {}
    for i in info:
        if i in keep:
            first_g.setdefault(root_of(i), group_of(i)) if group_of(i) in GROUPS else None
    out = []
    for i in info:  # load_equipment 순서 = 장비 목록 순서
        if i not in keep:
            continue
        root = root_of(i)
        g = group_of(i)
        if g not in GROUPS:
            g = first_g.get(root, g)
        if g not in GROUPS or (want != "전체" and g != want):
            continue
        c = cen.get(i, "")
        if center != "전체" and c != center:
            continue
        r = info[i]
        out.append({"id": i, "name": to_str(r["short"]) or to_str(r["name"]), "full": to_str(r["name"]),
                    "depth": int(r.get("depth") or 0), "root": root, "group": g, "center": c,
                    "head": i in has_kids, "own": i in with_bars})
    # 기간에 실적이 있는 묶음(주장비 단위)을 구분 안에서 위로 (2026-11-20 충방전기 현황과 같은 규칙)
    busy_root = {r["root"] for r in out if r["id"] in with_bars}
    order = {g: k for k, g in enumerate(GROUPS)}
    out = [r for _, r in sorted(enumerate(out), key=lambda t: (order[t[1]["group"]],
                                                               busy_first and t[1]["root"] not in busy_root, t[0]))]
    return out


def is_off(d: dt.date, hol: set) -> bool:
    return d.weekday() >= 5 or d in hol


def now_next(bs: list[dict], today: dt.date) -> tuple[dict | None, bool]:
    """오늘 돌고 있는 실적 (없으면 다음 예약). (막대, 오늘 진행 중?)"""
    cur = [b for b in bs if b["start"] <= today <= b["end"]]
    if cur:
        return cur[0], True
    nxt = sorted((b for b in bs if b["start"] > today), key=lambda b: b["start"])
    return (nxt[0] if nxt else None), False


# ── 엑셀 (2026-11-21 사용자: 시험파트 '참고_시험평가장비 가동률' 파일과 같은 형식) ─────────────
# 총괄 탭 (장비 리스트 · 내부+외부/내부/외부 가동시간·횟수·가동률) + 장비마다 탭 하나 (1월 1일 ~ 12월 31일 하루 한 줄,
# 오른쪽에 월별 SUMIFS 합계). 숫자는 가동률 계산과 같음: 사용시간 = calc.expand_daily(+충방전기 하루 최대)의 그날 몫,
# 가용시간 = 장비 KPI 현황과 같은 '올해 오늘까지' (도입일·연간기준시간 반영). 세부장비 실적은 주장비 탭에 함께.
GREEN = "FF92D050"
YELLOW = "FFFFFF00"
DAY_HEAD = ["장비명", "장비취득일자", "취득금액(원)", "NFEC등록번호", "가동No.", "사용시작일", "사용종료일",
            "활용유형\n(내부/외부)", "사용기관(기업)명", "사업자등록번호", "기업규모", "사용목적", "의뢰자", "사용시간\n(hr기준)"]


def _sheet_name(k: int, name: str, used: set) -> str:
    bad = '[]:*?/\\'
    base = "".join("·" if ch in bad else ch for ch in f"{k}. {name}")[:31]
    out, n = base, 2
    while out in used:
        tail = f" ({n})"
        out, n = base[:31 - len(tail)] + tail, n + 1
    used.add(out)
    return out


def year_units(rws: list[dict]) -> list[dict]:
    """엑셀 탭 = 화면 줄의 맨 위 장비(주장비) 하나씩 (세부장비 실적은 그 탭에 함께)."""
    seen, out = set(), []
    for r in rws:
        if r["root"] not in seen:
            seen.add(r["root"])
            out.append(r["root"])
    return out


def to_excel(rws: list[dict], logs: pd.DataFrame, eq: pd.DataFrame, year: int, today: dt.date, cfg: dict,
             title: str = "", charger_sheet: bytes | None = None) -> bytes:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from core import report, seed

    ys, ye = dt.date(year, 1, 1), dt.date(year, 12, 31)
    cutoff = min(today, ye) if year == today.year else ye  # 올해는 오늘까지 센 시간 (장비 KPI 현황과 같음)
    annual = float(cfg.get("annual_hours") or 2000)
    roots = year_units(rws)
    fam = db.descendants(eq)  # 장비 → 자신 + 모든 하위 장비
    info = {int(r["id"]): r for r in eq.to_dict("records")}
    # 2026-11-24 사용자: '의뢰자'에 우리 쪽 담당자(작성자)가 들어가 모두 박노신으로 나옴 → 업체 목록의 업체 담당자 (없으면 빈칸)
    comp = db.load_companies()
    contact_of = ({to_str(n): to_str(c) for n, c in zip(comp["name"], comp["contact"]) if to_str(c) not in ("", "-")}
                  if not comp.empty else {})
    lg = logs[logs["start_date"].notna()].copy() if not logs.empty else logs
    if not lg.empty:
        lg["end_date"] = lg["end_date"].fillna(lg["start_date"])
        lg = lg[(lg["start_date"] <= pd.Timestamp(ye)) & (lg["end_date"] >= pd.Timestamp(ys))]
    daily = calc.expand_daily(lg, cfg.get("alloc_mode", "spread"), db.charger_caps()) if not lg.empty else None
    by_log: dict[tuple[int, dt.date], float] = {}
    if daily is not None and len(daily):
        dd = daily[(daily["day"] >= pd.Timestamp(ys)) & (daily["day"] <= pd.Timestamp(cutoff))]
        for (i, d), h in dd.groupby(["log_id", "day"])["hours"].sum().items():
            by_log[(int(i), d.date())] = float(h)
    summ = calc.equipment_summary(daily if daily is not None else calc.expand_daily(lg), eq[eq["id"].isin(roots)],
                                  ys, cutoff, annual, eq) if roots else pd.DataFrame()
    avail = dict(zip(summ["equip_id"].astype(int), summ["가용시간"])) if len(summ) else {}

    wb = Workbook()
    tot = wb.active
    tot.title = "총괄"
    thin = Side(style="thin", color="000000")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    mid = Alignment(horizontal="center", vertical="center", wrap_text=True)
    bold = Font(name="맑은 고딕", bold=True, size=11)
    norm = Font(name="맑은 고딕", size=11)
    days = [ys + dt.timedelta(days=k) for k in range((ye - ys).days + 1)]
    used_names: set = {"총괄"}
    sheets = []
    for k, rid in enumerate(roots, start=1):
        me = info.get(rid, {})
        ids = set(fam.get(rid, [rid]))
        mine = lg[lg["equip_id"].astype(int).isin(ids)] if not lg.empty else lg
        ws = wb.create_sheet(_sheet_name(k, to_str(me.get("name")), used_names))
        for j, h in enumerate(DAY_HEAD, start=1):
            c = ws.cell(1, j, h)
            c.font, c.alignment, c.border = bold, mid, box
            if j <= 4:
                c.fill = PatternFill("solid", fgColor=GREEN)
        recs = sorted(mine.to_dict("records"), key=lambda x: (x["start_date"], x["id"])) if len(mine) else []
        r, n_in, n_out, keys_in, keys_out = 2, 0, 0, set(), set()
        for d in days:
            ts = pd.Timestamp(d)
            run = [x for x in recs if x["start_date"] <= ts <= x["end_date"]]
            for x in (run or [None]):
                nm = to_str(me.get("name"))
                vals = [nm, None, None, None, r - 1, d, d]
                if x is not None:
                    eid = int(x["equip_id"])
                    if eid != rid:  # 세부장비 실적은 어느 장비인지 함께
                        nm = f"{nm} › {to_str(info.get(eid, {}).get('short') or info.get(eid, {}).get('name'))}"
                    out = to_str(x.get("usage_type")) == "외부"
                    h = by_log.get((int(x["id"]), d), 0.0) if d <= cutoff else None
                    key = to_str(x.get("series")) or f"#{x['id']}"
                    if d <= cutoff:
                        (keys_out if out else keys_in).add(key)
                    vals = [nm, None, None, None, r - 1, d, d, "외부" if out else "내부",
                            to_str(x.get("company")) or to_str(x.get("dept")), to_str(x.get("brn")), None,
                            seed.purpose_label(to_str(x.get("purpose"))), contact_of.get(to_str(x.get("company"))) or None,
                            (int(h) if float(h).is_integer() else float(h)) if h is not None else None]
                if r == 2:  # 장비 정보는 첫 줄에
                    acq = me.get("acquired_on")
                    vals[1] = acq.date() if acq is not None and pd.notna(acq) else None
                    vals[3] = to_str(me.get("nfec")) or None
                for j, v in enumerate(vals, start=1):
                    c = ws.cell(r, j, v)
                    c.font, c.alignment = norm, Alignment(horizontal="center", vertical="center")
                    if j in (2, 6, 7):
                        c.number_format = "mm-dd-yy"
                    elif j == 14:
                        c.number_format = "0.##"  # 나눠 담긴 시간도 값은 그대로 (합계가 가동률 계산과 같게)
                r += 1
        last = r - 1
        for j, h in ((16, "월"), (17, "사용시간(hr)"), (18, "내부"), (19, "외부")):
            c = ws.cell(1, j, h)
            c.font, c.alignment = bold, mid
        for m in range(1, 13):
            rr = m + 1
            ws.cell(rr, 16, m)
            rng = f'$G:$G,">="&DATE({year},P{rr},1),$G:$G,"<="&EOMONTH(DATE({year},P{rr},1),0)'
            ws.cell(rr, 17, f"=SUMIFS($N:$N,{rng})")
            ws.cell(rr, 18, f'=SUMIFS($N:$N,{rng},H:H,"내부")')
            ws.cell(rr, 19, f'=SUMIFS($N:$N,{rng},H:H,"외부")')
            for j in range(16, 20):
                ws.cell(rr, j).alignment = Alignment(horizontal="center")
        ws.cell(14, 16, "계")
        for j, col in ((17, "Q"), (18, "R"), (19, "S")):
            ws.cell(14, j, f"=SUM({col}2:{col}13)").font = bold
        for j in range(16, 20):
            ws.cell(14, j).alignment = Alignment(horizontal="center")
        av = float(avail.get(rid, 0.0))
        c = ws.cell(1, 21, "가동률")
        c.font, c.fill = bold, PatternFill("solid", fgColor=YELLOW)
        c = ws.cell(1, 22, f"=IFERROR(Q14/{av:.6f},0)" if av else 0)
        c.font, c.fill, c.number_format = bold, PatternFill("solid", fgColor=YELLOW), "0%"
        for col, wdt in {"A": 18.9, "B": 16.4, "C": 10.6, "D": 20.3, "E": 8, "F": 11, "G": 11, "H": 10.5, "I": 16,
                         "J": 14.4, "K": 10.5, "L": 10, "M": 9, "N": 10, "P": 5.8, "Q": 10.8, "R": 10.8, "S": 10.8}.items():
            ws.column_dimensions[col].width = wdt
        ws.freeze_panes = "A2"
        sheets.append((rid, ws.title, len(keys_in), len(keys_out), av, last))

    # ── 총괄 ──
    target = float(report.kpi(cfg, year)["util_total"] or 0)
    n = len(sheets)
    first, end = 6, 5 + max(n, 1)
    tot.cell(1, 5, f"{year}년 평균가동률").font = bold
    # 2026-11-24 점검: 장비별 가동률의 단순 평균(18.8%)이 장비 KPI 현황(19.0%)과 달랐음 → 같은 계산 (Σ가동시간 ÷ Σ가용시간)
    c = tot.cell(1, 6, f"=IFERROR(SUM(K{first}:K{end})/SUM(J{first}:J{end}),0)" if n else 0)
    c.number_format, c.font = "0.0%", bold
    tot.cell(1, 7, f"목표 : {target:g}%").font = bold
    tot.cell(2, 5, (title + " · " if title else "") + f"{cutoff:%Y-%m-%d}까지 · 가용시간·가동시간은 장비 KPI 현황과 같은 계산 "
                   "(세부장비 시간은 주장비에 더함, 주말에 이어지는 시험은 0시간)").font = Font(size=9, color="6B7280")
    for a, b, h in (("B4", "J4", "장비 리스트"), ("K4", "M4", "내부+외부"), ("N4", "P4", "내부"), ("Q4", "S4", "외부")):
        tot.merge_cells(f"{a}:{b}")
        c = tot[a]
        c.value, c.font, c.alignment = h, bold, mid
    heads = ["비고", "센터", "순번", "장비명", "구축연도", "NFEC번호", "itube 번호", "구축금액(원)", "가용시간(hr)",
             "가동시간(hr)", "사용횟수", "가동률(%)", "가동시간(hr)", "횟수", "가동률(%)", "가동시간(hr)", "횟수", "가동률(%)"]
    for j, h in enumerate(heads, start=2):
        c = tot.cell(5, j, h)
        c.font, c.alignment = bold, mid
    kids = {r["root"]: sum(1 for x in rws if x["root"] == r["root"] and x["id"] != r["root"]) for r in rws}
    cen = db.equip_centers(eq)
    for k, (rid, sn, ni, no, av, _) in enumerate(sheets, start=1):
        me, rr = info.get(rid, {}), 5 + k
        acq = me.get("acquired_on")
        q = sn.replace("'", "''")
        vals = [f"세부장비 {kids.get(rid, 0)}대 포함" if kids.get(rid) else None, cen.get(rid, "") or None, k,
                to_str(me.get("name")), acq.year if acq is not None and pd.notna(acq) else None, to_str(me.get("nfec")) or None,
                to_str(me.get("code")) or None, None, av, f"=N{rr}+Q{rr}", ni + no, f"=IFERROR(K{rr}/J{rr},0)",
                f"='{q}'!R14", ni, f"=IFERROR(N{rr}/J{rr},0)", f"='{q}'!S14", no, f"=IFERROR(Q{rr}/J{rr},0)"]
        for j, v in enumerate(vals, start=2):
            c = tot.cell(rr, j, v)
            c.font, c.alignment = norm, Alignment(horizontal="left" if j == 5 else "center", vertical="center")
            if j in (13, 16, 19):
                c.number_format = "0.0%"
            elif j in (10, 11, 14, 17):
                c.number_format = "#,##0.0"
    rr = end + 1
    tot.cell(rr, 5, "계").font = bold
    for col in "JKLNOQR":
        tot[f"{col}{rr}"] = f"=SUM({col}{first}:{col}{end})"
    for col, hc in (("M", "K"), ("P", "N"), ("S", "Q")):  # 계 줄도 Σ시간 ÷ Σ가용시간 (장비 KPI 현황과 같게)
        tot[f"{col}{rr}"] = f"=IFERROR({hc}{rr}/J{rr},0)"
        tot[f"{col}{rr}"].number_format = "0.0%"
    for col in "JKNQ":
        tot[f"{col}{rr}"].number_format = "#,##0.0"
    for row in tot.iter_rows(min_row=4, max_row=rr, min_col=2, max_col=19):
        for c in row:
            c.border = box
            if c.row == rr:
                c.font = bold
    for col, wdt in {"A": 4, "B": 14, "C": 8, "D": 6, "E": 39.8, "F": 10.5, "G": 21.9, "H": 13, "I": 13, "J": 11.4,
                     "K": 10.5, "L": 9, "M": 10.8, "N": 10.9, "O": 7, "P": 10, "Q": 11.4, "R": 7, "S": 10}.items():
        tot.column_dimensions[col].width = wdt

    if charger_sheet:  # 충방전기 챔버 현황표 (예전 '충방전기 장비사용 현황표')를 맨 뒤 시트로
        src = load_workbook(io.BytesIO(charger_sheet)).active
        dst = wb.create_sheet("충방전기 챔버")
        for row in src.iter_rows():
            for c in row:
                nc = dst.cell(c.row, c.column, c.value)
                if c.has_style:
                    nc.font, nc.fill, nc.border, nc.alignment = c.font.copy(), c.fill.copy(), c.border.copy(), c.alignment.copy()
        for kk, dim in src.column_dimensions.items():
            dst.column_dimensions[kk].width = dim.width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
