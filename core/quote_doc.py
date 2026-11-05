"""견적서 계산 · 엑셀 채우기 · PDF 만들기.

팀이 쓰던 엑셀 견적서 두 가지를 그대로 틀로 씁니다 (assets/quote_mfg.xlsx, assets/quote_test.xlsx).
앱에서 입력한 값을 같은 칸에 넣고, LibreOffice 로 PDF 를 만듭니다. 그래서 로고·칸·선·결재칸이 원래 양식과 같습니다.

- 제조(장비사용) 양식: RAT-2610-143 아모그린텍 견적서 모양. 장비 11줄, 재료비 8줄.
- 시험 양식: RAT-2601-005 네패스야하드 견적서 모양. 1쪽 내부보관용(단가·난이도 포함), 2쪽 업체용. 장비 9줄, 기술료 3줄.

금액은 칸마다 계산해서 '값'으로 넣습니다 (수식을 남기지 않음). 직접 입력한 금액은 그대로 씁니다.
"""
from __future__ import annotations

import datetime as dt
import io
import math
import os
import re
import shutil
import subprocess
import tempfile

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
TEMPLATES = {"제조": os.path.join(ASSETS, "quote_mfg.xlsx"), "시험": os.path.join(ASSETS, "quote_test.xlsx")}
FORMS = ("제조", "시험")
MAX_LINES = {"제조": 11, "시험": 9}
MAX_EXTRAS = {"제조": 8, "시험": 3}
EXTRA_TITLE = {"제조": "재료비", "시험": "기술료"}
DISC_LABELS = {"제조": ("이차전지 협의회 할인", "전 공정 할인"), "시험": ("장비사용료 할인", "기술지원 회원사 할인")}
DEFAULT_EXTRAS = {"제조": [], "시험": [{"name": "시험데이터"}, {"name": "엔지니어지원비"},
                                     {"name": "재료비(시약, 가스, 지그등)"}]}
DEFAULT_REMARKS = {
    "제조": " * 1회 최소 믹서용량 50L(실용량 35L) 기준 / 믹서용량 5L(실용량 3.5L) 기준\n"
            " * 전극제조실 : 클린룸 / 셀 조립실 : 드라이룸\n * 재료비는 구입 단가에 따라 변동 가능",
    "시험": " * 충북테크노파크 장비사용료 산출기준, 회원사 및 장비사용일정은 협의가 필요 함.",
}
UNITS = ["hr", "day", "건", "회", "ch", "식", "개", "EA", "m"]


