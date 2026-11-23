"""장비 사용 등록 › 장비표 (2026-11-23 사용자): 예전 엑셀처럼 왼쪽 = 장비, 오른쪽 = 날짜.

- 위 버튼으로 시험(환경) · 시험(충방전) · 제조(오창) · 문백 · 분석 중 하나를 고르면 그 장비만 줄로 나옴.
- 칸 = 시간 + 업체 약칭 (업체마다 색), 며칠 이어지는 실적(기간·묶음)은 띠 하나. 같은 장비에서 겹치면 줄이 나뉨.
- 칸을 누르면 오른쪽 입력 카드가 그 장비·날짜로 열림 (있는 실적이면 그 실적). 빈칸 여러 개를 끌면 장기(기간) 입력.
- 합계 = 가동률(장비 KPI 현황)과 같은 계산 (calc.expand_daily + 충방전기 하루 최대, 주말·공휴일 0).
"""
from __future__ import annotations

import datetime as dt
import html
import re
import zlib

import pandas as pd
import streamlit as st

from core import db
from core import period as per
from core.calc import expand_daily
from core.period import kr_holidays

# 2026-11-23 사용자: 문백 장비(제조 라인 + 충방전기 + 실환경모사·안전시험 챔버)는 예전 문백 엑셀처럼 한 버튼에
MB = "문백"
GROUPS = ["시험(환경)", "시험(충방전)", "제조(오창)", MB, "분석"]
GROUP_DOT = {"시험(환경)": "#F472B6", "시험(충방전)": "#E879F9", "제조(오창)": "#34D399", MB: "#FBBF24",
             "분석": "#A78BFA", "기타": "#94A3B8"}
WEEK = "월화수목금토일"
# 업체 색: 어두운 바탕에서 서로 잘 구별되는 색 (업체 이름으로 늘 같은 색)
PALETTE = ["#F59E0B", "#F43F5E", "#38BDF8", "#10B981", "#A78BFA", "#2DD4BF", "#FB923C", "#E879F9",
           "#84CC16", "#60A5FA", "#F472B6", "#FACC15"]
INNER = "#94A3B8"


def equip_groups(eq: pd.DataFrame) -> dict[int, str]:
    """장비 ID → 버튼. 구분은 장비 가동 현황과 같은 규칙(맨 위 장비를 따름), 제조만 센터로 오창(제조검증·MV)/문백."""
    from core import status
    grp = status.device_group(eq, db.load_channels())
    cen = db.equip_centers(eq)
    root = {int(i): int(r) for i, r in zip(eq["id"], eq["root_id"]) if pd.notna(r) and int(r)} if "root_id" in eq else {}
    out = {}
    for i in eq["id"].astype(int):
        g = grp.get(root.get(i, i), grp.get(i, "기타"))
        if db.center_short(cen.get(i, "")) == "문백":
            out[i] = MB
        elif g == status.CHARGER or grp.get(i) == status.CHARGER:
            out[i] = "시험(충방전)"
        elif g == "제조":
            out[i] = "제조(오창)"
        elif g == "시험":
            out[i] = "시험(환경)"
        elif g == "분석":
            out[i] = "분석"
        else:
            out[i] = "기타"
    return out


def short_company(name: str) -> str:
    """업체 약칭: (주)·주식회사 등을 떼고 앞 다섯 글자 (칸이 좁아서)."""
    n = db.to_str(name)
    if not n:
        return "내부"
    n = re.sub(r"\(주\)|㈜|주식회사|\(재\)|\(사\)|재단법인|사단법인|\(유\)|유한회사", "", n).strip()
    return n[:5] or "내부"


def company_color(name: str) -> str:
    n = db.to_str(name)
    if not n:
        return INNER
    return PALETTE[zlib.crc32(n.encode()) % len(PALETTE)]


def _rgba(c: str, a: float) -> str:
    c = c.lstrip("#")
    return f"rgba({int(c[:2], 16)},{int(c[2:4], 16)},{int(c[4:], 16)},{a})"


