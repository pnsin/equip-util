"""장비 정보 › 장비 정보: 장비 한 대의 '프로필' — 사진 · 주요 사양 · 자료(링크) · 사용 시 주의 · A/S 연락처.

- 기본 정보(이름 · 번호 · 위치 · 관리자 …)는 '기준 정보 › 장비' 값을 그대로 보여 줌 (두 곳에서 따로 고치지 않게).
- 가동률 숫자는 '현황 › 장비 상세'에 있고, 여기서는 단추로 넘어감.
- 사진은 앱에서 바로 올리면 작게 줄여 구글 시트(장비사진 탭)에 저장 (드라이브 연결 없음).
- 사양 · 자료 표는 고치는 즉시 저장되고, 사이드바 '되돌리기'로 취소할 수 있음.
"""
from __future__ import annotations

import datetime as dt
import html
import re

import pandas as pd
import streamlit as st

from core import db, photos
from core.terms import w
from ui_style import empty_state, page_header
from views import common
from views.common import search_box

GROUP = "장비"
DOC_KINDS = ["설명서", "SOP", "사양서", "교육자료", "점검표", "사진·도면", "기타"]
DOC_TAG = {"설명서": ("PDF", "pink"), "SOP": ("SOP", "blue"), "사양서": ("사양", "green"), "교육자료": ("교육", "purple"),
           "점검표": ("점검", "orange"), "사진·도면": ("도면", "blue"), "기타": ("자료", "gray")}

# ── 장비 친구들: 사진이 없을 때 대신 나오는 그림 (이름으로 고름) ───────────────

_FACE = ('<circle cx="26" cy="{y}" r="2.2" fill="#1E2433"/><circle cx="38" cy="{y}" r="2.2" fill="#1E2433"/>'
         '<path d="M29 {m}c2 1.6 4 1.6 6 0" stroke="#1E2433" stroke-width="1.9" fill="none" stroke-linecap="round"/>')
ICONS = {
    "mix": ("var(--ip1)", '<path d="M14 26h36l-4 22a6 6 0 0 1-6 5H24a6 6 0 0 1-6-5z" fill="#9DB9F5"/>'
                           '<rect x="10" y="22" width="44" height="7" rx="3.5" fill="#7C9FEA"/>'
                           '<path d="M32 8v20" stroke="#5A7BD0" stroke-width="4" stroke-linecap="round"/>'
            + _FACE.format(y=40, m=44)),
    "roll": ("var(--ip2)", '<rect x="8" y="32" width="48" height="20" rx="10" fill="#B9A6F2"/>'
                            '<circle cx="22" cy="22" r="12" fill="#9C86EC"/><circle cx="22" cy="22" r="4" fill="#fff"/>'
                            '<path d="M36 26h16" stroke="#9C86EC" stroke-width="4" stroke-linecap="round"/>'
             + _FACE.format(y=41, m=45)),
    "box": ("var(--ip3)", '<rect x="12" y="10" width="40" height="44" rx="10" fill="#8FD3B4"/>'
                           '<rect x="18" y="16" width="28" height="16" rx="5" fill="#E7F6EF"/>'
                           '<circle cx="44" cy="24" r="2.6" fill="#5DBB91"/>' + _FACE.format(y=41, m=45)),
    "bat": ("var(--ip4)", '<rect x="26" y="6" width="12" height="6" rx="2" fill="#F2B36B"/>'
                           '<rect x="16" y="11" width="32" height="46" rx="10" fill="#F7C68C"/>'
                           '<rect x="21" y="36" width="22" height="15" rx="4" fill="#F2A44D"/>' + _FACE.format(y=25, m=29)),
    "scope": ("var(--ip5)", '<rect x="12" y="50" width="40" height="7" rx="3.5" fill="#F09BB8"/>'
                             '<path d="M22 50V34" stroke="#F09BB8" stroke-width="5" stroke-linecap="round"/>'
                             '<rect x="25" y="6" width="15" height="32" rx="7" fill="#F5B4CA" transform="rotate(-18 32 22)"/>'
                             '<circle cx="45" cy="44" r="7" fill="#F5B4CA"/>'
                             '<circle cx="29.5" cy="19" r="1.9" fill="#1E2433"/><circle cx="36.5" cy="16.8" r="1.9" fill="#1E2433"/>'),
    "gear": ("var(--ip6)", '<circle cx="32" cy="32" r="20" fill="#9FD4E6"/>'
                            '<g fill="#7FC2DA"><rect x="28" y="6" width="8" height="10" rx="3"/><rect x="28" y="48" width="8" height="10" rx="3"/>'
                            '<rect x="6" y="28" width="10" height="8" rx="3"/><rect x="48" y="28" width="10" height="8" rx="3"/></g>'
             + _FACE.format(y=31, m=36)),
}
_RULES = [("bat", "충방전|활성화|에이징|사이클러|cycler|셀 평가|평가"),
          ("scope", "분석|검사|측정|현미경|sem|xrd|ct\\b|tga|dsc|bet|입도|점도|저항"),
          ("mix", "믹서|mixer|교반|슬러리"),
          ("roll", "코터|롤|프레스|슬리터|노칭|스태킹|조립|와인딩|권취|극판|전극"),
          ("box", "챔버|항온|항습|오븐|건조|드라이|초순수|시설|글로브|방폭")]


