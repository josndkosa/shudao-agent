import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.agent import TripRequest
from server.agent.planner import POI_INDEX
from server.agent.validator import validate


def _day(day_no, items, city="成都", tickets=0):
    return {"day": day_no, "city": city, "weather": {},
            "items": items, "load": {"hours": 10, "intensity": 0, "tickets": tickets}}


def _poi_item(pid, arrival, departure):
    p = POI_INDEX[pid]
    return {"type": "poi", "poi_id": pid, "name": p["name"], "arrival": arrival,
            "departure": departure, "visit_hours": p["visit_hours"], "ticket": p["ticket"],
            "leg_hours": 0.3, "tags": p["tags"]}


def test_v2_open_window_violation():
    plan = {"days": [_day(1, [_poi_item("CD-06", "19:00", "22:30")])]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    assert any(v["rule"] == "V2-open-window" for v in vs)


def test_v1_duration_violation():
    items = [_poi_item("CD-01", "08:30", "11:00"), _poi_item("CD-02", "21:00", "23:00")]
    plan = {"days": [_day(1, items)]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    assert any(v["rule"] == "V1-duration" for v in vs)


def test_v5_family_violation():
    plan = {"days": [_day(1, [_poi_item("CD-22", "20:00", "21:30")])]}
    vs = validate(plan, TripRequest(days=1, budget=99999, family=True))
    assert any(v["rule"] == "V5-family" for v in vs)


def test_v4_budget_violation():
    items = [_poi_item("CD-14", "09:00", "11:30"), _poi_item("CD-06", "13:00", "16:30")]
    plan = {"days": [_day(1, items, tickets=125)]}
    vs = validate(plan, TripRequest(days=1, budget=100))
    assert any(v["rule"] == "V4-budget" for v in vs)


def test_clean_plan_passes():
    items = [_poi_item("CD-01", "09:00", "11:30"), _poi_item("CD-05", "13:30", "15:00")]
    plan = {"days": [_day(1, items, tickets=0)]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    assert vs == []
