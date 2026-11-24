"""장비 사용 등록 › 장비표 (2026-11-23 사용자): 예전 엑셀처럼 왼쪽 = 장비, 오른쪽 = 날짜.

- 위 버튼으로 시험(환경) · 시험(충방전) · 제조(오창) · 문백 · 분석 중 하나를 고르면 그 장비만 줄로 나옴.
- 칸 = 시간 + 업체 약칭 (업체마다 색), 며칠 이어지는 실적(기간·묶음)은 띠 하나. 같은 장비에서 겹치면 줄이 나뉨.
- 칸을 누르면 오른쪽 입력 카드가 그 장비·날짜로 열림 (있는 실적이면 그 실적). 빈칸 여러 개를 끌면 장기(기간) 입력.
- 기간 실적도 날짜 칸마다 시간+업체 (엑셀처럼). 칸 고르기 → Ctrl+C/V, Delete, Ctrl+Z.
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
MB = "제조(문백)"  # 문백 센터 장비 전체 (제조 라인·충방전기·챔버). 2026-11-24 사용자: 버튼 이름은 제조(문백)
GROUPS = ["시험(환경)", "시험(충방전)", "제조(오창)", MB, "분석"]
GROUP_DOT = {"시험(환경)": "#D97757", "시험(충방전)": "#B0567F", "제조(오창)": "#4A6B5D", MB: "#D4A359",
             "분석": "#7A65A8", "기타": "#A39F96"}
WEEK = "월화수목금토일"
# 업체 색: (글자색, 칸 바탕) 짝. 밝은 종이 바탕에서 서로 구별되는 부드러운 파스텔 + 진한 글자 (업체 이름으로 늘 같은 색)
# 2026-11-23 지시서: 앞 다섯 짝은 시험·제조·분석·교육·지원 색과 같은 계열
PALETTE = ["#9A3412", "#1E4D3B", "#4C3575", "#92400E", "#2C5470", "#8A2E5A",
           "#4A5A1E", "#8A4B12", "#205958", "#6B4528", "#3C3A7A", "#6E5A12"]
_BG = {"#9A3412": "#FDE8E4", "#1E4D3B": "#E6F2EC", "#4C3575": "#EFEBF8", "#92400E": "#FEF3C7", "#2C5470": "#E3EEF5",
       "#8A2E5A": "#F6E3EC", "#4A5A1E": "#EAF1DC", "#8A4B12": "#FCE9D6", "#205958": "#DFF0EF", "#6B4528": "#F1E6DA",
       "#3C3A7A": "#E9E7F6", "#6E5A12": "#F5EDCF", "#3F3D38": "#EAE8E3"}
INNER = "#3F3D38"  # 내부: 배경 #EAE8E3 · 글자 #3F3D38


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
    """화면에 그릴 표 데이터: 날짜 열, 묶음(구분 칸)별 장비 줄, 줄마다 실적(날짜 칸)."""
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
    # 2026-11-24 사용자: 세부장비를 따로 쓸 수 없는 묶음(SMT)은 주장비 한 줄로, 표 맨 아래에
    one = {i for i in order if groups.get(i) == group and root.get(i, i) == i and is_one_row(short.get(i, ""))}
    up = {i: root[i] for i in order if root.get(i) in one and i != root[i]}
    if up and not near.empty:
        near = near.assign(equip_id=near["equip_id"].map(lambda v: up.get(int(v), int(v))))
    with_logs = set(near["equip_id"].astype(int)) if not near.empty else set()
    leaves = set(db.pick_ids(eq, m1))
    ids = [i for i in order if groups.get(i) == group and i not in up and (i in leaves or i in with_logs or i in one)]

    # 구분 칸: 제조는 라인(맨 위 장비), 문백은 라인·충방전기 묶음 + 시험 챔버, 나머지는 센터
    from core import status
    dg = status.device_group(eq, db.load_channels())

    def section(i: int) -> str:
        if i in one:
            return "SMT"
        if group == MB and dg.get(root.get(i, i)) == "시험":
            return "시험 챔버"
        if group.startswith("제조") or group == MB:
            return short.get(root.get(i, i), "")
        return cen.get(i, "") or "기타"  # 2026-11-24 사용자: 센터는 정식 이름으로
    sec_order: list[str] = []
    for i in ids:
        s = section(i)
        if s not in sec_order:
            sec_order.append(s)
    ids.sort(key=lambda i: (i in one, sec_order.index(section(i))))  # 같은 묶음끼리 모음, 한 줄 묶음은 맨 아래

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
            # 날짜별 시간 (기간 실적도 칸마다 보이게; 주말 제외 실적은 주말 칸이 비어 있음)
            if period:
                dd = expand_daily(g, cfg.get("alloc_mode", "spread"))
                per_day = {d.date(): float(h) for d, h in dd.groupby("day")["hours"].sum().items() if h > 0}
            else:
                per_day = {s: hours}
            items_by_eq.setdefault(int(eid), []).append({
                "log": int(first["id"]), "s": s, "e": e, "period": period, "h": hlab, "days": per_day,
                "co": short_company(comp), "full": comp or "내부", "color": company_color(comp),
                "ch": _ch_label(first)})

    # 보이는 날짜: 주말·공휴일 숨기기를 켜도, 하루짜리 실적이 있는 날은 보임
    days = [m0 + dt.timedelta(days=n) for n in range((m1 - m0).days + 1)]
    off = {d for d in days if d.weekday() >= 5 or d in hol}
    if hide_off:
        busy = {it["s"] for v in items_by_eq.values() for it in v if not it["period"]}
        days = [d for d in days if d not in off or d in busy]

    rows = []
    for i in ids:
        its = sorted(items_by_eq.get(i, []), key=lambda it: (it["s"], not it["period"]))
        lanes: list[list[dict]] = []
        for it in its:
            vis = [d for d in days if d in it["days"]]
            if not vis:
                continue
            it = {**it, "vis": set(vis)}
            for ln in lanes:  # 같은 날 겹치는 실적은 줄을 나눔 (한 실적은 늘 같은 줄)
                if all(not (it["vis"] & o["vis"]) for o in ln):
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
        if i in one:
            name = short.get(i, name)  # 표면실장 기술지원 장비(SMT) 한 줄
        elif (group.startswith("제조") or group == MB) and root.get(i, i) == i and any(parent.get(j) == i for j in ids):
            name = "라인 전체" if dg.get(i) == "제조" else "장비 전체"
        rows.append({"id": i, "name": name, "full": short.get(i, str(i)), "parent": sub, "sec": section(i),
                     "lanes": lanes or [[]]})
    return {"days": days, "off": off, "rows": rows, "m0": m0}


GRP_W = 96  # 주장비 칸 너비 (CSS --grpw 와 같게)


def is_one_row(name: str) -> bool:
    """세부장비를 따로 쓰지 않고 주장비 한 줄로만 등록하는 묶음 (SMT)."""
    n = db.to_str(name)
    return "SMT" in n.upper() or "표면실장" in n


def _text_px(t: str, wide: float = 12.5, narrow: float = 7.0) -> float:
    """글자 폭 어림 (한글 12px 글꼴 기준)."""
    return sum(wide if ord(ch) > 0x2E80 else narrow for ch in t)


def _dev_width(rows: list[dict]) -> int:
    """장비 칸 너비 = 이 표에서 가장 긴 이름에 맞춤 (2026-11-24 사용자: 칸이 너무 넓은 곳은 줄이기).
    괄호(사양)는 아랫줄이라 따로 잼. 너무 긴 이름은 줄바꿈 (최대 230px)."""
    has_grp = any(r["parent"] for r in rows)
    need = 0.0
    for r in rows:
        n = r["name"]
        i = n.find("(")
        main, spec = (n[:i].rstrip(), n[i:]) if i > 0 else (n, "")
        w = max(_text_px(main), _text_px(spec, 11, 6.2))
        if has_grp and not r["parent"]:  # 주장비 칸까지 합친 줄은 그만큼 덜 필요
            w -= GRP_W
        need = max(need, w)
    return int(min(230, max(110, need + 24)))


def _name_html(name: str) -> str:
    """괄호(사양)는 한 줄 아래에 작게 (2026-11-24 사용자). 예: 배터리 완제품 활성화 장비 / (5V, 50A, 192ch)"""
    i = name.find("(")
    if i <= 0:
        return html.escape(name)
    return f"{html.escape(name[:i].rstrip())}<span class='spec'>{html.escape(name[i:])}</span>"


def to_html(data: dict, today: dt.date, sel: dict | None) -> str:
    """표 HTML (칸에 data-eid·data-day, 실적에 data-log)."""
    e = html.escape
    days = data["days"]
    rows = data["rows"]
    if not rows:
        return "<div class='eg-empty'>이 구분에는 이번 달에 보일 장비가 없어요.</div>"
    # 2026-11-24 사용자: 같은 주장비 아래 세부장비는 왼쪽에 주장비 이름을 한 번만(셀 병합), 오른쪽에 장비 이름
    has_grp = any(r["parent"] for r in rows)
    h = ["<div class='eg-scroll'><table class='eg" + (" has-grp" if has_grp else "")
         + "'><colgroup><col class='c-sec'>" + ("<col class='c-grp'>" if has_grp else "") + "<col class='c-dev'>"]
    h += ["<col>" for _ in days]
    h.append("</colgroup><thead><tr><th class='sec'>구분</th>"
             + ("<th class='dev wide' colspan='2'>장비</th>" if has_grp else "<th class='dev'>장비</th>"))
    for d in days:
        cls = ("off " if d in data["off"] else "") + ("today" if d == today else "")
        h.append(f"<th class='{cls}'>{d.day}<small>{WEEK[d.weekday()]}</small></th>")
    h.append("</tr></thead><tbody>")  # 합계 열은 뺌 (2026-11-23 사용자: 앱에서는 필요 없음)
    sec_rows: dict[str, int] = {}
    for r in rows:
        sec_rows[r["sec"]] = sec_rows.get(r["sec"], 0) + len(r["lanes"])
    # 주장비 묶음: 같은 구분 안에서 이어지는 같은 주장비 줄들 → 시작 줄 번호: 묶음 줄 수
    grp_span: dict[int, int] = {}
    k = 0
    while k < len(rows):
        j = k
        if rows[k]["parent"]:
            while j + 1 < len(rows) and rows[j + 1]["parent"] == rows[k]["parent"] and rows[j + 1]["sec"] == rows[k]["sec"]:
                j += 1
            grp_span[k] = sum(len(rows[x]["lanes"]) for x in range(k, j + 1))
        k = j + 1
    seen: set[str] = set()
    sel_eid, sel_day, sel_log = (sel or {}).get("eid"), (sel or {}).get("day"), (sel or {}).get("log")
    ri = 0
    for idx, r in enumerate(rows):
        n = len(r["lanes"])
        for li, lane in enumerate(r["lanes"]):
            last = " last" if li == n - 1 else ""
            h.append(f"<tr class='{'first' if li == 0 else ''}{last}' data-ri='{ri}'>")
            ri += 1
            if li == 0 and r["sec"] not in seen:
                seen.add(r["sec"])
                sec_txt = e(r["sec"])
                for tail in ("안전성평가센터", "지원센터"):  # 긴 센터 이름은 두 줄로
                    if sec_txt.endswith(tail) and len(sec_txt) > len(tail) + 1:
                        sec_txt = sec_txt[: -len(tail)] + "<br>" + tail
                        break
                h.append(f"<td class='sec' rowspan='{sec_rows[r['sec']]}'><span>{sec_txt}</span></td>")
            if li == 0:
                if idx in grp_span:
                    h.append(f"<td class='grp' rowspan='{grp_span[idx]}'>{e(r['parent'])}</td>")
                if has_grp and not r["parent"]:
                    h.append(f"<td class='dev wide' colspan='2' rowspan='{n}' title='{e(r['full'])}'>"
                             f"<div class='nm'>{_name_html(r['name'])}</div></td>")
                else:
                    h.append(f"<td class='dev' rowspan='{n}' title='{e(r['full'])}'><div class='nm'>{_name_html(r['name'])}</div></td>")
            at = {d: it for it in lane for d in it["vis"]}
            for ci, d in enumerate(days):
                cls = "off" if d in data["off"] else ""
                it = at.get(d)
                if it is None:
                    s_cls = " sel" if sel_eid == r["id"] and sel_day == d and not sel_log else ""
                    h.append(f"<td class='{cls}{s_cls}' data-eid='{r['id']}' data-day='{d}' data-ci='{ci}'></td>")
                    continue
                c = it["color"]
                # 누른 그 칸만 표시 (기간 실적의 다른 날 칸은 그대로) — 2026-11-24 사용자
                picked = " picked" if sel_log == it["log"] and (sel_day is None or sel_day == d) else ""
                hv = it["days"][d]
                hl = f"{round(hv, 1):g}"
                tip = e(f"{it['full']} · {d:%m/%d} {hl}h" + (f" · {it['s']:%m/%d}~{it['e']:%m/%d}" if it["period"] else "")
                        + (f" · {it['ch']}" if it["ch"] else ""))
                # 기간 실적은 이어지는 칸끼리 붙여 보이게 (왼쪽·오른쪽 이음)
                prev_same = ci > 0 and at.get(days[ci - 1]) is it
                next_same = ci + 1 < len(days) and at.get(days[ci + 1]) is it
                join = (" jl" if prev_same else "") + (" jr" if next_same else "")
                h.append(f"<td class='{cls} has' data-eid='{r['id']}' data-day='{d}' data-ci='{ci}'>"
                         f"<div class='cell{join}{picked}' data-log='{it['log']}' data-day='{d}' title='{tip}' "
                         f"style='background:{_BG.get(c, _rgba(c, .18))};color:{c}'><b>{e(hl)}</b><span>{e(it['co'])}</span></div></td>")
            h.append("</tr>")
    h.append("</tbody></table></div>")
    # 업체 색 안내
    seen_c: dict[str, str] = {}
    for r in rows:
        for lane in r["lanes"]:
            for it in lane:
                seen_c.setdefault(it["co"], it["color"])
    leg = "".join(f"<span><i style='background:{_BG.get(c, c)};box-shadow:inset 0 0 0 1.5px {c}'></i>{e(n)}</span>" for n, c in seen_c.items())
    h.append(f"<div class='eg-foot'><div class='eg-leg'>{leg}</div><div class='eg-note'>칸 고르기(끌기·Shift+클릭) · Ctrl+C / Ctrl+V · Delete · Ctrl+Z</div></div>")
    return "".join(h)


CSS = """
:host{display:block}
.eg-scroll{overflow-x:auto;border:1px solid #E8E6DF;border-radius:14px;background:#FFFFFF}
table.eg{border-collapse:separate;border-spacing:0;table-layout:fixed;width:100%;min-width:var(--minw,900px);
  font-family:inherit;color:#191918}
.eg col.c-sec{width:92px}.eg col.c-dev{width:var(--devw,190px)}.eg col.c-tot{width:58px}
.eg th,.eg td{border-right:1px solid #EAE7DF;border-bottom:1px solid #EAE7DF;text-align:center;padding:0;height:34px;
  font-size:11px;position:relative;box-sizing:border-box}
.eg thead th{background:#F2EFE9;height:42px;font-weight:600;color:#4A4741;font-size:12px;position:sticky;top:0;z-index:3}
.eg thead th small{display:block;font-size:10px;color:#A39F96;font-weight:400}
.eg thead th.off,.eg thead th.off small{color:#C84B31}
.eg thead th.today{background:#D97757;color:#fff}.eg thead th.today small{color:#FDF2EE}
.eg td.off{background:#F7F5F0}
.eg td.sec{background:#FAF9F5;color:#6B6860;font-weight:700;font-size:11.5px;padding:4px 6px;line-height:1.35;word-break:keep-all}
.eg td.dev{text-align:center;padding:0 10px;font-size:12px;background:#FFFFFF}
.eg td.dev .nm{white-space:normal;word-break:keep-all;overflow-wrap:anywhere;line-height:1.25;margin:4px 0}  /* 장비 이름은 다 보이게, 길면 줄바꿈 (2026-11-24 사용자) */
.eg col.c-grp{width:var(--grpw,96px)}
.eg td.dev .nm .spec{display:block;font-size:10.5px;color:#8A867D;margin-top:1px}
.eg td.grp{background:#FAF8F4;color:#6B6860;font-size:10.5px;font-weight:600;line-height:1.3;padding:4px 6px;word-break:keep-all;position:sticky;left:92px;z-index:2}
.eg.has-grp td.dev:not(.wide),.eg.has-grp th.dev:not(.wide){left:calc(92px + var(--grpw,96px))}
.eg td.dev small{display:block;color:#A39F96;font-size:9.5px;line-height:1.1;overflow:hidden;text-overflow:ellipsis}
.eg th.sec,.eg td.sec{position:sticky;left:0;z-index:2}
.eg th.dev,.eg td.dev{position:sticky;left:92px;z-index:2}
.eg thead th.sec,.eg thead th.dev{z-index:4}
.eg td.tot{font-weight:700;background:#F2EFE9;font-size:12px}
.eg td.tot.z{color:#A39F96;font-weight:400}
.eg tbody td[data-eid]{cursor:pointer}
.eg tbody td[data-eid]:hover{background:rgba(217,119,87,.14)}
.eg tbody td.drag{background:rgba(217,119,87,.28)!important}
.eg tbody td.sel{box-shadow:inset 0 0 0 2px #D97757}
.cell{position:absolute;inset:2px;border-radius:5px;display:flex;flex-direction:column;align-items:center;justify-content:center;
  line-height:1.15;cursor:pointer;color:#191918;overflow:hidden}
.cell b{font-size:12px}.cell span{font-size:9px;letter-spacing:-.2px;opacity:.92;white-space:nowrap}
.bar{position:absolute;top:3px;bottom:3px;left:2px;right:2px;border-radius:6px;border-left:3px solid;display:flex;align-items:center;
  gap:6px;padding:0 8px;font-size:11px;white-space:nowrap;overflow:hidden;cursor:pointer;color:#191918}
.bar.cl{border-top-left-radius:0;border-bottom-left-radius:0}.bar.cr{border-top-right-radius:0;border-bottom-right-radius:0}
.bar .d{opacity:.7;font-size:10px}
.cell:hover,.bar:hover{filter:brightness(.96)}
.cell.picked,.bar.picked{outline:2px solid #D97757;outline-offset:-2px}
.cell.jl{left:0;border-top-left-radius:0;border-bottom-left-radius:0}
.cell.jr{right:0;border-top-right-radius:0;border-bottom-right-radius:0}
.eg tbody td.rs{background:rgba(217,119,87,.22)!important}
.eg tbody td.rs .cell{box-shadow:inset 0 0 0 2px #C26344}
.eg tbody td.cp{outline:2px dashed #D97757;outline-offset:-3px}
.eg-tip{font-size:11.5px;color:#A39F96;margin-top:6px}
.eg-foot{display:flex;justify-content:space-between;gap:12px;margin-top:10px;flex-wrap:wrap}
.eg-leg{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#6B6860}
.eg-leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.eg-note{font-size:12px;color:#A39F96}
.eg-empty{padding:40px;text-align:center;color:#6B6860;border:1px dashed #E8E6DF;border-radius:14px}
@media (max-width:640px){
  .eg col.c-sec{width:26px}.eg td.sec{writing-mode:vertical-rl;padding:4px 0;font-size:10px;letter-spacing:.5px}
  .eg th.sec{font-size:0}
  .eg th.dev,.eg td.dev{left:26px}.eg col.c-dev{width:140px}.eg td.grp{left:26px;font-size:10px;padding:3px 4px}.eg col.c-grp{width:64px}.eg.has-grp td.dev:not(.wide),.eg.has-grp th.dev:not(.wide){left:90px}.eg td.dev{padding:0 6px;font-size:11px}
  .eg col.c-tot{width:44px}
  table.eg{min-width:calc(26px + 140px + var(--ndays) * 42px)}.eg.has-grp{min-width:calc(90px + 140px + var(--ndays) * 42px)}
}
"""

JS = r"""
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const W = window;
  let box = parentElement.querySelector('.eg-root');
  if (!box) { box = document.createElement('div'); box.className = 'eg-root'; parentElement.appendChild(box); }
  box.innerHTML = data.html;
  const t = box.querySelector('table.eg');
  if (t) { t.style.setProperty('--ndays', data.ndays); t.style.setProperty('--minw', data.minw + 'px'); t.style.setProperty('--devw', data.devw + 'px'); }
  // 엑셀처럼: 칸 고르기(끌기·Shift+클릭) → Ctrl+C → 다른 칸 누르고 Ctrl+V
  const trs = () => [...box.querySelectorAll('tbody tr[data-ri]')];
  const cellAt = (r, c) => { const tr = trs()[r]; return tr ? tr.querySelector(`td[data-ci="${c}"]`) : null; };
  const pos = (td) => ({r: +td.parentElement.dataset.ri, c: +td.dataset.ci});
  if (W.__egSig !== data.sig) { W.__egSel = null; W.__egSig = data.sig; }
  const paintSel = () => {
    box.querySelectorAll('td.rs').forEach(x => x.classList.remove('rs'));
    const s = W.__egSel; if (!s) return;
    const [r0, r1] = [Math.min(s.a.r, s.b.r), Math.max(s.a.r, s.b.r)], [c0, c1] = [Math.min(s.a.c, s.b.c), Math.max(s.a.c, s.b.c)];
    if (r0 === r1 && c0 === c1) return;  // 한 칸은 노란 테두리(선택)로 이미 보임
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) { const td = cellAt(r, c); if (td) td.classList.add('rs'); }
  };
  const paintClip = () => {
    box.querySelectorAll('td.cp').forEach(x => x.classList.remove('cp'));
    const k = W.__egClip; if (!k || k.sig !== data.sig) return;
    k.items.forEach(it => { const td = box.querySelector(`td[data-day="${it.day}"] .cell[data-log="${it.log}"]`); if (td) td.parentElement.classList.add('cp'); });
  };
  paintSel(); paintClip();
  let down = null, moved = false;
  box.onmousedown = (ev) => {
    W.__egActive = true;
    const td = ev.target.closest('td[data-ci]');
    if (!td || ev.button !== 0) return;
    ev.preventDefault();
    if (ev.shiftKey && W.__egSel) { W.__egSel = {a: W.__egSel.a, b: pos(td)}; paintSel(); return; }
    down = td; moved = false; W.__egSel = {a: pos(td), b: pos(td)}; paintSel();
  };
  box.onmouseover = (ev) => {
    if (!down) return;
    const td = ev.target.closest('td[data-ci]');
    if (td && td !== down) { moved = true; W.__egSel = {a: pos(down), b: pos(td)}; paintSel(); }
  };
  box.onmouseup = (ev) => {
    if (!down) return;
    const a = down; down = null;
    const td = ev.target.closest ? ev.target.closest('td[data-ci]') : null;
    if (!moved) {
      const it = a.querySelector('[data-log]');
      if (it) setTriggerValue('pick', {t: 'log', log: +it.dataset.log, day: it.dataset.day, n: Date.now()});
      else setTriggerValue('pick', {t: 'new', eid: +a.dataset.eid, day: a.dataset.day, n: Date.now()});
      return;
    }
    // 한 줄에서 빈칸만 끌었으면 기간(장기) 입력으로 열기
    if (td && td.parentElement === a.parentElement) {
      const s = W.__egSel, c0 = Math.min(s.a.c, s.b.c), c1 = Math.max(s.a.c, s.b.c);
      let empty = true;
      for (let c = c0; c <= c1; c++) { const x = cellAt(s.a.r, c); if (x && x.querySelector('[data-log]')) empty = false; }
      if (empty) {
        const d = [a.dataset.day, td.dataset.day].sort();
        setTriggerValue('pick', {t: 'range', eid: +a.dataset.eid, d0: d[0], d1: d[1], n: Date.now()});
      }
    }
  };
  if (!W.__egKeys) {
    W.__egKeys = true;
    // 표는 shadow DOM 안에 있어서 문서에서는 composedPath 로 확인
    document.addEventListener('mousedown', (ev) => {
      if (!ev.composedPath().some(n => n && n.classList && n.classList.contains('eg-root'))) W.__egActive = false;
    }, true);
    document.addEventListener('mouseup', () => { if (W.__egUp) W.__egUp(); });
    document.addEventListener('keydown', (ev) => {
      if (!W.__egActive || !W.__egKey) return;
      const tg = ev.target, tag = (tg && tg.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (tg && tg.isContentEditable)) return;
      W.__egKey(ev);
    });
  }
  W.__egUp = () => { down = null; };
  W.__egKey = (ev) => {
    const ctl = ev.ctrlKey || ev.metaKey, k = ev.key.toLowerCase();
    const s = W.__egSel;
    if (k === 'escape') { W.__egClip = null; paintClip(); return; }
    if (ctl && k === 'z') { ev.preventDefault(); setTriggerValue('pick', {t: 'undo', n: Date.now()}); return; }
    if (!s) return;
    const [r0, r1] = [Math.min(s.a.r, s.b.r), Math.max(s.a.r, s.b.r)], [c0, c1] = [Math.min(s.a.c, s.b.c), Math.max(s.a.c, s.b.c)];
    if (k === 'delete' || k === 'backspace') {
      const out = [];
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) {
        const td = cellAt(r, c), it = td && td.querySelector('[data-log]');
        if (it) out.push({log: +it.dataset.log, day: it.dataset.day});
      }
      if (!out.length) return;
      ev.preventDefault();
      setTriggerValue('pick', {t: 'del', items: out, n: Date.now()});
      return;
    }
    if (!ctl) return;
    if (k === 'c') {
      const items = [];
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) {
        const td = cellAt(r, c), it = td && td.querySelector('[data-log]');
        if (it) items.push({dr: r - r0, dc: c - c0, log: +it.dataset.log, day: it.dataset.day});
      }
      if (!items.length) return;
      ev.preventDefault();
      W.__egClip = {sig: data.sig, items}; paintClip();
    } else if (k === 'v') {
      const clip = W.__egClip; if (!clip) return;
      ev.preventDefault();
      const out = [];
      clip.items.forEach(it => {
        const td = cellAt(r0 + it.dr, c0 + it.dc);
        if (td) out.push({log: it.log, src: it.day, eid: +td.dataset.eid, day: td.dataset.day});
      });
      if (out.length) setTriggerValue('pick', {t: 'paste', items: out, n: Date.now()});
    }
  };
}
"""

_COMP = None


def _component():
    global _COMP
    if _COMP is None:
        _COMP = st.components.v2.component("equip_entry_grid", css=CSS, js=JS)
    return _COMP


def _paste(items: list[dict]) -> None:
    """복사한 칸(실적)을 고른 칸에 하루짜리 실적으로 붙여 넣음. 기간 실적은 그날 몫 시간으로.

    이미 같은 장비·같은 날·같은 업체 실적이 있으면 건너뜀 (두 번 붙여 넣어도 겹치지 않게). Ctrl+Z 로 한 번에 되돌림."""
    logs = db.load_logs()
    if logs.empty or not items:
        return
    full = logs.copy()
    full["end_date"] = full["end_date"].fillna(full["start_date"])
    cfg = db.get_settings()
    recs, skipped = [], 0
    for it in items:
        try:
            lid, eid = int(it["log"]), int(it["eid"])
            src_day, day = dt.date.fromisoformat(it["src"]), dt.date.fromisoformat(it["day"])
        except (KeyError, TypeError, ValueError):
            continue
        hit = full[full["id"] == lid]
        if hit.empty:
            continue
        src = hit.iloc[0].to_dict()
        hours = db.to_num(src.get("hours"), 0) or 0
        if per.is_period(src):
            rows = per.series_rows(full, lid)
            dd = expand_daily(rows, cfg.get("alloc_mode", "spread"))
            dd = dd[dd["day"] == pd.Timestamp(src_day)]
            hours = float(dd["hours"].sum()) if not dd.empty else 0
        if hours <= 0:
            continue
        comp = db.to_str(src.get("company"))
        same = full[(full["equip_id"] == eid) & (full["start_date"] <= pd.Timestamp(day))
                    & (full["end_date"] >= pd.Timestamp(day)) & (full["company"].map(db.to_str) == comp)]
        if not same.empty or any(r["equip_id"] == eid and r["start_date"] == day and r["company"] == comp for r in recs):
            skipped += 1
            continue
        rec = {k: src.get(k) for k in db.LOG_FIELDS if k in src}
        rec.update(equip_id=eid, start_date=day, end_date=day, hours=round(hours, 1), fee=0, series="", fee_log="",
                   company=comp)
        if eid != int(src["equip_id"]):  # 다른 장비면 챔버·채널 선택은 가져오지 않음
            rec.update(chambers="", ch_part="")
        recs.append(rec)
    if recs:
        with db.undo_group(f"붙여넣기 {len(recs)}건"):
            db.insert_logs(recs)
        _reset_panel()
        st.toast(f"{len(recs)}건 붙여 넣었어요" + (f" (이미 있는 {skipped}칸은 건너뜀)" if skipped else ""))
    elif skipped:
        st.toast("이미 같은 실적이 있어서 붙여 넣지 않았어요")


def _reset_panel() -> None:
    """실적이 바뀌었으니 오른쪽 입력 카드를 닫고 다시 그림 (지워진 실적을 들고 있지 않게)."""
    for k in ("cal_pick", "cal_picks", "cal_preset"):
        st.session_state.pop(k, None)
    st.session_state.cal_ver = st.session_state.get("cal_ver", 0) + 1
    st.session_state.entry_ver = st.session_state.get("entry_ver", 0) + 1


def _undo(_items=None) -> None:
    """Ctrl+Z: 마지막 저장·삭제·붙여넣기를 되돌림 (최근 30번까지, 달력과 같은 기록)."""
    label = db.undo_last()
    if label:
        _reset_panel()
        st.toast(f"되돌렸어요: {label}")


def _delete(items: list[dict]) -> None:
    """고른 칸의 실적을 지움 (엑셀의 Delete). 기간 실적은 고른 날만 빼고 나머지는 남김 (가운데를 빼면 둘로 나뉨)."""
    logs = db.load_logs()
    if logs.empty or not items:
        return
    full = logs.copy()
    full["end_date"] = full["end_date"].fillna(full["start_date"])
    mode = db.get_settings().get("alloc_mode", "spread")
    # 칸 → 그 날을 가진 실제 행 (묶음 실적은 달마다 한 줄)
    rm: dict[int, set] = {}
    for it in items:
        try:
            lid, day = int(it["log"]), dt.date.fromisoformat(it["day"])
        except (KeyError, TypeError, ValueError):
            continue
        rows = per.series_rows(full, lid)
        ts = pd.Timestamp(day)
        hit = rows[(rows["start_date"] <= ts) & (rows["end_date"] >= ts)]
        if hit.empty:
            continue
        rm.setdefault(int(hit.iloc[0]["id"]), set()).add(day)
    if not rm:
        return
    dels, upd, adds = [], {}, []
    for rid, days in rm.items():
        row = full[full["id"] == rid]
        r = row.iloc[0].to_dict()
        dd = expand_daily(row, mode)
        dd = dd[dd["hours"] > 0] if (dd["hours"] > 0).any() else dd
        all_days = [d.date() for d in dd["day"]]
        hours = dict(zip(all_days, dd["hours"].astype(float)))
        fees = dict(zip(all_days, dd["fee"].astype(float)))
        keep = [d for d in all_days if d not in days]
        if not keep:
            dels.append(rid)
            continue
        runs, cur = [], [keep[0]]
        for d in keep[1:]:  # 지운 날이 사이에 있으면 끊김
            between = [x for x in all_days if cur[-1] < x < d]
            if any(x in days for x in between):
                runs.append(cur)
                cur = [d]
            else:
                cur.append(d)
        runs.append(cur)
        pieces = [{"start_date": rr[0], "end_date": rr[-1], "hours": round(sum(hours[x] for x in rr), 1),
                   "fee": round(sum(fees[x] for x in rr))} for rr in runs]
        base = {k: r.get(k) for k in db.LOG_FIELDS if k in r}
        upd[rid] = base | pieces[0]
        adds += [base | p for p in pieces[1:]]
    db.precheck("usage", upd, dels)  # 일부만 지워지는 일이 없게 먼저 확인
    with db.undo_group(f"칸 지우기 {len(items)}칸"):
        if upd:
            db.update_logs(upd)
        if adds:
            db.insert_logs(adds)
        if dels:
            db.delete_logs(dels)
    _reset_panel()
    st.toast(f"{len(items)}칸 지웠어요 · Ctrl+Z로 되돌리기")


def _on_pick() -> None:
    """표에서 누른 것 → 오른쪽 입력 카드 (views.calendar_entry 의 cal_* 상태를 그대로 씀)."""
    st_obj = st.session_state.get("eg_grid")
    ev = getattr(st_obj, "pick", None) if st_obj is not None else None
    if ev is None and isinstance(st_obj, dict):
        ev = st_obj.get("pick")
    if not ev:
        return
    if ev.get("t") in ("paste", "del", "undo"):
        {"paste": _paste, "del": _delete, "undo": _undo}[ev["t"]](ev.get("items") or [])
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
            # 예전 버튼 이름(제조(문백) 등)이 남아 있으면 첫 버튼으로
            old = {"문백": MB}.get(st.session_state.get("eg_last"))  # 이름만 바뀐 버튼은 그 버튼으로
            if old:
                st.session_state["eg_last"] = old
            if st.session_state.get("eg_last") not in opts:
                st.session_state["eg_last"] = GROUPS[0]
            if st.session_state.get("eg_grp") not in opts:
                st.session_state.pop("eg_grp", None)
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
                sel = {"log": int(pick["id"]), "day": pick.get("day")}
            elif pre:
                sel = {"eid": pre["eq"], "day": st.session_state.get("cal_day")}
        nd = len(data["days"])
        devw = _dev_width(data["rows"])
        _component()(data={"html": to_html(data, dt.date.today(), sel), "ndays": nd, "sig": f"{g}|{month:%Y-%m}|{hide}",
                           "minw": 92 + devw + nd * 34 + 96, "devw": devw},
                     key="eg_grid", on_pick_change=_on_pick)