def _icon_key(text: str) -> str:
    t = text.lower()
    for k, pat in _RULES:
        if re.search(pat, t):
            return k
    return "gear"


def _illust(key: str, size: int = 78) -> str:
    bg, body = ICONS[key]
    return (f"<div class='ii' style='background:{bg};box-shadow:0 0 0 60px {bg}'><svg viewBox='0 0 64 64' width='{size}' height='{size}'>"
            f"{body}</svg></div>")


def _short_loc(loc: str) -> str:
    m = re.search(r"\(([^)]+)\)", loc or "")
    return m.group(1) if m else (loc or "")


CSS = """<style>
:root { --ip1:#EEF0FF; --ip2:#F1ECFF; --ip3:#E7F6EF; --ip4:#FFF2E3; --ip5:#FDEBF1; --ip6:#E6F5FA; }
/* 카드 목록 */
[class*="st-key-iccard_"] {position: relative;}
[class*="st-key-icgo_"] {position: absolute !important; inset: 0; width: 100% !important; height: 100% !important; z-index: 3; margin: 0 !important;}
[class*="st-key-icgo_"] div, [class*="st-key-phgo_"] div {width: 100% !important; height: 100% !important;}
[class*="st-key-icgo_"] button {width: 100% !important; height: 100% !important; opacity: 0; cursor: pointer;}
.ic {background: var(--panel); border: 1px solid var(--line); border-radius: 18px; overflow: hidden;
  box-shadow: var(--card-shadow); transition: transform .15s ease, box-shadow .15s ease;}
[class*="st-key-iccard_"]:hover .ic {transform: translateY(-3px); box-shadow: 0 10px 24px rgba(17,28,46,.10);
  border-color: color-mix(in srgb, var(--accent) 30%, var(--line));}
.ic {margin-bottom: .45rem;}
.ic .icph {height: 128px; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden;}
.ic .icph img {width: 100%; height: 100%; object-fit: cover;}
.ii {position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;}
.ic .bd {padding: .7rem .85rem .8rem;}
.ic .nm {font-weight: 700; font-size: .95rem; line-height: 1.3; color: var(--ink); display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 2.5em;}
.ic .cd {font-size: .75rem; color: var(--accent); margin-top: .15rem; font-variant-numeric: tabular-nums;}
.ic .cd.no {color: var(--dim);}
.ic .wh {font-size: .75rem; color: var(--muted); margin-top: .3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.ic .bs {display: flex; gap: .3rem; margin-top: .55rem; flex-wrap: wrap;}
.bdg {font-size: .7rem; padding: .12rem .55rem; border-radius: 999px; background: var(--panel2); color: var(--muted);}
.bdg.e {background: var(--warn-bg); color: var(--warn);}
.bdg.k {background: var(--accent-bg); color: var(--accent);}
/* 장비 한 대 */
.hero-n {font-size: 1.45rem; font-weight: 700; line-height: 1.3; color: var(--ink);}
.hero-c {color: var(--accent); font-size: .85rem; margin: .2rem 0 .9rem;}
.hero-c .up {color: var(--muted);}
.kv {display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: .6rem 1.1rem; margin-bottom: .6rem;}
.kv div {min-width: 0;} .kv span {display: block; font-size: .72rem; color: var(--muted);}
.kv b {display: block; font-size: .88rem; font-weight: 600; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
.bigph {border-radius: 14px; overflow: hidden; background: var(--panel2); aspect-ratio: 4 / 3;
  display: flex; align-items: center; justify-content: center;}
.bigph img {width: 100%; height: 100%; object-fit: contain; background: #F6F7F9;}
.bigph {position: relative;}
.bigph .ii svg {width: 120px; height: 120px;}
.phcap {font-size: .75rem; color: var(--muted); margin-top: .3rem; text-align: center;}
[class*="st-key-phth_"] {position: relative;}
[class*="st-key-phgo_"] {position: absolute !important; inset: 0; width: 100% !important; height: 100% !important; z-index: 3; margin: 0 !important;}
[class*="st-key-phgo_"] button {width: 100% !important; height: 100% !important; opacity: 0; cursor: pointer;}
.th {aspect-ratio: 4 / 3; border-radius: 9px; overflow: hidden; border: 2px solid transparent; background: var(--panel2);}
.th.on {border-color: var(--accent);}
.th img {width: 100%; height: 100%; object-fit: cover; display: block;}
.st-key-info_up section {padding: .4rem .6rem; border-radius: 12px; border: 1.5px dashed var(--line2); background: var(--deep);}
.st-key-info_up section button {font-size: .8rem;}
.st-key-info_up [data-testid="stFileUploaderDropzoneInstructions"] {display: none;}
.st-key-info_up label p {font-size: .78rem; color: var(--muted);}
.boxh {display: flex; align-items: baseline; justify-content: space-between; gap: .6rem; margin: .1rem 0 .45rem;}
.boxh b {font-size: 1rem; font-weight: 700; color: var(--ink);}
.boxh small {font-size: .74rem; color: var(--dim);}
.doc {display: flex; align-items: center; gap: .7rem; padding: .55rem .2rem; border-bottom: 1px dashed var(--line);
  text-decoration: none !important; color: var(--ink) !important;}
.doc:last-child {border-bottom: none;}
a.doc:hover .t b {color: var(--accent);}
.doc .di {flex: none; width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center;
  justify-content: center; font-size: .66rem; font-weight: 700;}
.di.pink {background: #FDEBF1; color: #C2416E;} .di.blue {background: #EEF0FF; color: #5B6CFF;}
.di.green {background: #E7F6EF; color: #1E8E5A;} .di.purple {background: #F1ECFF; color: #6E4FD0;}
.di.orange {background: #FFF2E3; color: #B5650B;} .di.gray {background: var(--panel2); color: var(--muted);}
.doc .t {flex: 1; min-width: 0;} .doc .t b {display: block; font-size: .88rem; font-weight: 600; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;}
.doc .t small {display: block; font-size: .72rem; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
.doc .go {font-size: .72rem; color: var(--muted); background: var(--panel2); padding: .15rem .6rem; border-radius: 999px;}
.doc.nolink .go {display: none;}
.nodoc {font-size: .82rem; color: var(--dim); padding: .5rem 0 .2rem;}
[class*="st-key-info_caution_"] textarea {background: #FFFBEF !important; border-color: #F3E3B5 !important; line-height: 1.6;}
[class*="st-key-info_contact_"] textarea {line-height: 1.6;}
@media (max-width: 640px) {.ic .icph {height: 104px;}}
</style>"""


