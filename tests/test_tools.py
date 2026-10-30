import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.tools import budget, poi_search, route, weather


def test_poi_search_tag_hit():
    r = poi_search(city="成都", tags=["美食"])
    assert r["count"] > 0
    assert any("美食" in p["tags"] for p in r["pois"])


def test_poi_search_family_filter():
    r = poi_search(city="成都", tags=["夜生活"], family=True)
    for p in r["pois"]:
        assert p["family"] >= 2


def test_poi_search_alias():
    r = poi_search(city="重庆", tags=["遛娃"])
    assert r["count"] > 0


def test_budget_math():
    b = budget(3, 300, intercity_price=154)
    assert b["tickets"] == 300
    assert b["transit"] == 35 * 3 + 154
    assert b["total"] == b["tickets"] + b["meals"] + b["transit"]


def test_weather_snapshot():
    w = weather("重庆")
    assert w["source"] == "local-snapshot"
    assert len(w["temp"]) == 2


def test_route_intercity():
    r = route({"city": "成都"}, {"city": "重庆"}, mode="intercity")
    assert r["mode"] == "intercity" and r["price"] > 0
