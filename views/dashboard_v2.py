"""장비 KPI 현황 다시 설계 시안 (2026-11-22 시안, 2026-11-23 적용). 숫자는 기존 화면과 같은 계산을 그대로 씀.

- 맨 위: '목표 대비 지금' 두 칸 (가동률 · 수수료). 배터리 모양 게이지 + 목표 눈금 + 달성률.
- 그 아래 얇은 한 줄: 유지보수 · 장비 종·대수 (보조 정보).
- 쪽 제목과 영역 제목의 장식(아이콘 타일 · 꼬리표 · 그라데이션 밑줄)은 이 화면에서 뺌.
"""
import datetime as dt
import html

import pandas as pd

import streamlit as st

from core import db
from core.terms import w

E = html.escape

CSS = """<style>
/* 제목 장식 줄이기 */
.ph2 .ic, .ph2 .eb2, .ph2::after {display: none !important;}
.ph2 {padding-bottom: 6px !important; margin-bottom: 6px !important; border-bottom: 0 !important;}
.dh .ic {display: none !important;}
.dh .tt {font-size: 19px !important;}
.dh .tt::before {content: ''; display: inline-block; width: 10px; height: 10px; border-radius: 3px; background: var(--sc);
  margin-right: 10px; vertical-align: 2px;}
.st-key-dsec_util {--sc: #D97757;} .st-key-dsec_fee {--sc: #4A6B5D;}
[class*="st-key-dsec_"] {border-top-width: 1px !important;}
.st-key-dsec_util, .st-key-dsec_fee {border-top-color: var(--line) !important;}
.dct {border-left: 0 !important; padding-left: 0 !important; color: var(--muted) !important; font-weight: 700 !important;}

/* 목표 대비 지금 */
.kh {display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 6px 0 12px;}
.kc {background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 22px 28px 20px; text-align: center;
  font-variant-numeric: tabular-nums;}
.kc .lb {font-size: 17px; font-weight: 700; color: var(--ink);}
.kc .num {font-size: 54px; font-weight: 800; letter-spacing: -.03em; line-height: 1.05; color: var(--c); margin: 8px 0 30px;}
.kc .num small {font-size: 28px; font-weight: 700; margin-left: 2px;}
.bat {position: relative; display: flex; align-items: center; max-width: 560px; margin: 0 auto;}
.bat .cell {position: relative; flex: 1; height: 34px; border: 2px solid color-mix(in srgb, var(--c) 55%, var(--line));
  border-radius: 10px; padding: 3px; box-sizing: border-box;}
.bat .fill {height: 100%; border-radius: 6px; background: var(--c);
  -webkit-mask: repeating-linear-gradient(90deg, #000 0 calc(10% - 3px), transparent calc(10% - 3px) 10%);
          mask: repeating-linear-gradient(90deg, #000 0 calc(10% - 3px), transparent calc(10% - 3px) 10%);
  mask-size: var(--ms) 100%; -webkit-mask-size: var(--ms) 100%;}
.bat .cap {width: 6px; height: 14px; margin-left: 3px; border-radius: 0 4px 4px 0;
  background: color-mix(in srgb, var(--c) 55%, var(--line));}
.bat .goal {position: absolute; background: none; border-radius: 0; padding: 0; margin: 0; box-shadow: none; top: -9px; bottom: -9px; width: 0; border-left: 2px dashed #6B6860; opacity: .9;}
.bat .goal em {font-style: normal; position: absolute; top: -20px; left: 0; transform: translateX(-50%); font-size: 12px; font-weight: 700;
  color: #6B6860; white-space: nowrap;}
.kc .meta {display: flex; justify-content: center; gap: 28px; margin-top: 18px; font-size: 15px; color: var(--muted);}
.kc .meta b {display: block; font-size: 22px; color: var(--ink); font-weight: 800; margin-top: 2px;}
.kc .meta b.hit {color: var(--c);}

/* 보조 정보 한 줄: 같은 크기 칸으로 나눔 (2026-11-23 사용자 B안) */
.ks {display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 0 0 18px;}
.ks > div {display: grid; grid-template-columns: repeat(var(--n), 1fr); background: var(--panel); border: 1px solid var(--line);
  border-radius: 14px; overflow: hidden; font-variant-numeric: tabular-nums; min-height: 92px;}
.ks .cl {display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; padding: 10px 6px;
  border-left: 1px solid var(--line); min-width: 0;}
.ks .cl:first-child {border-left: 0; background: var(--cb);}
.ks .t {font-size: 13px; font-weight: 700; color: var(--muted); white-space: nowrap;}
.ks .v {font-size: 24px; font-weight: 800; color: var(--ink); white-space: nowrap; line-height: 1.2;}
.ks .v small {font-size: 12.5px; font-weight: 600; color: var(--muted); margin: 0 3px 0 1px;}
.ks .cl:first-child .v, .ks .cl:first-child .v small {color: var(--c);} .ks .cl:first-child .v {font-size: 28px;}
.ks .v.d {font-size: 17px;}
.ks .s {font-size: 11.5px; color: var(--muted); max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
@media (max-width: 900px) {.kh, .ks {grid-template-columns: 1fr; gap: 10px;}}
@media (max-width: 640px) {
  .kc {padding: 12px 14px 12px; border-radius: 14px;} .kc .lb {font-size: 14px;} .kc .num {font-size: 34px; margin: 2px 0 20px;}
  .kc .num small {font-size: 18px;} .bat .cell {height: 22px; border-radius: 8px;} .bat .fill {border-radius: 4px;}
  .kc .meta {gap: 6px; font-size: 13px; margin-top: 10px;} .kc .meta > div {display: flex; gap: 5px; align-items: baseline;}
  .kc .meta b {display: inline; font-size: 15px; margin: 0;} 
  .ks > div {min-height: 76px;} .ks .cl {padding: 8px 3px;} .ks .t {font-size: 11px; letter-spacing: -.02em;} .ks .v {font-size: 17px;}
  .ks .cl:first-child .v {font-size: 19px;} .ks .v small {font-size: 11px; margin: 0 1px;} .ks .v.d {font-size: 14px;} .ks .s {font-size: 10.5px;}}
</style>"""