# ── 데이터 ────────────────────────────────────────────────────────

def _of(df: pd.DataFrame, eid: int) -> pd.DataFrame:
    return df[df["equip_id"] == str(int(eid))] if not df.empty else df


def _counts(info: dict) -> dict[str, dict[int, int]]:
    out = {}
    for t in ("equip_specs", "equip_docs", "equip_photos"):
        df = info[t]
        vc = pd.to_numeric(df["equip_id"], errors="coerce").dropna().astype(int).value_counts() if not df.empty else {}
        out[t] = dict(vc)
    return out


def _cover(info: dict) -> dict[int, str]:
    ph = info["equip_photos"]
    out: dict[int, str] = {}
    for r in ph.itertuples(index=False):
        try:
            i = int(r.equip_id)
        except ValueError:
            continue
        if i not in out:
            out[i] = r.thumb or r.photo
    return out


def _open(eid: int | None) -> None:
    if eid is None:
        st.query_params.pop("eq", None)
    else:
        st.query_params["eq"] = str(int(eid))


# ── 첫 화면: 카드 목록 ──────────────────────────────────────────────

def _gallery(eq: pd.DataFrame, info: dict) -> None:
    cnt = _counts(info)
    cover = _cover(info)
    kids_of: dict[int, list[str]] = {}
    for r in eq.itertuples(index=False):
        if pd.notna(r.parent_id):
            kids_of.setdefault(int(r.parent_id), []).append(r.name)

    center = common.center_pick("info_center")
    c1, c2 = st.columns([3, 1.1], vertical_alignment="center")
    with c1:
        q = search_box("info_q", "장비명 · ITUBE번호 · 모델명 · 사양으로 찾기")
    with c2:
        view = st.segmented_control("보기", ["카드", "목록"], default="카드", key="info_view",
                                    label_visibility="collapsed") or "카드"
    df = eq[eq["depth"] == 0]  # 세부장비는 장비 한 대 화면에서 봄
    if center:
        cen = db.equip_centers(eq)
        df = df[df["id"].astype(int).map(cen).eq(center)]
    if q:
        spec_txt = (info["equip_specs"].assign(t=lambda d: d["item"] + " " + d["value"])
                    .groupby("equip_id")["t"].agg(" ".join) if not info["equip_specs"].empty else pd.Series(dtype=str))
        hay = (df["name"] + " " + df["code"] + " " + df["model"] + " " + df["species"] + " " + df["maker"] + " "
               + df["manager"] + " " + df["id"].astype(str).map(spec_txt).fillna("")
               + " " + df["id"].map(lambda i: " ".join(kids_of.get(int(i), []))))
        df = df[hay.str.contains(q, case=False, regex=False)]
    if df.empty:
        empty_state("찾는 장비가 없어요", "검색어나 센터 선택을 바꿔 보세요.")
        return

    if view == "목록":
        tbl = pd.DataFrame({
            "id": df["id"].astype(int),
            "장비명": df["name"], "ITUBE번호": df["code"], "대분류": df["group"],
            "위치": df["location"].map(_short_loc), "관리자": df["manager"],
            "사진": df["id"].map(lambda i: cnt["equip_photos"].get(int(i), 0)),
            "사양": df["id"].map(lambda i: cnt["equip_specs"].get(int(i), 0)),
            "자료": df["id"].map(lambda i: cnt["equip_docs"].get(int(i), 0)),
        })
        ev = st.dataframe(tbl, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          column_order=[c for c in tbl.columns if c != "id"], key="info_tbl",
                          height=min(640, 38 + 35 * len(tbl)),
                          column_config={"장비명": st.column_config.TextColumn(width="large")})
        rows = ev.selection.rows if ev and ev.selection else []
        if rows:
            st.session_state.pop("info_tbl", None)
            _open(int(tbl.iloc[rows[0]]["id"]))
            st.rerun()
        st.caption("줄을 누르면 그 장비가 열려요.")
        return

    e = html.escape
    items = list(df.itertuples(index=False))
    per = 4
    for i in range(0, len(items), per):
        cols = st.columns(per)
        for col, r in zip(cols, items[i:i + per]):
            eid = int(r.id)
            img = cover.get(eid)
            ph = (f"<img src='{photos.data_uri(img)}' alt=''>" if img
                  else _illust(_icon_key(r.name + " " + " ".join(kids_of.get(eid, [])))))
            n_doc, n_spec = cnt["equip_docs"].get(eid, 0), cnt["equip_specs"].get(eid, 0)
            bs = ""
            if n_spec:
                bs += f"<span class='bdg'>사양 {n_spec}</span>"
            if n_doc:
                bs += f"<span class='bdg'>자료 {n_doc}</span>"
            if kids_of.get(eid):
                bs += f"<span class='bdg k'>세부 {len(kids_of[eid])}</span>"
            if not (n_doc or n_spec or img):
                bs = "<span class='bdg e'>아직 비어 있어요</span>" + bs
            who = " · ".join(x for x in (_short_loc(r.location), r.manager) if x)
            code = (f"<div class='cd'>{e(r.code)}</div>" if r.code else "<div class='cd no'>ITUBE번호 없음</div>")
            with col, st.container(key=f"iccard_{eid}"):
                st.markdown(f"<div class='ic'><div class='icph'>{ph}</div><div class='bd'><div class='nm' title='{e(r.name)}'>"
                            f"{e(r.name)}</div>{code}<div class='wh'>{e(who) or '&nbsp;'}</div><div class='bs'>{bs}</div>"
                            "</div></div>", unsafe_allow_html=True)
                st.button("열기", key=f"icgo_{eid}", on_click=_open, args=(eid,))