def _ch_label(rec: dict) -> str:
    """충방전기 채널 일부를 쓴 실적이면 'n ch' (전체면 빈칸)."""
    part = db.to_str(rec.get("ch_part"))
    if not part:
        return ""
    try:
        from core import chargers
        n = len(chargers.nums(part))
        return f"{n}ch" if n else ""
    except Exception:  # noqa: BLE001 - 표시용이라 못 읽으면 생략
        return ""


def build(eq: pd.DataFrame, logs: pd.DataFrame, cfg: dict, month: dt.date, group: str, hide_off: bool) -> dict:
    """화면에 그릴 표 데이터: 날짜 열, 묶음(구분 칸)별 장비 줄, 줄마다 실적(칸·띠)과 합계."""
    m0 = month.replace(day=1)
    m1 = (m0 + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    ts0, ts1 = pd.Timestamp(m0), pd.Timestamp(m1)
    groups = equip_groups(eq)
    hol = kr_holidays({m0.year})
    order = [int(i) for i in eq["id"]]
    short = dict(zip(eq["id"].astype(int), eq["short"]))
    parent = {int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)} if "parent_id" in eq else {}
    root = {int(i): int(r) for i, r in zip(eq["id"], eq["root_id"]) if pd.notna(r) and int(r)} if "root_id" in eq else {}
    cen = db.equip_centers(eq)

    near = logs[(logs["start_date"] <= ts1) & (logs["end_date"].fillna(logs["start_date"]) >= ts0)] if not logs.empty else logs
    near = near[near["equip_id"].map(lambda v: groups.get(int(v)) == group)] if not near.empty else near
    with_logs = set(near["equip_id"].astype(int)) if not near.empty else set()
    leaves = set(db.pick_ids(eq, m1))
    ids = [i for i in order if groups.get(i) == group and (i in leaves or i in with_logs)]

    # 구분 칸: 제조는 라인(맨 위 장비), 문백은 라인·충방전기 묶음 + 시험 챔버, 나머지는 센터
    from core import status
    dg = status.device_group(eq, db.load_channels())

    def section(i: int) -> str:
        if group == MB and dg.get(root.get(i, i)) == "시험":
            return "시험 챔버"
        if group.startswith("제조") or group == MB:
            return short.get(root.get(i, i), "")
        return db.center_short(cen.get(i, "")) or "기타"
    sec_order: list[str] = []
    for i in ids:
        s = section(i)
        if s not in sec_order:
            sec_order.append(s)
    ids.sort(key=lambda i: sec_order.index(section(i)))  # 같은 묶음끼리 모음 (장비 목록 순서 유지)

    # 실적 → 한 건(묶음ID로 이은 기간 실적은 하나)
    items_by_eq: dict[int, list[dict]] = {}
    if not near.empty:
        lg = near.copy()
        lg["end_date"] = lg["end_date"].fillna(lg["start_date"])
        ser = lg["series"].map(db.to_str) if "series" in lg else pd.Series([""] * len(lg), index=lg.index)
        lg["_k"] = [s or f"#{i}" for s, i in zip(ser, lg["id"])]
        full = logs.copy()
        full["end_date"] = full["end_date"].fillna(full["start_date"])
        for (eid, k), g in lg.groupby(["equip_id", "_k"], sort=False):
            g = g.sort_values("start_date")
            first = g.iloc[0].to_dict()
            allg = per.series_rows(full, int(first["id"])) if k[0] != "#" else g
            s, e = db.to_date(allg["start_date"].min()), db.to_date(allg["end_date"].max())
            period = s != e or k[0] != "#"
            hours = float(pd.to_numeric(g["hours"], errors="coerce").fillna(0).sum())
            if period:
                try:
                    pdh = float(per.per_day_of(allg))
                except Exception:  # noqa: BLE001
                    pdh = 0.0
                hlab = f"{pdh:g}h/일" if pdh else ""
            else:
                hlab = f"{hours:g}"
            comp = db.to_str(first.get("company"))
            items_by_eq.setdefault(int(eid), []).append({
                "log": int(first["id"]), "s": s, "e": e, "period": period, "h": hlab,
                "co": short_company(comp), "full": comp or "내부", "color": company_color(comp),
                "ch": _ch_label(first)})

    # 보이는 날짜: 주말·공휴일 숨기기를 켜도, 하루짜리 실적이 있는 날은 보임
    days = [m0 + dt.timedelta(days=n) for n in range((m1 - m0).days + 1)]
    off = {d for d in days if d.weekday() >= 5 or d in hol}
    if hide_off:
        busy = {it["s"] for v in items_by_eq.values() for it in v if not it["period"]}
        days = [d for d in days if d not in off or d in busy]

    # 합계 = 가동률과 같은 계산
    capped = expand_daily(near, cfg.get("alloc_mode", "spread"), db.charger_caps()) if not near.empty else None
    tot: dict[int, float] = {}
    if capped is not None and not capped.empty:
        cm = capped[(capped["day"] >= ts0) & (capped["day"] <= ts1)]
        tot = {int(k): float(v) for k, v in cm.groupby("equip_id")["hours"].sum().items()}

    rows = []
    for i in ids:
        its = sorted(items_by_eq.get(i, []), key=lambda it: (it["s"], not it["period"]))
        lanes: list[list[dict]] = []
        for it in its:
            vis = [d for d in days if it["s"] <= d <= it["e"]]
            if not vis:
                continue
            it = {**it, "d0": vis[0], "d1": vis[-1], "n": len(vis)}
            for ln in lanes:
                if all(it["d0"] > o["d1"] or it["d1"] < o["d0"] for o in ln):
                    ln.append(it)
                    break
            else:
                lanes.append([it])
        p = parent.get(i)
        name = re.sub(r"\s*\+\s*챔버.*$", "", short.get(i, str(i)))  # '…+챔버 3대(문백#1~#3)' 는 줄 이름에서 뺌
        name = re.sub(r"\s·\s(문백|오창|제조검증|MV)$", "", name)  # 센터별로 나눈 표라 같은 이름 구분용 꼬리는 뺌
        sub = short.get(p, "") if p is not None and not group.startswith("제조") and group != MB else ""
        if sub and sub in name:
            sub = ""
        if (group.startswith("제조") or group == MB) and root.get(i, i) == i and any(parent.get(j) == i for j in ids):
            name = "라인 전체" if dg.get(i) == "제조" else "장비 전체"
        rows.append({"id": i, "name": name, "full": short.get(i, str(i)), "parent": sub, "sec": section(i),
                     "lanes": lanes or [[]], "total": round(tot.get(i, 0.0), 1)})
    return {"days": days, "off": off, "rows": rows, "m0": m0}


