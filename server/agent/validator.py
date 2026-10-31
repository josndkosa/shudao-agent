"""校验段：纯规则引擎，不依赖 LLM —— 「LLM 产出 + 规则校验」的工程卖点。

规则（软硬分级）：
  V1 时长      hard   内容时长 Σ(交通+游玩) 不超规划器同款容量（跨城日扣城际 1.8h）；收班 ≤ 22:00
  V2 开放窗口  hard   到离时间须落在 POI open_hour 内
  V3 强度      soft   日 Σ(slope + crowd_level*0.4) ≤ 8.5 —— 软约束：只提醒不自动修复
  V4 预算      hard   门票+餐饮+交通 ≤ 请求预算
  V5 亲子      hard   family 模式排除 family<2 的点（双保险）
severity: hard=必须自动修复并回流；soft=仅 advisory 提醒，不进修复循环。
"""
from __future__ import annotations

from ..tools import budget
from ..tools.poi_search import _load_meta
from ..tools.route import intercity_cost
from .planner import BUFFER, DAY_END, DAY_START, MEAL_HOURS, POI_INDEX

# V3 强度阈值按城市地形分档（meta.json city_info.terrain.intensity_cap）：
# 同样的"强度 8.5"，在成都盆地只是多走路，在昆明 1891m 高原与拉萨 3650m 高原完全是另一回事。
# 无地形配置的城市回落到该默认值（保持旧行为）。
INTENSITY_CAP = 8.5
_TERRAIN_CAP = {c: v["terrain"]["intensity_cap"] for c, v in _load_meta()["city_info"].items()}


def _parse_h(s):
    h, m = s.split(":")
    return int(h) + int(m) / 60.0


def _ic_hours(day):
    """从 day 的 intercity 条目推导城际时长——时间线是唯一事实源，与城市对解耦。"""
    for it in day["items"]:
        if it["type"] == "intercity":
            return round(_parse_h(it["departure"]) - _parse_h(it["arrival"]), 2)
    return 0.0


def validate(plan, request):
    violations = []
    for d in plan.get("days", []):
        poi_items = [it for it in d["items"] if it["type"] == "poi"]


        if poi_items:
            last_dep = _parse_h(poi_items[-1]["departure"])
            # 与规划器同款容量模型：跨城日的城际时长在容量里预留，不在 span 里重复加
            cap = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - _ic_hours(d)
            content_hours = sum(it.get("leg_hours", 0) + it.get("visit_hours", 0) for it in poi_items)
            if last_dep > DAY_END:
                violations.append({"rule": "V1-duration", "severity": "hard",
                                   "day": d["day"], "poi": poi_items[-1]["poi_id"],
                                   "detail": f"收班超时：{_parse_h(poi_items[-1]['departure']):.2f}h 结束超过 22:00",
                                   "fix_hint": "drop"})
            if content_hours > cap + 0.01:
                violations.append({"rule": "V1-duration", "severity": "hard", "day": d["day"], "poi": None,
                                   "detail": f"内容时长 {content_hours:.1f}h 超过容量 {cap:.1f}h",
                                   "fix_hint": "drop"})

        for it in poi_items:
            p = POI_INDEX.get(it["poi_id"])
            if not p:
                violations.append({"rule": "V5-unknown", "severity": "hard", "day": d["day"], "poi": it["poi_id"],
                                   "detail": "POI 不在本地快照中", "fix_hint": "drop"})
                continue
            arr, dep = _parse_h(it["arrival"]), _parse_h(it["departure"])
            o0, o1 = p["open_hour"]
            if arr < o0 or dep > o1:
                violations.append({"rule": "V2-open-window", "severity": "hard", "day": d["day"], "poi": it["poi_id"],
                                   "detail": f"排 {arr:.1f}-{dep:.1f}h 但开放 {o0}-{o1}h",
                                   "fix_hint": "drop"})
            if request.family and p["family"] < 2:
                violations.append({"rule": "V5-family", "severity": "hard", "day": d["day"], "poi": it["poi_id"],
                                   "detail": f"亲子友好度 {p['family']}<2", "fix_hint": "drop"})

        intensity = sum(POI_INDEX[it["poi_id"]]["slope"] + POI_INDEX[it["poi_id"]]["crowd_level"] * 0.4
                        for it in poi_items if it["poi_id"] in POI_INDEX)
        cap = _TERRAIN_CAP.get(d["city"], INTENSITY_CAP)
        if intensity > cap:
            worst = max(poi_items, key=lambda x: POI_INDEX[x["poi_id"]]["slope"] if x["poi_id"] in POI_INDEX else 0)
            violations.append({"rule": "V3-intensity", "severity": "soft", "day": d["day"], "poi": worst["poi_id"],
                               "detail": f"强度 {intensity:.1f} 超过 {cap}", "fix_hint": "none"})

    tickets_total = sum(d["load"]["tickets"] for d in plan.get("days", []))
    b = budget(request.days, tickets_total, intercity_price=intercity_cost(plan.get("days", [])),
               family=request.family)
    plan["budget"] = b
    if b["total"] > request.budget:
        day_max = max(plan.get("days", []), key=lambda d: d["load"]["tickets"]) if plan.get("days") else None
        violations.append({"rule": "V4-budget", "severity": "hard",
                           "day": day_max["day"] if day_max else 0, "poi": None,
                           "detail": f"预估 {b['total']} 元 > 预算 {request.budget} 元", "fix_hint": "drop"})
    return violations