# ── 장비 한 대 ──────────────────────────────────────────────────────

PASTE_JS = r"""
<script>
(function () {
  const doc = window.parent.document, win = window.parent;
  if (win.__infoPaste) doc.removeEventListener('paste', win.__infoPaste, true);
  win.__infoPaste = function (ev) {
    const inp = doc.querySelector('.st-key-info_up input[type=file]');
    if (!inp) return;
    const t = ev.target;
    if (t && (t.tagName === 'TEXTAREA' || (t.tagName === 'INPUT' && t.type !== 'file') || t.isContentEditable)) return;
    const files = [...(ev.clipboardData ? ev.clipboardData.items : [])]
      .filter((it) => it.kind === 'file' && it.type.startsWith('image/')).map((it) => it.getAsFile()).filter(Boolean);
    if (!files.length) return;
    ev.preventDefault(); ev.stopPropagation();
    const dt = new win.DataTransfer();
    files.forEach((f, i) => dt.items.add(new win.File([f], f.name && f.name !== 'image.png' ? f.name : `붙여넣은 사진 ${i + 1}.png`, {type: f.type})));
    inp.files = dt.files;
    inp.dispatchEvent(new win.Event('change', {bubbles: true}));
  };
  doc.addEventListener('paste', win.__infoPaste, true);
})();
</script>
"""