def to_html(data: dict, today: dt.date, sel: dict | None) -> str:
    """표 HTML (칸에 data-eid·data-day, 실적에 data-log)."""
    e = html.escape
    days = data["days"]
    rows = data["rows"]
    if not rows:
        return "<div class='eg-empty'>이 구분에는 이번 달에 보일 장비가 없어요.</div>"
    h = ["<div class='eg-scroll'><table class='eg'><colgroup><col class='c-sec'><col class='c-dev'>"]
    h += ["<col>" for _ in days]
    h.append("<col class='c-tot'></colgroup><thead><tr><th class='sec'>구분</th><th class='dev'>장비</th>")
    for d in days:
        cls = ("off " if d in data["off"] else "") + ("today" if d == today else "")
        h.append(f"<th class='{cls}'>{d.day}<small>{WEEK[d.weekday()]}</small></th>")
    h.append("<th class='tot'>합계</th></tr></thead><tbody>")
    sec_rows: dict[str, int] = {}
    for r in rows:
        sec_rows[r["sec"]] = sec_rows.get(r["sec"], 0) + len(r["lanes"])
    seen: set[str] = set()
    sel_eid, sel_day, sel_log = (sel or {}).get("eid"), (sel or {}).get("day"), (sel or {}).get("log")
    for r in rows:
        n = len(r["lanes"])
        for li, lane in enumerate(r["lanes"]):
            last = " last" if li == n - 1 else ""
            h.append(f"<tr class='{'first' if li == 0 else ''}{last}'>")
            if li == 0 and r["sec"] not in seen:
                seen.add(r["sec"])
                h.append(f"<td class='sec' rowspan='{sec_rows[r['sec']]}'><span>{e(r['sec'])}</span></td>")
            if li == 0:
                par = f"<small>{e(r['parent'])}</small>" if r["parent"] else ""
                h.append(f"<td class='dev' rowspan='{n}' title='{e(r['full'])}'><div class='nm'>{e(r['name'])}</div>{par}</td>")
            starts = {it["d0"]: it for it in lane}
            skip = 0
            for d in days:
                if skip:
                    skip -= 1
                    continue
                cls = "off" if d in data["off"] else ""
                it = starts.get(d)
                if it is None:
                    s_cls = " sel" if sel_eid == r["id"] and sel_day == d and not sel_log else ""
                    h.append(f"<td class='{cls}{s_cls}' data-eid='{r['id']}' data-day='{d}'></td>")
                    continue
                span = it["n"]
                skip = span - 1
                c = it["color"]
                picked = " picked" if sel_log == it["log"] else ""
                tip = e(f"{it['full']} · {it['s']:%m/%d}" + (f"~{it['e']:%m/%d}" if it["period"] else "")
                        + (f" · {it['h']}" + ("h" if not it["period"] else "")))
                if it["period"]:
                    bits = [f"<b>{e(it['co'])}</b>"]
                    if span >= 3:
                        bits.append(f"<span>{e(' · '.join(x for x in (it['ch'], it['h']) if x))}</span>")
                    if span >= 6:
                        bits.append(f"<span class='d'>{it['s'].month}/{it['s'].day}~{it['e'].month}/{it['e'].day}</span>")
                    cont = (" cl" if it["s"] < it["d0"] else "") + (" cr" if it["e"] > it["d1"] else "")
                    inner = (f"<div class='bar{cont}{picked}' data-log='{it['log']}' data-day='{it['d0']}' title='{tip}' "
                             f"style='background:{_rgba(c, .30)};border-left-color:{c}'>{''.join(bits)}</div>")
                else:
                    inner = (f"<div class='cell{picked}' data-log='{it['log']}' data-day='{it['d0']}' title='{tip}' "
                             f"style='background:{_rgba(c, .32)}'><b>{e(it['h'])}</b><span>{e(it['co'])}</span></div>")
                h.append(f"<td class='{cls} has' colspan='{span}'>{inner}</td>")
            if li == 0:
                t = r["total"]
                h.append(f"<td class='tot{' z' if not t else ''}' rowspan='{n}'>{t:g}</td>")
            h.append("</tr>")
    h.append("</tbody></table></div>")
    # 업체 색 안내
    seen_c: dict[str, str] = {}
    for r in rows:
        for lane in r["lanes"]:
            for it in lane:
                seen_c.setdefault(it["co"], it["color"])
    leg = "".join(f"<span><i style='background:{c}'></i>{e(n)}</span>" for n, c in seen_c.items())
    h.append(f"<div class='eg-foot'><div class='eg-leg'>{leg}</div><div class='eg-note'>합계 = 가동률 계산과 같음</div></div>")
    return "".join(h)