def _gauge(color: str, value: float, goal: float, scale: float, goal_label: str) -> str:
    pct = max(0.0, min(100.0, value / scale * 100)) if scale else 0
    g = max(0.0, min(100.0, goal / scale * 100)) if scale else 0
    # mask 는 칸(10%) 무늬를 게이지 전체 기준으로 맞추려고 fill 너비의 역수만큼 키움
    ms = f"{100 / pct * 100:.1f}%" if pct else "100%"
    goal_html = (f'<span class="goal" style="left:calc(3px + (100% - 6px) * {g / 100:.4f})"><em>{E(goal_label)}</em></span>'
                 if goal else "")
    return (f'<div class="bat"><div class="cell"><div class="fill" style="width:{pct:.2f}%;--ms:{ms}"></div>{goal_html}</div>'
            f'<div class="cap"></div></div>')


def top(year: int, y_tot: dict, kpi: dict, fee: float, eok, won_short) -> None:
    from views.equipment import count_summary
    gu, gf = float(kpi["util_total"] or 0), float(kpi["fee"] or 0)
    u = float(y_tot["util"] or 0)
    ur = u / gu * 100 if gu else None
    fr = fee / gf * 100 if gf else None
    c1 = (f'<div class="kc" style="--c:#D97757"><div class="lb">{E(w(f"{year}년 가동률"))}</div>'
          f'<div class="num">{u:.1f}<small>%</small></div>'
          + _gauge("#D97757", u, gu, 100, f"목표 {gu:.0f}%")
          + f'<div class="meta"><div>달성률<b class="{"hit" if ur and ur >= 100 else ""}">'
          f'{f"{ur:.1f}%" if ur is not None else "–"}</b></div></div></div>')
    c2 = (f'<div class="kc" style="--c:#4A6B5D"><div class="lb">{year}년 수수료</div>'
          f'<div class="num">{won_short(fee)}</div>'
          + _gauge("#4A6B5D", fee, gf, max(gf * 1.25, fee * 1.04, 1), f"목표 {eok(gf)}")
          + f'<div class="meta"><div>달성률<b class="{"hit" if fr and fr >= 100 else ""}">'
          f'{f"{fr:.1f}%" if fr is not None else "–"}</b></div></div></div>')
    eq = db.load_equipment(full=True)
    names = dict(zip(eq["id"].astype(int), eq["name"]))
    mt = db.load_maint()  # 최근 날짜부터
    mt = mt[mt["date"].map(bool)] if not mt.empty else mt
    today = dt.date.today()
    rm = today.month if year == today.year else 12  # 기준 달 (지난 해를 보면 12월)
    pm_y, pm = (year, rm - 1) if rm > 1 else (year - 1, 12)
    n_of = (lambda y, m: int(mt["date"].map(lambda d: d.year == y and d.month == m).sum())) if not mt.empty else (lambda y, m: 0)
    yr = mt[mt["date"].map(lambda d: d.year == year)] if not mt.empty else mt
    if len(yr):
        r0 = yr.iloc[0]
        eid = r0["equip_id"]
        last = (f'<div class="v d">{r0["date"]:%m.%d}</div>'
                f'<div class="s">{E(names.get(int(eid), "") if pd.notna(eid) else (r0["equip_ref"] or ""))}</div>')
    else:
        last = '<div class="v d">—</div><div class="s">아직 없어요</div>'

    def cell(t: str, body: str) -> str:
        return f'<div class="cl"><div class="t">{E(t)}</div>{body}</div>'

    def cnt(n: int) -> str:
        return f'<div class="v">{n}<small>건</small></div>'

    def jd(j, d) -> str:
        return f'<div class="v">{j}<small>종</small>{d}<small>대</small></div>'

    s1 = (f'<div style="--c:#D97757;--cb:#FDF2EE;--n:4">' + cell("유지보수 · 올해" if year == today.year else f"유지보수 · {year}", cnt(len(yr)))
          + cell("이번 달" if year == today.year else "12월", cnt(n_of(year, rm)))
          + cell("지난달" if year == today.year else "11월", cnt(n_of(pm_y, pm))) + cell("최근 기록", last) + '</div>')
    blocks, _ = count_summary(eq)
    rows = dict(blocks)["센터별"].to_dict("records")
    tot = next((r for r in rows if r["센터"] == "합계"), {"종": 0, "대수": 0})
    cs = [r for r in rows if r["센터"] != "합계"]
    s2 = (f'<div style="--c:#4A6B5D;--cb:#EBF2EE;--n:{len(cs) + 1}">' + cell("장비 전체", jd(tot["종"], tot["대수"]))
          + "".join(cell(db.center_short(r["센터"]) or r["센터"], jd(r["종"], r["대수"])) for r in cs) + '</div>')
    st.markdown(CSS + f'<div class="kh">{c1}{c2}</div><div class="ks">{s1}{s2}</div>', unsafe_allow_html=True)