def _save_photos(eid: int, rows: list[dict], label: str) -> None:
    keep = [{k: r.get(k, "") for k in db.cols("equip_photos")} for r in rows]
    db.save_info_rows("equip_photos", eid, keep, label)


def _photos(eid: int, name: str, icon: str, info: dict) -> None:
    ph = _of(info["equip_photos"], eid).to_dict("records")
    k = f"info_ph_{eid}"
    cur = min(st.session_state.get(k, 0), max(len(ph) - 1, 0))
    if ph:
        p = ph[cur]
        st.markdown(f"<div class='bigph'><img src='{photos.data_uri(p['photo'] or p['thumb'])}' alt=''></div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='bigph'>{_illust(icon, 120)}</div>", unsafe_allow_html=True)

    if ph:
        cols = st.columns(5)
        for j, p in enumerate(ph):
            with cols[j % 5], st.container(key=f"phth_{eid}_{j}"):
                st.markdown(f"<div class='th{' on' if j == cur else ''}'><img src='{photos.data_uri(p['thumb'] or p['photo'])}'"
                            " alt=''></div>", unsafe_allow_html=True)
                st.button("보기", key=f"phgo_{eid}_{j}", on_click=st.session_state.__setitem__, args=(k, j))
        b1, b2 = st.columns(2)
        if cur > 0 and b1.button("대표 사진으로", key=f"ph_cover_{eid}", icon=":material/star:", width="stretch"):
            ph.insert(0, ph.pop(cur))
            _save_photos(eid, ph, f"{name} 대표 사진")
            st.session_state[k] = 0
            st.rerun()
        with b2.popover("사진 지우기", icon=":material/delete:", width="stretch"):
            st.markdown("지금 보고 있는 사진을 지울까요?")
            if st.button("지우기", key=f"ph_del_{eid}", type="primary"):
                ph.pop(cur)
                _save_photos(eid, ph, f"{name} 사진 지우기")
                st.session_state[k] = max(cur - 1, 0)
                st.rerun()

    ver = st.session_state.get("info_up_ver", 0)
    with st.container(key="info_up"):
        ups = st.file_uploader("사진 올리기 · 여기로 끌어다 놓기 · Ctrl+V 붙여넣기", type=["png", "jpg", "jpeg", "webp", "gif", "bmp"],
                               accept_multiple_files=True, key=f"info_up_{eid}_{ver}")
    st.html(PASTE_JS, unsafe_allow_javascript=True)
    if ups:
        new = []
        for f in ups:
            try:
                thumb, big = photos.shrink(f.getvalue())
            except ValueError:
                st.warning(f"{f.name}: 사진 파일이 아니에요.")
                continue
            new.append({"id": "", "title": re.sub(r"\.[^.]+$", "", f.name), "thumb": thumb, "photo": big,
                        "created_at": db._now(), "created_by": db.who()})
        if new:
            _save_photos(eid, ph + new, f"{name} 사진 {len(new)}장 올리기")
            st.session_state[k] = len(ph)
            st.session_state.info_up_ver = ver + 1
            st.rerun()


def _clean(df: pd.DataFrame, keys: list[str]) -> list[dict]:
    out = []
    for r in df.to_dict("records"):
        rec = {c: ("" if r.get(c) is None or (isinstance(r.get(c), float) and pd.isna(r.get(c))) else str(r.get(c)).strip())
               for c in ["id"] + keys}
        if any(rec[c] for c in keys):
            out.append(rec)
    return out


def _specs(eid: int, name: str, info: dict) -> None:
    base = _of(info["equip_specs"], eid)[["id", "item", "value"]].reset_index(drop=True)
    ver = st.session_state.get(f"info_sp_ver_{eid}", 0)
    st.markdown("<div class='boxh'><b>주요 사양</b><small>바로 고치면 저장돼요 · 엑셀에서 붙여넣기 가능</small></div>",
                unsafe_allow_html=True)
    ed = st.data_editor(base, key=f"info_specs_{eid}_{ver}", num_rows="dynamic", hide_index=True, width="stretch",
                        column_order=["item", "value"],
                        column_config={"item": st.column_config.TextColumn("항목", width="small"),
                                       "value": st.column_config.TextColumn("값", width="large")})
    new, old = _clean(ed, ["item", "value"]), _clean(base, ["item", "value"])
    if new != old:
        db.save_info_rows("equip_specs", eid, new, f"{name} 사양")
        st.session_state[f"info_sp_ver_{eid}"] = ver + 1
        st.rerun()