CSS = """
:host{display:block}
.eg-scroll{overflow-x:auto;border:1px solid #334155;border-radius:14px;background:#1E293B}
table.eg{border-collapse:separate;border-spacing:0;table-layout:fixed;width:100%;min-width:var(--minw,900px);
  font-family:inherit;color:#E2E8F0}
.eg col.c-sec{width:92px}.eg col.c-dev{width:var(--devw,190px)}.eg col.c-tot{width:58px}
.eg th,.eg td{border-right:1px solid #334155;border-bottom:1px solid #334155;text-align:center;padding:0;height:34px;
  font-size:11px;position:relative;box-sizing:border-box}
.eg thead th{background:#162032;height:42px;font-weight:600;color:#CBD5E1;font-size:12px;position:sticky;top:0;z-index:3}
.eg thead th small{display:block;font-size:10px;color:#64748B;font-weight:400}
.eg thead th.off,.eg thead th.off small{color:#F87171}
.eg thead th.today{background:#312E81;color:#fff}.eg thead th.today small{color:#C7D2FE}
.eg td.off{background:rgba(15,23,42,.38)}
.eg td.sec{background:#162032;color:#FBBF24;font-weight:700;font-size:11.5px;padding:4px 6px;line-height:1.35;word-break:keep-all}
.eg td.dev{text-align:left;padding:0 10px;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:#1A2436}
.eg td.dev .nm{overflow:hidden;text-overflow:ellipsis}
.eg td.dev small{display:block;color:#64748B;font-size:9.5px;line-height:1.1;overflow:hidden;text-overflow:ellipsis}
.eg th.sec,.eg td.sec{position:sticky;left:0;z-index:2}
.eg th.dev,.eg td.dev{position:sticky;left:92px;z-index:2}
.eg thead th.sec,.eg thead th.dev{z-index:4}
.eg td.tot{font-weight:700;background:#162032;font-size:12px}
.eg td.tot.z{color:#475569;font-weight:400}
.eg tbody td[data-eid]{cursor:pointer}
.eg tbody td[data-eid]:hover{background:rgba(99,102,241,.14)}
.eg tbody td.drag{background:rgba(99,102,241,.28)!important}
.eg tbody td.sel{box-shadow:inset 0 0 0 2px #FCD34D}
.cell{position:absolute;inset:2px;border-radius:5px;display:flex;flex-direction:column;align-items:center;justify-content:center;
  line-height:1.15;cursor:pointer;color:#F8FAFC;overflow:hidden}
.cell b{font-size:12px}.cell span{font-size:9px;letter-spacing:-.2px;opacity:.92;white-space:nowrap}
.bar{position:absolute;top:3px;bottom:3px;left:2px;right:2px;border-radius:6px;border-left:3px solid;display:flex;align-items:center;
  gap:6px;padding:0 8px;font-size:11px;white-space:nowrap;overflow:hidden;cursor:pointer;color:#F1F5F9}
.bar.cl{border-top-left-radius:0;border-bottom-left-radius:0}.bar.cr{border-top-right-radius:0;border-bottom-right-radius:0}
.bar .d{opacity:.7;font-size:10px}
.cell:hover,.bar:hover{filter:brightness(1.18)}
.cell.picked,.bar.picked{outline:2px solid #FCD34D;outline-offset:-2px}
.eg-foot{display:flex;justify-content:space-between;gap:12px;margin-top:10px;flex-wrap:wrap}
.eg-leg{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#94A3B8}
.eg-leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.eg-note{font-size:12px;color:#64748B}
.eg-empty{padding:40px;text-align:center;color:#94A3B8;border:1px dashed #334155;border-radius:14px}
@media (max-width:640px){
  .eg col.c-sec{width:26px}.eg td.sec{writing-mode:vertical-rl;padding:4px 0;font-size:10px;letter-spacing:.5px}
  .eg th.sec{font-size:0}
  .eg th.dev,.eg td.dev{left:26px}.eg col.c-dev{width:112px}.eg td.dev{padding:0 6px;font-size:11px}
  .eg col.c-tot{width:44px}
  table.eg{min-width:calc(26px + 112px + 44px + var(--ndays) * 42px)}
}
"""

