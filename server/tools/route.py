from .geo import haversine

ROAD_FACTOR = 1.35
CITY_SPEED = 28.0
WALK_SPEED = 4.5
INTERCITY_RAIL = {"成都-重庆": {"hours": 1.8, "price": 154}}


def _mode_kmh(a, b):
    d = haversine(a["lat"], a["lng"], b["lat"], b["lng"])
    return d


def leg_time(a, b):
    """两点间市内交通耗时（小时）：道路系数 + 市区均速。"""
    d = _mode_kmh(a, b) * ROAD_FACTOR
    return d / CITY_SPEED


def walk_time(a, b):
    d = _mode_kmh(a, b) * ROAD_FACTOR
    return d / WALK_SPEED


def intercity(city_a, city_b):
    key = "-".join(sorted([city_a, city_b]))
    return INTERCITY_RAIL.get(key, {"hours": 3.0, "price": 200})


def route(frm, to, mode="city"):
    """route 工具：距离/耗时估算，全本地计算。"""
    if mode == "intercity":
        info = intercity(frm["city"], to["city"]) if "city" in frm and "city" in to else {"hours": 3.0, "price": 200}
        return {"mode": "intercity", "km": 268, "hours": info["hours"], "price": info["price"]}
    if mode == "walk":
        h = walk_time(frm, to)
        km = _mode_kmh(frm, to)
    else:
        h = leg_time(frm, to)
        km = _mode_kmh(frm, to)
    return {
        "mode": mode,
        "km": round(km, 2),
        "hours": round(h, 2),
        "price": round(max(km * ROAD_FACTOR, 2.0) * 1.8, 0),
    }