def _docs(eid: int, name: str, info: dict) -> None:
    base = _of(info["equip_docs"], eid)[["id", "kind", "title", "url", "note"]].reset_index(drop=True)
    e = html.escape
    st.markdown("<div class='boxh'><b>자료</b><small>설명서 · SOP · 사양서 링크</small></div>", unsafe_allow_html=True)
    if base.empty:
        st.markdown("<div class='nodoc'>아직 자료가 없어요. 드라이브나 사내 폴더 링크를 넣어 두면 누구나 바로 열 수 있어요.</div>",
                    unsafe_allow_html=True)
    rows = []
    for r in base.itertuples(index=False):
        tag, color = DOC_TAG.get(r.kind, DOC_TAG["기타"])
        url = r.url if re.match(r"^(https?://|file:|\\\\)", r.url or "") else ""
        sub = " · ".join(x for x in (r.kind, r.note or (r.url if not url else "")) if x)
        inner = (f"<div class='di {color}'>{e(tag)}</div><div class='t'><b>{e(r.title or r.url or '(제목 없음)')}</b>"
                 f"<small>{e(sub)}</small></div><span class='go'>열기 ↗</span>")
        rows.append(f"<a class='doc' href='{e(url)}' target='_blank' rel='noopener'>{inner}</a>" if url
                    else f"<div class='doc nolink'>{inner}</div>")
    if rows:
        st.markdown("".join(rows), unsafe_allow_html=True)
    ver = st.session_state.get(f"info_dc_ver_{eid}", 0)
    with st.popover("자료 추가 · 고치기", icon=":material/add_link:", width="stretch"):
        ed = st.data_editor(base, key=f"info_docs_{eid}_{ver}", num_rows="dynamic", hide_index=True, width="stretch",
                            column_order=["kind", "title", "url", "note"],
                            column_config={
                                "kind": st.column_config.SelectboxColumn("종류", options=DOC_KINDS, default="설명서",
                                                                         width="small"),
                                "title": st.column_config.TextColumn("제목", width="medium"),
                                "url": st.column_config.TextColumn("링크", width="large",
                                                                   help="드라이브 · 사내 폴더 주소를 붙여넣으세요."),
                                "note": st.column_config.TextColumn("메모", width="small")})
        st.caption("줄을 고치면 바로 저장돼요. 지우려면 줄 왼쪽을 눌러 고른 뒤 Delete.")
    new, old = _clean(ed, ["kind", "title", "url", "note"]), _clean(base, ["kind", "title", "url", "note"])
    if new != old:
        db.save_info_rows("equip_docs", eid, new, f"{name} 자료")
        st.session_state[f"info_dc_ver_{eid}"] = ver + 1
        st.rerun()


def _save_note(eid: int) -> None:
    ss = st.session_state
    db.save_info_note(eid, ss.get(f"info_caution_{eid}", ""), ss.get(f"info_contact_{eid}", ""))


def _notes(eid: int, info: dict, key: str, title: str, hint: str, place: str) -> None:
    nt = info["equip_notes"]
    row = nt[nt["id"] == str(eid)]
    k = f"info_{key}_{eid}"
    if k not in st.session_state:
        st.session_state[k] = row.iloc[0][key] if not row.empty else ""
    st.markdown(f"<div class='boxh'><b>{title}</b><small>{hint}</small></div>", unsafe_allow_html=True)
    st.text_area(title, key=k, label_visibility="collapsed", placeholder=place, height=110,
                 on_change=_save_note, args=(eid,))