def num(v, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return default if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = str(v).replace(",", "").replace("원", "").strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def has_amount(v) -> bool:
    """금액을 직접 넣었는지 (빈 칸이면 자동 계산)."""
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    return str(v).strip() != ""


def ch_of(ln: dict) -> float:
    """쓰는 채널 수 (충방전기처럼 단가가 ch당일 때). 비우면 1."""
    return num(ln.get("ch"), 1) or 1


def ch_price(ln: dict):
    """견적서에 찍을 단가 = 단가 × 채널 수 (채널이 1이면 그대로)."""
    p = ln.get("price")
    return num(p) * ch_of(ln) if ch_of(ln) != 1 and p is not None else p


def ch_tag(ln: dict) -> str:
    c = ch_of(ln)
    return f"{c:g}ch" if c != 1 else ""


def line_auto(form: str, ln: dict) -> float:
    """시간당 단가로 계산한 금액. 제조 = 사용량 × 단가 × 채널, 시험 = 수량 × 시험시간 × 단가 × 채널 × 난이도."""
    if form == "시험":
        cnt = num(ln.get("count"), 1) or 0
        diff = num(ln.get("difficulty"), 1)
        return cnt * num(ln.get("qty")) * num(ln.get("price")) * ch_of(ln) * diff
    return num(ln.get("qty")) * num(ln.get("price")) * ch_of(ln)


def line_amount(form: str, ln: dict) -> float:
    return num(ln.get("amount")) if has_amount(ln.get("amount")) else line_auto(form, ln)


def extra_amount(ex: dict) -> float:
    if has_amount(ex.get("amount")):
        return num(ex.get("amount"))
    return num(ex.get("qty")) * num(ex.get("price"))


def is_blank_line(ln: dict) -> bool:
    keys = ("name", "spec", "note", "qty", "price", "amount")
    return not any(str(ln.get(k) or "").strip() not in ("", "0", "0.0", "nan", "None") for k in keys)


def totals(q: dict) -> dict:
    """견적 합계. 할인은 앞 할인을 뺀 금액에 다음 할인을 적용, 총계는 천 원 미만 절사, 부가세 10%."""
    form = q.get("form", "제조")
    lines = [ln for ln in q.get("lines", []) if not is_blank_line(ln)]
    extras = [ex for ex in q.get("extras", []) if not is_blank_line(ex)]
    eq = round(sum(line_amount(form, ln) for ln in lines))
    p1, p2 = num(q.get("disc1")), num(q.get("disc2"))
    d1 = round(eq * p1 / 100)
    ext = round(sum(extra_amount(ex) for ex in extras))
    if form == "시험":
        after = eq - d1
        both = after + ext
        d2 = round(both * p2 / 100)
        base = both - d2
    else:
        d2 = round((eq - d1) * p2 / 100)
        after = eq - d1 - d2
        both = after + ext
        base = both
    final = int(math.floor(base / 1000) * 1000) if base > 0 else 0
    vat = round(final * 1.1)
    return {"eq": eq, "d1": d1, "d2": d2, "after": after, "extras": ext, "both": both, "final": final, "vat": vat}


# ── 견적번호 ────────────────────────────────────────────────────

def make_no(date: dt.date, seq: int | str) -> str:
    return f"RAT-{date:%y%m}-{str(seq).zfill(3) if str(seq).isdigit() else seq}"


def next_seq(seqs: list, year_nos: list[str] | None = None) -> int:
    """올해 발급 번호 다음 번호 (126-1 같은 재견적 번호는 앞 숫자만 봄)."""
    best = 0
    for s in seqs:
        m = re.match(r"\s*(\d+)", str(s))
        if m:
            best = max(best, int(m.group(1)))
    return best + 1


# ── 엑셀 채우기 ─────────────────────────────────────────────────

def _date_text(form: str, d: dt.date) -> str:
    return f"{d:%Y.%m.%d}." if form == "제조" else f"{d.year}. {d.month}. {d.day}."


def _head(q: dict, d: dt.date) -> dict:
    writer = " ".join(x for x in (str(q.get("writer") or "").strip(), str(q.get("writer_title") or "").strip()) if x)
    return {
        "no": f"NO.  : {q.get('no', '')}",
        "date": f"   일  자 : {_date_text(q.get('form', '제조'), d)}",
        "to": f"수신 : {q.get('company', '')}",
        "writer": f"   담  당 : {writer}",
        "ref": f"참조 : {q.get('contact', '')}",
        "email": f"   E-Mail: {q.get('email', '')}",
        "title": f"제목 : {q.get('title', '')}",
        "tel": f"TEL  : {q.get('phone', '')}",
    }


def _put(ws, ref: str, value) -> None:
    from openpyxl.cell.cell import MergedCell
    c = ws[ref]
    if isinstance(c, MergedCell):
        return
    c.value = value


def _val(v):
    """엑셀에 넣을 값: 빈 칸은 None, 숫자는 숫자로."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else v
    s = str(v).strip()
    if not s or s in ("nan", "None"):
        return None
    try:
        f = float(s.replace(",", ""))
        return int(f) if f.is_integer() else f
    except ValueError:
        return s


def _fill_mfg(ws, q: dict, d: dt.date, t: dict) -> None:
    h = _head(q, d)
    for ref, k in (("C9", "no"), ("H9", "date"), ("C10", "to"), ("H10", "writer"), ("C11", "ref"),
                   ("H11", "email"), ("C12", "title"), ("C13", "tel")):
        _put(ws, ref, h[k])
    lines = [ln for ln in q.get("lines", []) if not is_blank_line(ln)][:MAX_LINES["제조"]]
    for i in range(MAX_LINES["제조"]):
        r = 19 + i
        ln = lines[i] if i < len(lines) else None
        if ln is None:
            for col in "CDEFGH":
                _put(ws, f"{col}{r}", None)
            _put(ws, f"I{r}", 0)
            _put(ws, f"J{r}", 0)
            continue
        amt = round(line_amount("제조", ln))
        for col, k in (("C", "name"), ("D", "spec"), ("E", "note"), ("F", "qty"), ("G", "unit"), ("H", "price")):
            _put(ws, f"{col}{r}", _val(ln.get(k)))
        if ch_tag(ln):  # ch당 단가 × 채널 수로 찍음
            _put(ws, f"E{r}", " ".join(x for x in (ch_tag(ln), str(_val(ln.get("note")) or "")) if x))
            _put(ws, f"H{r}", _val(ch_price(ln)))
        _put(ws, f"I{r}", amt)
        _put(ws, f"J{r}", amt)
    _put(ws, "J30", t["eq"])
    _put(ws, "H31", _val(q.get("disc1")) or None)
    _put(ws, "J31", t["d1"])
    _put(ws, "H32", _val(q.get("disc2")) or None)
    _put(ws, "J32", t["d2"])
    _put(ws, "J33", t["after"])
    extras = [ex for ex in q.get("extras", []) if not is_blank_line(ex)][:MAX_EXTRAS["제조"]]
    for i in range(MAX_EXTRAS["제조"]):
        r = 36 + i
        ex = extras[i] if i < len(extras) else None
        if ex is None:
            for col in "CDEFGH":
                _put(ws, f"{col}{r}", None)
            _put(ws, f"I{r}", 0)
            _put(ws, f"J{r}", 0)
            continue
        amt = round(extra_amount(ex))
        for col, k in (("D", "name"), ("F", "qty"), ("G", "unit"), ("H", "price")):
            _put(ws, f"{col}{r}", _val(ex.get(k)))
        _put(ws, f"I{r}", amt)
        _put(ws, f"J{r}", amt)
    _put(ws, "J44", t["extras"])
    _put(ws, "J45", t["both"])
    _put(ws, "J46", t["final"])
    _put(ws, "J49", t["vat"])
    rem = q.get("remarks")
    _put(ws, "B48", DEFAULT_REMARKS["제조"] if rem is None else rem)


def _fill_test(ws, q: dict, d: dt.date, t: dict) -> None:
    h = _head(q, d)
    for top in (0, 54):  # 1쪽(내부보관용) · 2쪽(업체용)
        for ref, k in (("C9", "no"), ("I9", "date"), ("C10", "to"), ("I10", "writer"), ("C11", "ref"),
                       ("I11", "email"), ("C12", "title"), ("C13", "tel")):
            col, row = ref[0], int(ref[1:])
            _put(ws, f"{col}{row + top}", h[k])
        _put(ws, f"C{14 + top}", None)
        _put(ws, f"K{5 + top}", ws["K5"].value)
        _put(ws, f"K{6 + top}", ws["K6"].value)
    _put(ws, "D57", None)
    lines = [ln for ln in q.get("lines", []) if not is_blank_line(ln)][:MAX_LINES["시험"]]
    for i in range(MAX_LINES["시험"]):
        r, r2 = 20 + i, 74 + i
        ln = lines[i] if i < len(lines) else None
        _put(ws, f"B{r2}", i + 1)
        if ln is None:
            for col in "CDEFG":
                _put(ws, f"{col}{r}", None)
                _put(ws, f"{col}{r2}", None)
            _put(ws, f"H{r}", None)
            for ref in (f"I{r}", f"K{r}", f"K{r2}"):
                _put(ws, ref, 0)
            _put(ws, f"G{r2}", None)
            continue
        amt = round(line_amount("시험", ln))
        nm = _val(ln.get("name"))
        vals = {"C": _val(ln.get("spec")), "D": f"{nm or ''} ({ch_tag(ln)})" if ch_tag(ln) else nm,
                "E": _val(ln.get("count")), "F": _val(ln.get("qty")), "G": _val(ch_price(ln)),
                "H": _val(ln.get("difficulty"))}
        for col, v in vals.items():
            _put(ws, f"{col}{r}", v)
        for col in "CDEF":
            _put(ws, f"{col}{r2}", vals[col])
        _put(ws, f"I{r}", amt)
        _put(ws, f"K{r}", amt)
        _put(ws, f"G{r2}", amt)
        _put(ws, f"K{r2}", amt)
    p1, p2 = _val(q.get("disc1")) or None, _val(q.get("disc2")) or None
    for a, b in ((29, 83), (31, 85)):
        _put(ws, f"K{a}", t["eq"] if a == 29 else t["after"])
        _put(ws, f"K{b}", t["eq"] if a == 29 else t["after"])
    _put(ws, "G30", p1)
    _put(ws, "K30", t["d1"])
    _put(ws, "G84", p1)
    _put(ws, "I84", None)
    _put(ws, "K84", t["d1"])
    extras = (list(q.get("extras") or []) + [{}] * 3)[:3]
    for i, ex in enumerate(extras):
        r, r2 = 34 + i, 88 + i
        blank = is_blank_line(ex)
        amt = 0 if blank else round(extra_amount(ex))
        name = _val(ex.get("name"))
        _put(ws, f"C{r}", name)
        _put(ws, f"F{r}", _val(ex.get("qty")))
        _put(ws, f"G{r}", _val(ex.get("price")))
        _put(ws, f"H{r}", amt)
        _put(ws, f"K{r}", amt)
        _put(ws, f"B{r2}", i + 1)
        _put(ws, f"C{r2}", name)
        _put(ws, f"F{r2}", amt)
        _put(ws, f"K{r2}", amt)
    for a, b, v in ((37, 91, t["extras"]), (38, 92, t["both"]), (39, 93, t["d2"]), (40, 94, t["final"]),
                    (43, 97, t["vat"])):
        _put(ws, f"K{a}", v)
        _put(ws, f"K{b}", v)
    _put(ws, "G39", p2)
    _put(ws, "G93", p2)
    rem = q.get("remarks")
    rem = DEFAULT_REMARKS["시험"] if rem is None else rem
    _put(ws, "B42", rem)
    _put(ws, "B96", rem)
    for r in range(44, 49):  # 2쪽 아래 안내 문구 = 1쪽과 같게
        _put(ws, f"B{r + 54}", ws[f"B{r}"].value)


_REF = re.compile(r"^=\$?([A-Z]{1,3})\$?(\d+)$")


def _resolve_formulas(ws) -> None:
    """남은 수식은 PDF 프로그램이 다시 계산하지 않을 수 있어 값으로 바꿉니다 (=C9 처럼 칸을 가리키는 것만)."""
    for _ in range(3):
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    m = _REF.match(v.replace(" ", ""))
                    if m:
                        ref = ws[f"{m.group(1)}{m.group(2)}"].value
                        if not (isinstance(ref, str) and ref.startswith("=")):
                            c.value = ref
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.value = None


def fill_xlsx(q: dict, part: str = "all") -> bytes:
    """견적서 엑셀(원래 양식)을 채워 돌려줍니다. part: 'all' | 'customer'(업체용 쪽만) | 'internal'(내부보관용 쪽만)."""
    import openpyxl
    form = q.get("form", "제조") if q.get("form") in FORMS else "제조"
    wb = openpyxl.load_workbook(TEMPLATES[form])
    ws = wb.active
    d = q.get("date")
    if isinstance(d, str):
        try:
            d = dt.date.fromisoformat(d[:10])
        except ValueError:
            d = dt.date.today()
    d = d or dt.date.today()
    t = totals(q)
    if form == "시험":
        _fill_test(ws, q, d, t)
    else:
        _fill_mfg(ws, q, d, t)
    _resolve_formulas(ws)
    # 한 쪽 너비에 맞춰 인쇄 (글꼴이 조금 달라도 오른쪽이 잘리지 않게)
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    if form == "시험" and part in ("customer", "internal"):
        ws.print_area = "A55:L103" if part == "customer" else "A1:L54"
        ws.row_breaks.brk = []
        ws.page_setup.fitToHeight = 1
    ws.title = "견적서"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── PDF ─────────────────────────────────────────────────────────

def soffice_path() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in ("/usr/bin/soffice", "/usr/lib/libreoffice/program/soffice", "/opt/libreoffice/program/soffice"):
        if os.path.exists(p):
            return p
    return None


def can_pdf() -> bool:
    return soffice_path() is not None


class PdfError(Exception):
    pass


def to_pdf(xlsx: bytes, timeout: int = 90) -> bytes:
    exe = soffice_path()
    if not exe:
        raise PdfError("PDF를 만드는 프로그램(LibreOffice)이 서버에 없습니다.")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "quote.xlsx")
        with open(src, "wb") as f:
            f.write(xlsx)
        env = dict(os.environ, HOME=tmp)
        fc = os.path.join(ASSETS, "fonts.conf")
        if os.path.exists(fc):
            env["FONTCONFIG_FILE"] = fc
        cmd = [exe, f"-env:UserInstallation=file://{tmp}/profile", "--headless", "--norestore",
               "--convert-to", "pdf", "--outdir", tmp, src]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout, env=env)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise PdfError(f"PDF를 만들지 못했습니다: {e}") from e
        out = os.path.join(tmp, "quote.pdf")
        if not os.path.exists(out):
            raise PdfError("PDF를 만들지 못했습니다.")
        with open(out, "rb") as f:
            return f.read()


def file_name(q: dict, ext: str = "pdf", part: str = "") -> str:
    """'RAT-2611-145_장비사용 견적서_아모그린텍.pdf' (예전 파일 이름 모양)."""
    bad = r'[\\/:*?"<>|]'
    kind = "장비사용 견적서" if q.get("form") == "제조" else (q.get("title") or "견적서")
    name = f"{q.get('no', '견적서')}_{kind}_{q.get('company', '')}".strip("_")
    if part == "internal":
        name += "_내부보관용"
    return re.sub(bad, "", name) + "." + ext