JS = r"""
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  let box = parentElement.querySelector('.eg-root');
  if (!box) { box = document.createElement('div'); box.className = 'eg-root'; parentElement.appendChild(box); }
  box.innerHTML = data.html;
  const t = box.querySelector('table.eg');
  if (t) { t.style.setProperty('--ndays', data.ndays); t.style.setProperty('--minw', data.minw + 'px'); }
  let down = null, moved = false;
  const clear = () => box.querySelectorAll('td.drag').forEach(x => x.classList.remove('drag'));
  const paint = (a, b) => {
    clear();
    if (!a || !b || a.dataset.eid !== b.dataset.eid) return;
    const tr = a.parentElement, cells = [...tr.querySelectorAll('td[data-eid]')];
    let i = cells.indexOf(a), j = cells.indexOf(b);
    if (i > j) [i, j] = [j, i];
    // 실적이 있는 칸을 건너뛰지 않게: 사이에 실적 칸이 있으면 거기서 멈춤
    for (let k = i; k <= j; k++) cells[k].classList.add('drag');
  };
  box.onmousedown = (ev) => {
    const td = ev.target.closest('td[data-eid]');
    if (!td || ev.button !== 0) return;
    down = td; moved = false; ev.preventDefault();
  };
  box.onmouseover = (ev) => {
    if (!down) return;
    const td = ev.target.closest('td[data-eid]');
    if (td && td !== down) { moved = true; paint(down, td); }
  };
  const up = (ev) => {
    if (!down) return;
    const a = down; down = null;
    const td = ev.target.closest ? ev.target.closest('td[data-eid]') : null;
    if (moved && td && td.dataset.eid === a.dataset.eid && td !== a) {
      const d = [a.dataset.day, td.dataset.day].sort();
      setTriggerValue('pick', {t: 'range', eid: +a.dataset.eid, d0: d[0], d1: d[1], n: Date.now()});
      return;
    }
    clear();
    if (!moved) setTriggerValue('pick', {t: 'new', eid: +a.dataset.eid, day: a.dataset.day, n: Date.now()});
  };
  box.onmouseup = up;
  const docUp = () => { if (down) { down = null; clear(); } };
  document.addEventListener('mouseup', docUp);
  box.onclick = (ev) => {
    const it = ev.target.closest('[data-log]');
    if (it) setTriggerValue('pick', {t: 'log', log: +it.dataset.log, day: it.dataset.day, n: Date.now()});
  };
  return () => document.removeEventListener('mouseup', docUp);
}
"""