def _history(ids: list[int], eq: pd.DataFrame) -> None:
    """장비 히스토리: 날짜순 타임라인 (주장비 전체면 세부장비 기록까지 함께). 사진 한 장, 엑셀로 내려받기."""
    from core import history
    eid = ids[0]
    name_of = dict(zip(eq["id"].astype(int), eq["name"]))
    df = history.load()
    df = df[df["equip_id"].isin(ids)] if not df.empty else df
    e = html.escape
    with st.container(border=True, key=f"hist_{eid}"):
        h1, h2 = st.columns([3, 1], vertical_alignment="center")
        h1.markdown(f"<div class='boxh'><b>장비 히스토리</b><small>{len(df)}건 · 최근 기록이 위</small></div>",
                    unsafe_allow_html=True)
        if not df.empty:
            h2.download_button("엑셀", history.to_xlsx(df, name_of), f"장비히스토리_{name_of.get(eid, eid)}.xlsx",
                               icon=":material/download:", width="stretch", key=f"hist_xl_{eid}")
        ver = st.session_state.get("hist_ver", 0)
        with st.expander("기록 추가", icon=":material/add:"):
            with st.form(f"hist_add_{eid}_{ver}", border=False):
                c1, c2 = st.columns([1, 2])
                day = c1.date_input("날짜", value=dt.date.today(), format="YYYY-MM-DD")
                who = c2.selectbox("장비", ids, format_func=lambda i: name_of.get(i, str(i))) if len(ids) > 1 else eid
                text = st.text_area("내용", placeholder="예) 히터 온도 이상 → 센서 교체 (OO기계 A/S)", height=90)
                pic = st.file_uploader("사진 (선택)", type=["png", "jpg", "jpeg", "webp", "bmp"])
                if st.form_submit_button("저장", type="primary", icon=":material/save:"):
                    if not text.strip():
                        st.warning("내용을 적어 주세요.")
                    else:
                        thumb = big = ""
                        if pic is not None:
                            try:
                                thumb, big = photos.shrink(pic.getvalue())
                            except ValueError:
                                st.warning("사진 파일이 아니라서 빼고 저장했어요.")
                        history.add(int(who), day, text.strip(), thumb, big)
                        st.session_state.hist_ver = ver + 1
                        st.rerun()
        if df.empty:
            st.caption("아직 기록이 없어요.")
            return
        for r in df.to_dict("records"):
            rid = int(r["id"])
            c1, c2, c3 = st.columns([0.9, 4, 0.5], vertical_alignment="top")
            c1.markdown(f"<b>{r['date'] or ''}</b>", unsafe_allow_html=True)
            dev = f"<small style='color:var(--accent)'>{e(name_of.get(r['equip_id'], ''))}</small><br>" \
                if len(ids) > 1 else ""
            c2.markdown(f"{dev}{e(str(r['content'])).replace(chr(10), '<br>')}"
                        f"<br><small style='color:var(--muted)'>{e(str(r['created_by'] or ''))}</small>",
                        unsafe_allow_html=True)
            if r["thumb"]:
                c2.markdown(f"<img src='{photos.data_uri(r['photo'] or r['thumb'])}' style='max-width:260px;"
                            "border-radius:8px'>", unsafe_allow_html=True)
            with c3.popover("", icon=":material/more_horiz:"):
                new = st.text_area("내용", value=str(r["content"]), key=f"hist_ed_{rid}")
                if st.button("고치기", key=f"hist_up_{rid}", type="primary"):
                    history.update(rid, content=new.strip())
                    st.rerun()
                if st.button("지우기", key=f"hist_del_{rid}", icon=":material/delete:"):
                    history.delete(rid)
                    st.rerun()


def _family(root: int, eq: pd.DataFrame) -> list[tuple[int, int]]:
    """root 아래 세부장비를 목록 순서대로 (id, 깊이)."""
    kids: dict[int, list[int]] = {}
    for i, p in zip(eq["id"].astype(int), eq["parent_id"]):
        if pd.notna(p):
            kids.setdefault(int(p), []).append(i)
    out: list[tuple[int, int]] = []

    def walk(i: int, d: int) -> None:
        for k in kids.get(i, []):
            out.append((k, d))
            walk(k, d + 1)
    walk(root, 1)
    return out


def _root(eid: int, eq: pd.DataFrame) -> int:
    par = dict(zip(eq["id"].astype(int), eq["parent_id"]))
    seen = set()
    while pd.notna(par.get(eid)) and eid not in seen:
        seen.add(eid)
        eid = int(par[eid])
    return eid


def _detail(eid: int, eq: pd.DataFrame, info: dict) -> None:
    if st.button("모든 장비", icon=":material/arrow_back:", type="tertiary", key="info_back"):
        _open(None)
        st.rerun()
    fam = _family(eid, eq)
    if not fam:
        _unit(eid, eq, info)
        _history([eid], eq)
        return
    # 세부장비가 많아도 짧게: 왼쪽은 이름 목록(검색), 오른쪽은 고른 하나만
    name_of = dict(zip(eq["id"].astype(int), eq["name"]))
    key = f"info_unit_{eid}"
    cur = st.session_state.get(key, eid)
    nav, body = st.columns([1, 3.3], gap="medium")
    with nav, st.container(border=True, key="info_nav"):
        q = st.text_input("세부장비 찾기", key=f"info_unit_q_{eid}", placeholder=f"세부장비 {len(fam)}개에서 찾기",
                          label_visibility="collapsed", icon=":material/search:")
        depth = dict(fam)
        ids = [i for i, _ in fam if not q or q.lower() in name_of.get(i, "").lower()]
        if cur != eid and cur not in ids:
            ids = [cur] + ids
        with st.container(height=min(620, 60 + 36 * (len(ids) + 1)), border=False):
            sel = st.radio("세부장비", [eid] + ids, key=key, label_visibility="collapsed",
                           format_func=lambda i: "■ 주장비 전체" if i == eid
                           else "\u3000" * (depth.get(i, 1) - 1) + name_of.get(i, str(i)))
    with body:
        _unit(sel, eq, info, in_list=True)
        _history([eid] + [i for i, _ in fam] if sel == eid else [sel], eq)


