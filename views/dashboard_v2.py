"""장비 KPI 현황 다시 설계 시안 (2026-11-22, EQUIP_KPI_V2=1 일 때만). 숫자는 기존 화면과 같은 계산을 그대로 씀.

- 맨 위: '목표 대비 지금' 두 칸 (가동률 · 수수료). 배터리 모양 게이지 + 목표 눈금 + 달성률.
- 그 아래 얇은 한 줄: 유지보수 · 장비 종·대수 (보조 정보).
- 쪽 제목과 영역 제목의 장식(아이콘 타일 · 꼬리표 · 그라데이션 밑줄)은 이 화면에서 뺌.
"""
import html

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
.st-key-dsec_util {--sc: #3B82F6;} .st-key-dsec_fee {--sc: #10B981;}
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
.bat .goal {position: absolute; background: none; border-radius: 0; padding: 0; margin: 0; box-shadow: none; top: -9px; bottom: -9px; width: 0; border-left: 2px dashed var(--ink); opacity: .75;}
.bat .goal em {font-style: normal; position: absolute; top: -20px; left: 0; transform: translateX(-50%); font-size: 12px; font-weight: 700;
  color: var(--ink); white-space: nowrap;}
.kc .meta {display: flex; justify-content: center; gap: 28px; margin-top: 18px; font-size: 15px; color: var(--muted);}
.kc .meta b {display: block; font-size: 22px; color: var(--ink); font-weight: 800; margin-top: 2px;}
.kc .meta b.hit {color: var(--c);}

/* 보조 정보 한 줄 */
.ks {display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 0 0 18px;}
.ks > div {background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 12px 18px;
  display: flex; align-items: center; justify-content: center; gap: 22px; font-variant-numeric: tabular-nums; min-height: 64px;}
.ks .t {font-size: 14px; font-weight: 700; color: var(--muted); white-space: nowrap;}
.ks .v {font-size: 22px; font-weight: 800; color: var(--c); white-space: nowrap;}
.ks .v small {font-size: 14px; font-weight: 700; margin-left: 1px;}
.ks .mm {display: grid; grid-template-columns: repeat(12, 22px); gap: 2px; font-size: 11px; text-align: center;}
.ks .mm b {display: block; height: 20px; border-radius: 4px; line-height: 20px; color: var(--ink);
  background: color-mix(in srgb, #F59E0B calc(var(--a) * 1%), transparent);}
.ks .mm b.z {color: var(--dim); background: transparent;}
.ks .mm span {color: var(--dim);}
.ks .cs {display: flex; gap: 18px; font-size: 13px; color: var(--muted);}
.ks .cs b {display: block; font-size: 15px; color: var(--ink);}
@media (max-width: 900px) {.kh, .ks {grid-template-columns: 1fr; gap: 10px;}}
@media (max-width: 640px) {
  .kc {padding: 12px 14px 12px; border-radius: 14px;} .kc .lb {font-size: 14px;} .kc .num {font-size: 34px; margin: 2px 0 20px;}
  .kc .num small {font-size: 18px;} .bat .cell {height: 22px; border-radius: 8px;} .bat .fill {border-radius: 4px;}
  .kc .meta {gap: 6px; font-size: 13px; margin-top: 10px;} .kc .meta > div {display: flex; gap: 5px; align-items: baseline;}
  .kc .meta b {display: inline; font-size: 15px; margin: 0;} 
  .ks > div {flex-direction: column; gap: 6px; padding: 10px;} .ks .mm {grid-template-columns: repeat(12, 1fr); width: 100%;}
  .ks .cs {gap: 10px; font-size: 11.5px;}}
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
    c1 = (f'<div class="kc" style="--c:#3B82F6"><div class="lb">{E(w(f"{year}년 가동률"))}</div>'
          f'<div class="num">{u:.1f}<small>%</small></div>'
          + _gauge("#3B82F6", u, gu, 100, f"목표 {gu:.0f}%")
          + f'<div class="meta"><div>달성률<b class="{"hit" if ur and ur >= 100 else ""}">'
          f'{f"{ur:.1f}%" if ur is not None else "–"}</b></div></div></div>')
    c2 = (f'<div class="kc" style="--c:#10B981"><div class="lb">{year}년 수수료</div>'
          f'<div class="num">{won_short(fee)}</div>'
          + _gauge("#10B981", fee, gf, max(gf * 1.25, fee * 1.04, 1), f"목표 {eok(gf)}")
          + f'<div class="meta"><div>달성률<b class="{"hit" if fr and fr >= 100 else ""}">'
          f'{f"{fr:.1f}%" if fr is not None else "–"}</b></div></div></div>')
    mt = db.load_maint()
    mt = mt[mt["date"].map(lambda d: bool(d) and d.year == year)] if not mt.empty else mt
    by_m = mt.groupby(mt["date"].map(lambda d: d.month)).size().to_dict() if not mt.empty else {}
    top_m = max(by_m.values() or [1])
    mini = "".join(f'<div><b class="{"" if by_m.get(m) else "z"}" style="--a:{int(12 + 38 * by_m.get(m, 0) / top_m)}">'
                   f'{by_m.get(m, 0)}</b><span>{m}</span></div>' for m in range(1, 13))
    blocks, _ = count_summary(db.load_equipment(full=True))
    rows = dict(blocks)["센터별"].to_dict("records")
    tot = next((r for r in rows if r["센터"] == "합계"), None)
    cs = "".join(f'<div>{E(db.center_short(r["센터"]) or r["센터"])}<b>{r["종"]}종 {r["대수"]}대</b></div>'
                 for r in rows if r["센터"] != "합계")
    s1 = (f'<div style="--c:#F59E0B"><span class="t">유지보수</span><span class="v">{len(mt)}<small>건</small></span>'
          f'<div class="mm">{mini}</div></div>')
    s2 = (f'<div style="--c:#8B5CF6"><span class="t">장비</span>'
          f'<span class="v">{tot["종"] if tot else 0}<small>종</small> {tot["대수"] if tot else 0}<small>대</small></span>'
          f'<div class="cs">{cs}</div></div>')
    st.markdown(CSS + f'<div class="kh">{c1}{c2}</div><div class="ks">{s1}{s2}</div>', unsafe_allow_html=True)
