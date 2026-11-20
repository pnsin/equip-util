"""데이터 점검 (2026-11-20 사용자: "실적이 있는데 화면에 안 나오는 경우는 아주 큰일").

시트에 있는 실적이 어느 화면(가동률·달력·충방전기 현황·i-Tube 파일)에서 빠지거나, 잘못 연결되거나,
두 번 세어질 수 있는 경우를 찾아 목록으로 돌려줍니다. 화면은 views/health.py.
level: "확인" = 숫자가 빠지거나 틀어질 수 있음 · "참고" = 설계대로지만 알아 두면 좋은 것
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core.db import descendants, to_str

CHECK, NOTE = "확인", "참고"
ROW_COLS = ["ID", "장비", "시작일", "종료일", "업체", "시간", "내용"]


def _rows(df: pd.DataFrame, note=None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=ROW_COLS)
    out = pd.DataFrame({
        "ID": df["id"].astype("int64"),
        "장비": df["equip_name"].map(to_str).replace("", "(장비 없음)") + df["equip_id"].map(
            lambda v: f" #{int(v)}" if pd.notna(v) else ""),
        "시작일": df["start_date"].dt.date,
        "종료일": df["end_date"].dt.date,
        "업체": df["company"].map(to_str).replace("", "내부"),
        "시간": df["hours"],
        "내용": [note(r) for r in df.to_dict("records")] if note else df["purpose_detail"].map(to_str),
    })
    return out.reset_index(drop=True)


def _parents(eq: pd.DataFrame) -> dict[int, int]:
    return ({int(i): int(p) for i, p in zip(eq["id"], eq["parent_id"]) if pd.notna(p)}
            if "parent_id" in eq else {})


def _chain(i: int, parent: dict[int, int]) -> list[int]:
    """자신 → 맨 위 장비까지."""
    out, seen = [], set()
    cur = i
    while cur is not None and cur not in seen:
        out.append(cur)
        seen.add(cur)
        cur = parent.get(cur)
    return out


def run(logs: pd.DataFrame, eq: pd.DataFrame, ch: pd.DataFrame, companies: pd.DataFrame,
        chargers: set[int], today: dt.date | None = None) -> list[dict]:
    """[{key, level, title, why, rows}] (문제가 있는 것만)."""
    today = today or dt.date.today()
    found: list[dict] = []

    def add(key, level, title, why, df, note=None):
        if df is not None and len(df):
            found.append({"key": key, "level": level, "title": title, "why": why, "rows": _rows(df, note)})

    if logs.empty:
        return found
    lg = logs.copy()
    ids = set(eq["id"].astype(int)) if not eq.empty else set()
    parent = _parents(eq)
    kpi = dict(zip(eq["id"].astype(int), eq["in_kpi"].astype(bool))) if not eq.empty else {}
    cat = dict(zip(eq["id"].astype(int), eq.get("category", pd.Series([""] * len(eq))).map(to_str))) if not eq.empty else {}
    known_eq = lg["equip_id"].map(lambda v: pd.notna(v) and int(v) in ids)

    # 1. 장비 연결
    add("no_equip", CHECK, "장비 목록에 없는 장비의 실적",
        "장비가 지워졌거나 번호가 틀려서 가동률·달력·장비별 화면 어디에도 나오지 않아요. 장비를 다시 골라 주세요.",
        lg[~known_eq])
    lg = lg[known_eq].copy()
    lg["eid"] = lg["equip_id"].astype(int)

    # 2. 날짜·시간
    bad_date = lg["start_date"].isna() | lg["end_date"].isna() | (lg["end_date"] < lg["start_date"])
    add("bad_date", CHECK, "날짜가 비었거나 종료일이 시작일보다 빠른 실적",
        "달력과 가동률 계산에서 빠지거나 하루로만 잡혀요.", lg[bad_date])
    ok = lg[~bad_date].copy()
    far = (ok["start_date"].dt.year < today.year - 5) | (ok["end_date"].dt.year > today.year + 1)
    add("far_date", CHECK, "연도가 이상한 실적", f"{today.year - 5}년 전이나 {today.year + 1}년 뒤 날짜예요. 오타인지 확인해 주세요.",
        ok[far])
    hrs = pd.to_numeric(ok["hours"], errors="coerce")
    add("no_hours", CHECK, "사용시간이 0이거나 비어 있는 실적", "가동률에 0시간으로 잡혀요.", ok[~(hrs > 0)])
    days = (ok["end_date"] - ok["start_date"]).dt.days + 1
    over = (hrs > days * 24) & ~ok["eid"].isin(chargers)
    add("over_24h", CHECK, "하루 24시간을 넘는 실적", "기간보다 사용시간이 많아요. 시간이나 기간이 잘못 들어갔을 수 있어요.",
        ok[over], lambda r: f"{int((r['end_date'] - r['start_date']).days) + 1}일에 {r['hours']:g}시간")

    # 3. 가동률(KPI)에 안 잡힘
    def counted(i: int) -> bool:
        return any(kpi.get(j) for j in _chain(i, parent))
    add("not_kpi", CHECK, "가동률에 안 잡히는 실적",
        "이 장비와 그 위 장비가 모두 '가동률산정 N'이라 장비 KPI 현황 합계에 들어가지 않아요.",
        ok[~ok["eid"].map(counted)])

    # 4. 장비 보유 기간 밖
    acq = dict(zip(eq["id"].astype(int), eq.get("acquired_on", pd.Series([None] * len(eq)))))
    ret = dict(zip(eq["id"].astype(int), eq.get("retired_on", pd.Series([None] * len(eq)))))

    def outside(r) -> bool:
        a, b = acq.get(r["eid"]), ret.get(r["eid"])
        s, e = r["start_date"].date(), r["end_date"].date()
        return bool((a and pd.notna(a) and s < a) or (b and pd.notna(b) and e > b))
    add("out_of_life", CHECK, "장비 도입일 전이나 불용일 뒤의 실적", "그 기간은 가용시간이 0이라 가동률이 틀어져요.",
        ok[[outside(r) for r in ok.to_dict("records")]] if len(ok) else ok)

    # 5. 충방전기 현황
    fam = set(chargers)
    for i in list(chargers):
        fam.update(_chain(i, parent))
    chg = ok[ok["eid"].isin(fam)]
    no_ch = chg[chg["chambers"].map(to_str) == ""]
    add("no_chamber", CHECK, "충방전기 현황에 안 보이는 충방전기 실적",
        "챔버가 정해져 있지 않아 충방전기 현황 표에 나오지 않아요. 입력 카드에서 챔버를 골라 주세요.", no_ch)
    ch_eq = dict(zip(ch["id"].astype(int), ch["equip_id"])) if not ch.empty else {}
    desc = descendants(eq)

    def ch_ids(v) -> list[int]:
        out = []
        for x in to_str(v).replace(" ", "").split(","):
            if x.strip().lstrip("-").isdigit():
                out.append(int(x))
        return out
    with_ch = ok[ok["chambers"].map(to_str) != ""]
    gone = with_ch[[any(c not in ch_eq for c in ch_ids(v)) for v in with_ch["chambers"]]]
    add("bad_chamber", CHECK, "없는 챔버를 가리키는 실적", "챔버 구성에서 지워진 챔버라 충방전기 현황에 나오지 않아요.", gone,
        lambda r: f"챔버ID {r['chambers']}")

    def wrong(r) -> bool:
        mine = set(desc.get(r["eid"], [r["eid"]])) | set(_chain(r["eid"], parent))
        return any(c in ch_eq and pd.notna(ch_eq[c]) and int(ch_eq[c]) not in mine for c in ch_ids(r["chambers"]))
    add("other_chamber", CHECK, "다른 장비의 챔버에 연결된 실적",
        "실적의 장비와 챔버의 충방전기가 달라서 현황 표와 가동률이 서로 다른 장비에 잡혀요.",
        with_ch[[wrong(r) for r in with_ch.to_dict("records")]] if len(with_ch) else with_ch,
        lambda r: f"챔버ID {r['chambers']}")

    # 6. 두 번 들어간 실적
    key = ["eid", "start_date", "end_date", "company", "hours", "purpose"]
    k = ok.assign(company=ok["company"].map(to_str), purpose=ok["purpose"].map(to_str))
    # 한 번에 같이 저장한 줄(ID 앞자리가 같음)은 시료·회차를 나눠 넣은 것이라 빼고, 따로 저장한 것만
    k["batch"] = k["id"].map(lambda v: int(v) // 1000 if str(v).isdigit() and len(str(v)) >= 13 else v)
    d_ = k[k.duplicated(key, keep=False)]
    dup = d_[d_.groupby(key)["batch"].transform("nunique") > 1].sort_values(key)
    add("dup", CHECK, "같은 내용이 두 번 들어간 실적", "장비·기간·업체·시간·목적이 모두 같아요. 두 번 세어지고 있을 수 있어요.", dup)

    # 같은 장비·같은 업체가 기간이 겹치게 따로 들어간 것 (다른 경로로 두 번 입력했을 수 있음)
    k["skey"] = [to_str(sv) or f"#{i}" for sv, i in zip(k["series"], k["id"])]
    over_ids: set = set()
    for _, g in k[k["company"] != ""].groupby(["eid", "company"]):
        if g["skey"].nunique() < 2:
            continue
        g = g.sort_values(["start_date", "id"]).to_dict("records")
        for i, r in enumerate(g):
            for q in g[i + 1:]:
                if q["start_date"] > r["end_date"]:
                    break
                if q["skey"] != r["skey"] and q["id"] not in set(dup["id"]):
                    over_ids.update((r["id"], q["id"]))
    add("overlap", NOTE, "같은 장비·같은 업체 실적의 기간이 겹침",
        "시료를 나눠 넣은 것이면 괜찮아요. 같은 일을 두 번 입력했다면 하나를 지워 주세요.",
        ok[ok["id"].isin(over_ids)].sort_values(["eid", "start_date"]))

    # 같은 챔버를 기간이 겹치게 두 업체가 통째로 쓴 것 (채널을 나눠 쓴 게 아니면 중복 예약)
    cb = []
    for r in with_ch.to_dict("records"):
        if to_str(r.get("ch_part")):
            continue
        for c in ch_ids(r["chambers"]):
            cb.append((c, r["start_date"], r["end_date"], to_str(r["company"]),
                       to_str(r.get("series")) or f"#{r['id']}", r["id"]))
    clash: set = set()
    by_c: dict = {}
    for t in cb:
        by_c.setdefault(t[0], []).append(t)
    for lst in by_c.values():
        lst.sort(key=lambda t: t[1])
        for i, a_ in enumerate(lst):
            for b_ in lst[i + 1:]:
                if b_[1] > a_[2]:
                    break
                if a_[3] != b_[3] and a_[4] != b_[4]:
                    clash.update((a_[5], b_[5]))
    add("chamber_clash", NOTE, "같은 챔버를 같은 기간에 두 업체가 통째로 씀",
        "채널을 나눠 쓴 거라면 입력 카드에서 채널을 골라 두면 현황 표가 정확해져요.",
        with_ch[with_ch["id"].isin(clash)].sort_values("start_date"), lambda r: f"챔버ID {r['chambers']}")

    # 7. 묶음ID
    ser = ok[ok["series"].map(to_str) != ""]
    mixed = [s for s, g in ser.groupby("series") if g["eid"].nunique() > 1 or g["company"].map(to_str).nunique() > 1]
    add("mixed_series", CHECK, "한 묶음인데 장비나 업체가 다른 기간 실적",
        "달마다 나눠 저장한 한 기간 실적인데 줄마다 장비·업체가 달라요. 고치기·삭제가 엉뚱하게 될 수 있어요.",
        ser[ser["series"].isin(mixed)])

    # 8. i-Tube 파일
    def facility(i: int) -> bool:
        return any("시설" in cat.get(j, "") for j in _chain(i, parent))
    no_code = ok[ok["itube_code"].map(to_str) == ""]
    add("no_itube", CHECK, "i-Tube 파일에서 빠지는 실적",
        "이 장비와 그 위 장비 모두 i-Tube 번호가 없어서 실적 내려받기(i-Tube 파일)에 들어가지 않아요. 장비 목록에서 번호를 넣어 주세요.",
        no_code[~no_code["eid"].map(facility)])
    add("no_itube_facility", NOTE, "i-Tube 번호가 없는 시설의 실적",
        "시설(클린룸·드라이룸 등)이라 i-Tube 파일에는 들어가지 않아요. 가동률에는 잡혀요.",
        no_code[no_code["eid"].map(facility)])
    ext = ok[ok["usage_type"].map(to_str) == "외부"]
    add("ext_no_company", CHECK, "외부 실적인데 업체가 비어 있음", "i-Tube 파일에 기관명이 비어 올라가요.",
        ext[ext["company"].map(to_str) == ""])
    names = set(companies["name"].map(to_str)) if not companies.empty else set()
    has_c = ext[ext["company"].map(to_str) != ""]
    def num(v) -> str:
        return "".join(ch_ for ch_ in to_str(v) if ch_.isdigit())
    brn_of = ({to_str(n): num(b) for n, b in zip(companies["name"], companies["brn"])}
              if not companies.empty and "brn" in companies else {})
    no_brn = [not num(b) and not brn_of.get(to_str(c)) for b, c in zip(has_c["brn"], has_c["company"])]
    add("ext_no_brn", CHECK, "외부 실적인데 사업자등록번호가 없음",
        "실적에도 업체 목록에도 번호가 없어 i-Tube 파일에 비어 올라가요. 업체 목록에 번호를 넣으면 파일에 자동으로 들어가요.",
        has_c[no_brn] if len(has_c) else has_c)
    add("unknown_company", NOTE, "업체 목록에 없는 업체 이름",
        "업체 목록과 글자가 달라서 사업자번호·업종이 자동으로 채워지지 않아요.",
        has_c[~has_c["company"].map(to_str).isin(names)])
    return found


def summary(found: list[dict]) -> tuple[int, int]:
    """(확인 필요 건수, 참고 건수) — 실적 줄 수 기준."""
    return (sum(len(f["rows"]) for f in found if f["level"] == CHECK),
            sum(len(f["rows"]) for f in found if f["level"] == NOTE))