def _unit(eid: int, eq: pd.DataFrame, info: dict, in_list: bool = False) -> None:
    r = eq[eq["id"] == eid].iloc[0]
    label_of = dict(zip(eq["id"].astype(int), eq["name"]))
    kids = eq[eq["parent_id"] == eid]
    up = int(r["parent_id"]) if pd.notna(r["parent_id"]) else None
    icon = _icon_key(r["name"] + " " + " ".join(kids["name"]))
    e = html.escape

    with st.container(border=True):
        left, right = st.columns([1, 1.65], gap="large")
        with left:
            _photos(eid, r["name"], icon, info)
        with right:
            sub = e(r["code"] or "ITUBE번호 없음")
            if r["species"] and r["species"] != r["name"]:
                sub += f" · {e(r['species'])}"
            if up is not None:
                sub += f" <span class='up'>· 소속 {e(label_of.get(up, ''))}</span>"
            items = [("대분류", r["group"]), ("위치", r["location"]), ("관리자", r["manager"]), ("제조사", r["maker"]),
                     ("모델명", r["model"]), ("구매처", r["vendor"]), ("장비용도", r["use"]), ("구분", r["category"]),
                     ("자산번호", r["asset_no"]), ("국가연구시설장비번호", r["nfec"]),
                     ("도입일", f"{r['acquired_on']:%Y-%m-%d}" if pd.notna(r["acquired_on"]) else ""),
                     ("불용일", f"{r['retired_on']:%Y-%m-%d}" if pd.notna(r["retired_on"]) else "")]
            kv = "".join(f"<div><span>{e(k)}</span><b title='{e(str(v))}'>{e(str(v))}</b></div>"
                         for k, v in items if str(v).strip() and str(v) not in ("모델없음", "모델명없음"))
            st.markdown(f"<div class='hero-n'>{e(r['name'])}</div><div class='hero-c'>{sub}</div><div class='kv'>{kv}</div>",
                        unsafe_allow_html=True)
            if r["system"]:
                st.caption(f"시스템 구성 · {r['system']}")
            if not kids.empty and not in_list:
                st.pills("세부장비", list(kids["id"].astype(int)), format_func=lambda i: label_of.get(i, str(i)),
                         key=f"info_kids_{eid}", on_change=lambda: _open(st.session_state.get(f"info_kids_{eid}")),
                         help="누르면 그 세부장비 정보가 열려요.")
            show_up = up is not None and not in_list
            b = st.columns([1, 1, 1] if show_up else [1, 1, 1.2])
            if b[0].button(w("가동률 보기"), icon=":material/monitoring:", width="stretch", key="info_to_detail"):
                common.go_equipment(eid)
            if b[1].button("기본 정보 고치기", icon=":material/edit:", width="stretch", key="info_to_master",
                           help="'기준 정보 › 장비' 표에서 이 장비를 찾아 엽니다."):
                common.go_master_equipment(r["name"])
            if show_up and b[2].button("소속 장비로", icon=":material/arrow_upward:", width="stretch",
                                              key="info_to_up"):
                _open(up)
                st.rerun()

    c1, c2 = st.columns([1.05, 1], gap="medium")
    with c1, st.container(border=True):
        _specs(eid, r["name"], info)
        _notes(eid, info, "caution", "사용 시 주의", "다 쓰고 칸 밖을 누르면 저장돼요",
               "예) 사용 후 블레이드 세척 필수 (NMP)\n진공 펌프 오일 3개월마다 확인")
    with c2, st.container(border=True):
        _docs(eid, r["name"], info)
        _notes(eid, info, "contact", "A/S 연락처", "제조사 · 구매처 담당자",
               "예) OO기계 서비스팀 홍길동 과장 031-000-0000")


def render() -> None:
    page_header("장비 정보", GROUP)
    st.markdown(CSS, unsafe_allow_html=True)
    eq = db.load_equipment()
    if eq.empty:
        empty_state("등록된 장비가 없습니다", "'기준 정보 › 장비'에서 먼저 장비를 추가하세요.")
        return
    info = db.load_info()
    want = st.session_state.pop("info_equip", None)
    if want is not None:
        _open(want)
    try:
        sel = int(st.query_params.get("eq", ""))
    except ValueError:
        sel = None
    if sel is not None and sel in set(eq["id"].astype(int)):
        top = _root(sel, eq)
        if top != sel:  # 세부장비로 바로 들어오면 주장비 화면에서 그 줄을 골라 둠
            st.session_state[f"info_unit_{top}"] = sel
            _open(top)
            sel = top
        _detail(sel, eq, info)
    else:
        _gallery(eq, info)