_COMP = None


def _component():
    global _COMP
    if _COMP is None:
        _COMP = st.components.v2.component("equip_entry_grid", css=CSS, js=JS)
    return _COMP


def _on_pick() -> None:
    """표에서 누른 것 → 오른쪽 입력 카드 (views.calendar_entry 의 cal_* 상태를 그대로 씀)."""
    st_obj = st.session_state.get("eg_grid")
    ev = getattr(st_obj, "pick", None) if st_obj is not None else None
    if ev is None and isinstance(st_obj, dict):
        ev = st_obj.get("pick")
    if not ev:
        return
    from views import calendar_entry as ce
    ce._clear_sel()
    st.session_state.cal_open = True
    # 입력 카드의 장비 구분·사용목적 기본값도 그 구분으로
    lane = {"시험(환경)": "시험", "시험(충방전)": ce.CHARGER_GROUP, "제조(오창)": "제조",
            "분석": "분석"}.get(st.session_state.get("eg_last", ""))
    if st.session_state.get("eg_last") == MB and ev.get("eid") is not None:  # 문백: 누른 장비의 구분으로
        from core import status
        eq = db.load_equipment()
        g = status.device_group(eq, db.load_channels())
        rt = dict(zip(eq["id"].astype(int), eq["root_id"])) if "root_id" in eq else {}
        r0 = int(rt.get(int(ev["eid"])) or int(ev["eid"]))
        lane = {"시험": "시험", status.CHARGER: ce.CHARGER_GROUP, "제조": "제조", "분석": "분석"}.get(
            g.get(int(ev["eid"])) if g.get(int(ev["eid"])) == status.CHARGER else g.get(r0, g.get(int(ev["eid"]))))
    if lane:
        st.session_state.cal_lane = lane
    else:
        st.session_state.pop("cal_lane", None)
    st.session_state["cal_pv"] = st.session_state.get("cal_pv", 0) + 1
    if ev.get("t") == "log":
        logs = db.load_logs()
        hit = logs[logs["id"] == int(ev["log"])]
        if hit.empty:
            return
        r = hit.iloc[0].to_dict()
        d = dt.date.fromisoformat(ev["day"])
        st.session_state.pop("cal_preset", None)
        st.session_state.cal_pick = {"day": d, "id": int(r["id"]), "rec": r, "period": per.is_period(r),
                                     "label": db.to_str(r.get("company")) or "내부"}
        st.session_state.cal_day = d
    elif ev.get("t") == "range":
        a, b = dt.date.fromisoformat(ev["d0"]), dt.date.fromisoformat(ev["d1"])
        st.session_state.pop("cal_pick", None)
        st.session_state.cal_preset = {"eq": int(ev["eid"]), "mode": "기간", "start": a, "end": b}
        st.session_state.cal_day = a
    else:
        d = dt.date.fromisoformat(ev["day"])
        st.session_state.pop("cal_pick", None)
        st.session_state.cal_preset = {"eq": int(ev["eid"]), "mode": "하루"}
        st.session_state.cal_day = d


