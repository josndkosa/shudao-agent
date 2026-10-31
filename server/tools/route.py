from .geo import haversine
from .poi_search import _load_meta

ROAD_FACTOR = 1.35
CITY_SPEED = 28.0
WALK_SPEED = 4.5
# 城际铁路人工覆盖表来自 data/meta.json（数据层 v2：新增城际线只改数据文件）
INTERCITY_RAIL = _load_meta()["intercity_rail"]
_CITY_HUB = _load_meta()["city_hub"]
_CITY_PROV = {c: v["province"] for c, v in _load_meta()["city_info"].items()}
# 跨省长途（川渝黔 → 桂/琼/藏）的时长上浮系数：铁路网绕行 + 车次少
_FAR_PROVINCES = {"西藏", "海南", "广西"}


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


def _gen_intercity(city_a, city_b):
    """按两城枢纽球面距离自动生成城际交通（覆盖表未收录的城对）。

    时长 = clamp(1.2 + d/250, 1.2, 14.0)；进藏城对 d 按 2.0 绕行系数计
    （直线 ~1250km 但铁路/公路实际 ~2500km），跨省进桂/琼/藏再上浮 1.25；
    票价 = round(clamp(d*0.48, 60, 2200) / 10) * 10（按直线距离，贴近真实票价档）。
    """
    a, b = _CITY_HUB[city_a], _CITY_HUB[city_b]
    d = haversine(a["lat"], a["lng"], b["lat"], b["lng"])
    pa, pb = _CITY_PROV.get(city_a), _CITY_PROV.get(city_b)
    detour = 2.0 if "西藏" in (pa, pb) else 1.0
    hours = 1.2 + d * detour / 250.0
    if (pa in _FAR_PROVINCES or pb in _FAR_PROVINCES) and pa != pb:
        hours *= 1.25
    hours = min(max(hours, 1.2), 14.0)
    price = round(min(max(d * 0.48, 60), 2200) / 10) * 10
    return {"hours": round(hours, 2), "price": price, "km": round(d)}


def intercity(city_a, city_b):
    """城际交通参数：人工覆盖表优先（如 成都-重庆 1.8h/¥154），其余按枢纽距离自动生成。"""
    key = "-".join(sorted([city_a, city_b]))
    if key in INTERCITY_RAIL:
        return INTERCITY_RAIL[key]
    if city_a in _CITY_HUB and city_b in _CITY_HUB:
        return _gen_intercity(city_a, city_b)
    return {"hours": 3.0, "price": 200, "km": 300}


def intercity_cost(days):
    """行程跨城段的城际票价合计（序列口径：相邻异城各计一段，多城多段如实累计）。"""
    total, prev = 0, None
    for d in days:
        if prev is not None and d["city"] != prev:
            total += intercity(prev, d["city"])["price"]
        prev = d["city"]
    return total


def route(frm, to, mode="city"):
    """route 工具：距离/耗时估算，全本地计算。"""
    if mode == "intercity":
        if "city" in frm and "city" in to:
            info = intercity(frm["city"], to["city"])
        else:
            info = {"hours": 3.0, "price": 200, "km": 300}
        return {"mode": "intercity", "km": info.get("km", 300), "hours": info["hours"], "price": info["price"]}
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
