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
          "color": "#F59E0B", "ch": "", "d0": d[0], "d1": d[2], "n": 3}
    data = {"days": d, "off": set(), "m0": d[0],
            "rows": [{"id": 5, "name": "코터", "full": "코터", "parent": "", "sec": "라인", "lanes": [[it]], "total": 24},
                     {"id": 6, "name": "프레스", "full": "프레스", "parent": "", "sec": "라인", "lanes": [[]], "total": 0}]}
    h = eg.to_html(data, d[1], {"log": 7})
    assert "colspan='3'" in h and "data-log='7'" in h and "picked" in h
    assert h.count("data-eid='6'") == 3  # 빈 줄은 날짜마다 누를 수 있는 칸