def render_grid(container, eq: pd.DataFrame, logs: pd.DataFrame, cfg: dict, month: dt.date) -> None:
    """버튼 줄 + 표 (입력 카드는 calendar_entry.render 가 오른쪽에 그림)."""
    groups = equip_groups(eq)
    leaves = set(db.pick_ids(eq, month))
    cnt = {g: sum(1 for i, v in groups.items() if v == g and i in leaves) for g in GROUPS}
    opts = GROUPS + (["기타"] if any(v == "기타" and i in leaves for i, v in groups.items()) else [])
    with container:
        with st.container(key="eg_top", horizontal=True, vertical_alignment="center", gap="small"):
            g = st.pills("구분", opts, default=st.session_state.get("eg_last", GROUPS[0]), key="eg_grp",
                         label_visibility="collapsed", format_func=lambda x: f"{x}  {cnt.get(x, 0)}대")
            g = g or st.session_state.get("eg_last", GROUPS[0])
            st.session_state["eg_last"] = g
            hide = st.toggle("주말 칸 숨기기", value=True, key="eg_hide")
        dot_css = "".join(
            f'.st-key-eg_grp [data-testid="stButtonGroup"] button:nth-of-type({i}) p::before {{content:"";display:inline-block;'
            f'width:.55em;height:.55em;border-radius:50%;background:{GROUP_DOT[x]};margin-right:.45em;vertical-align:.05em}}'
            for i, x in enumerate(opts, start=1))
        st.markdown(f"<style>{dot_css} .st-key-eg_top{{flex-wrap:wrap}} .st-key-eg_top [data-testid='stToggle']"
                    "{{margin-left:auto}}</style>".replace("{{", "{").replace("}}", "}"), unsafe_allow_html=True)
        data = build(eq, logs, cfg, month, g, hide)
        pick = st.session_state.get("cal_pick")
        pre = st.session_state.get("cal_preset")
        sel = None
        if st.session_state.get("cal_open"):
            if pick:
                sel = {"log": int(pick["id"])}
            elif pre:
                sel = {"eid": pre["eq"], "day": st.session_state.get("cal_day")}
        nd = len(data["days"])
        devw = 190 if g.startswith("제조") else 230
        _component()(data={"html": to_html(data, dt.date.today(), sel), "ndays": nd,
                           "minw": 92 + devw + 58 + nd * 34},
                     key="eg_grid", on_pick_change=_on_pick)
