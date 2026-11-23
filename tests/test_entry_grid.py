"""장비 사용 등록 › 장비표 (views/entry_grid.py)."""
from views import entry_grid as eg


def test_short_company():
    assert eg.short_company("주식회사 앤비티에스") == "앤비티에스"
    assert eg.short_company("(주)엘지에너지솔루션") == "엘지에너지"
    assert eg.short_company("") == "내부"
    assert eg.company_color("") == eg.INNER
    assert eg.company_color("솔리텍") == eg.company_color("솔리텍")


def test_html_has_click_targets():
    import datetime as dt
    d = [dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 4)]
    it = {"log": 7, "s": d[0], "e": d[2], "period": True, "h": "8h/일", "co": "솔리텍", "full": "솔리텍",
          "color": "#F59E0B", "ch": "", "days": {x: 8.0 for x in d}, "vis": set(d)}
    data = {"days": d, "off": set(), "m0": d[0],
            "rows": [{"id": 5, "name": "코터", "full": "코터", "parent": "", "sec": "라인", "lanes": [[it]]},
                     {"id": 6, "name": "프레스", "full": "프레스", "parent": "", "sec": "라인", "lanes": [[]]}]}
    h = eg.to_html(data, d[1], {"log": 7})
    # 2026-11-23: 기간 실적도 칸마다 (엑셀처럼) — 날짜 칸 셋에 모두 시간·업체
    assert h.count("data-log='7'") == 3 and "picked" in h and "colspan" not in h
    assert h.count("<b>8</b>") == 3 and " jl" in h and " jr" in h
    assert h.count("data-eid='6'") == 3  # 빈 줄은 날짜마다 누를 수 있는 칸


def test_only_clicked_cell_is_marked():
    import datetime as dt
    d = [dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 4)]
    it = {"log": 7, "s": d[0], "e": d[2], "period": True, "h": "8h/일", "co": "내부", "full": "내부",
          "color": "#94A3B8", "ch": "", "days": {x: 8.0 for x in d}, "vis": set(d)}
    data = {"days": d, "off": set(), "m0": d[0],
            "rows": [{"id": 5, "name": "코터", "full": "코터", "parent": "", "sec": "라인", "lanes": [[it]]}]}
    h = eg.to_html(data, d[0], {"log": 7, "day": d[1]})
    assert h.count(" picked") == 1
