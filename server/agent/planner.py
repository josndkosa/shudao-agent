"""规划段：LLM Function Calling 在线规划 + 离线贪心兜底 + 修复。

离线规划器是"断网仍能演示"的保命底座：
偏好打分 -> 城市分天 -> 逐日贪心装箱 -> 最近邻排序 -> 时间线推算。
每一步都向 EventBus 发带 reason 的决策事件，供前端可倒带时间轴回放。
"""
from __future__ import annotations

import json

from ..tools import budget, leg_time, load_pois, poi_search, route, weather
from ..tools.poi_search import _load_meta
from ..tools.route import intercity, intercity_cost
from . import llm as llm_mod
from .events import EventBus

DAY_START = 8.5
DAY_END = 22.0
MEAL_HOURS = 2.0
BUFFER = 0.5
# 城市枢纽坐标来自 data/meta.json——新增城市只改数据文件，不改代码（任务 D）
CITY_HUB = _load_meta()["city_hub"]
POI_INDEX = {p["id"]: p for p in load_pois()}


def _fmt(h):
    return f"{int(h):02d}:{int(round((h - int(h)) * 60)):02d}"


def _poi_brief(p):
    return {
        "id": p["id"], "name": p["name"], "city": p["city"], "tags": p["tags"],
        "ticket": p["ticket"], "visit_hours": p["visit_hours"], "open_hour": p["open_hour"],
        "score": p.get("_score", 0), "reasons": p.get("_reasons", []),
    }


def _tool_content(result, limit=4000):
    """工具结果进 messages 的安全序列化：超长时对 pois 列表尾部整点丢弃再序列化，
    绝不截在 JSON 中间——残缺 JSON 会被模型「补全」成幻觉 POI（03F 缺陷A根因）。"""
    s = json.dumps(result, ensure_ascii=False)
    if len(s) <= limit:
        return s
    pois = result.get("pois")
    if not isinstance(pois, list):
        return s[:limit]
    while pois:
        dropped = len(result["pois"]) - len(pois)
        out = {**result, "pois": pois, "count": len(pois)}
        if dropped:
            out["truncated"] = f"已按 score 降序截去尾部 {dropped} 个候选"
        s = json.dumps(out, ensure_ascii=False)
        if len(s) <= limit:
            return s
        pois = pois[:-1]
    return json.dumps({"count": 0, "pois": [], "truncated": "候选全部超长丢弃"},
                      ensure_ascii=False)


def _ic_leg(city_a, city_b):
    """城际段参数（hours + 车次名）：覆盖表带 label（成渝高铁），自动生成的城对用通用名。"""
    info = intercity(city_a, city_b)
    return {"hours": info["hours"], "label": info.get("label", f"{city_a}→{city_b} 列车")}


MAX_HOP_HOURS = 4.0   # 自动选城单跳城际上限：成渝1.8/渝贵2.5/贵昆3.5/昆大2.0 均在内；
                      # 成都→西双版纳 5.3h、阆中→昆明 4.4h 排除——到达已过半日，容量装不下大点，
                      # 亲子组曾因此摘成「空壳天」（坐5小时车去吃晚饭）。显式指定不受此限。


def _hop_hours(a, b):
    return intercity(a, b)["hours"]


def _apply_avoid(pois: list, avoid_tags: list) -> list:
    """排斥标签硬排除（03J）：命中即不进候选——不是打分扣分，是选点前的过滤。

    只在候选筛选这一步生效（poi_search 之后、打分装箱之前），不触碰 V1–V5 判定；
    空列表原样返回（行为与无记忆时逐字一致）。
    """
    if not avoid_tags:
        return pois
    avoid = set(avoid_tags)
    return [p for p in pois if not (set(p.get("tags", ())) & avoid)]


def _select_cities(request, bus: EventBus):
    """城市选择：request.cities 显式指定优先（过滤未收录城市）；空则自动选 N 城。

    批次2 算法：起点 = 候选池总分最高城；此后每跳在「距路线末端城际 ≤ MAX_HOP_HOURS」的
    未选城市中取总分最高者，无可达候选即停（宁少选城不选绕路/超长途）。
    一跳一跳选天然地理紧凑（不绕路）；总分优先保证城市质量——取代批次1 的
    「总分 top N + 最近邻重排」（该法把成都→西双版纳 5.3h 也串进一日切换）。
    """
    if request.cities:
        chosen = [c for c in request.cities if c in CITY_HUB]
        missing = [c for c in request.cities if c not in CITY_HUB]
        if missing:
            bus.emit("plan", "fallback", f"跳过未收录城市：{'、'.join(missing)}",
                     reason="本地快照暂未覆盖该城市，已从指定清单中剔除")
        if chosen:
            return chosen
        bus.emit("plan", "fallback", "指定城市均未收录", reason="回落为按候选池总分自动选城")
    r = poi_search(tags=request.tags, family=request.family)
    by_city = {}
    for p in r["pois"]:
        by_city[p["city"]] = by_city.get(p["city"], 0.0) + p.get("_score", 0)
    if not by_city:
        return []
    n = min(request.days, len(by_city))
    chosen = [max(by_city, key=lambda c: by_city[c])]
    rest = sorted((c for c in by_city if c not in chosen), key=lambda c: -by_city[c])
    while rest and len(chosen) < n:
        last = chosen[-1]
        reachable = [c for c in rest if _hop_hours(last, c) <= MAX_HOP_HOURS]
        if not reachable:
            break   # 距路线末端已无可达城市：宁少选城，不串超长途
        chosen.append(reachable[0])            # 可达候选中总分最高
        rest.remove(reachable[0])
    if chosen:
        score_desc = "、".join(f"{c}{by_city[c]:.1f}分" for c in chosen)
        hops = "、".join(f"{chosen[i]}→{chosen[i+1]} {_hop_hours(chosen[i], chosen[i+1])}h"
                         for i in range(len(chosen) - 1)) or "单城"
        bus.emit("plan", "decision", f"自动选城：{'、'.join(chosen)}",
                 reason=f"总分最高起点+逐跳≤{MAX_HOP_HOURS}h可达最高分（{score_desc}；{hops}）",
                 detail=chosen)
    return chosen


def _allocate_days(days, pools):
    """按候选池总分比例给各城分配天数；days=1 时聚焦总分更高的单一城市。"""
    cities = [c for c in pools if pools[c]]
    if not cities:
        return {}
    if len(cities) == 1:
        return {cities[0]: days}
    if days == 1:
        # 单日行程无法双城：只选候选池总分更高的城市，避免天数超发
        best = max(cities, key=lambda c: sum(x["_score"] for x in pools[c]))
        return {best: 1}
    if days < len(cities):
        # 天数不足以覆盖所有指定城市：取候选池总分前 days 城各 1 天（保持 pools 顺序），
        # 否则 min(take, 负数) 会产生负天数并被 range 吞掉、其余城各 1 天 → 天数超发（缺陷2的多城版）
        top = sorted(cities, key=lambda c: -sum(x["_score"] for x in pools[c]))[:days]
        return {c: 1 for c in cities if c in top}
    total = sum(sum(x["_score"] for x in pools[c]) for c in cities)
    alloc = {}
    if total <= 0:
        alloc = {c: 1 for c in cities}
        rest = days - len(cities)
        for i in range(rest):
            alloc[cities[i % len(cities)]] += 1
        return alloc
    remain = days
    for i, c in enumerate(cities):
        if i == len(cities) - 1:
            alloc[c] = remain
        else:
            take = max(1, round(days * sum(x["_score"] for x in pools[c]) / total))
            take = min(take, remain - (len(cities) - 1 - i))
            alloc[c] = take
            remain -= take
    return alloc


def _pick_day_pois(pool, capacity_hours, hub):
    """贪心装箱：种子=最高分，其后按 score/距离 综合扩张。"""
    chosen = []
    rest = sorted(pool, key=lambda x: -x["_score"])
    if not rest:
        return chosen
    seed = rest.pop(0)
    chosen.append(seed)
    used = seed["visit_hours"] + leg_time(hub, seed)

    def center():
        return {"lat": sum(x["lat"] for x in chosen) / len(chosen), "lng": sum(x["lng"] for x in chosen) / len(chosen)}

    while rest:
        c = center()
        best, best_gain = None, -1.0
        for x in rest:
            leg = leg_time(c, x)
            if used + leg + x["visit_hours"] > capacity_hours:
                continue
            gain = x["_score"] + 1.2 - 2.0 * leg   # 距离惩罚，避免一日千里
            if x["night_friendly"]:
                gain += 0.8                          # 夜间点天然适合日末
            # 轻度强度惩罚（软约束）：不得挤掉必游地标与夜间体验点（硬期待）
            if not x.get("must_see") and not x.get("night_friendly"):
                gain -= 0.25 * (x["slope"] + x["crowd_level"] * 0.4)
            if gain > best_gain:
                best, best_gain = x, gain
        if best is None:
            break
        chosen.append(best)
        used += leg_time(c, best) + best["visit_hours"]
        rest.remove(best)
    return chosen


def _order_day(pois, hub):
    """日内最近邻排序，夜间点强制排最后。"""
    if not pois:
        return []
    normal = [p for p in pois if not p["night_friendly"]]
    night = [p for p in pois if p["night_friendly"]]
    ordered, cur = [], hub
    pool = list(normal)
    while pool:
        nxt = min(pool, key=lambda x: leg_time(cur, x))
        ordered.append(nxt)
        pool.remove(nxt)
        cur = nxt
    ordered.extend(night)
    return ordered


def _content_hours(pois, city):
    """相邻跳口径的内容时长：与 validator 的 content_hours 同一把尺子。"""
    prev, total = CITY_HUB[city], 0.0
    for p in pois:
        total += leg_time(prev, p) + p["visit_hours"]
        prev = p
    return total


def _trim_to_capacity(ordered, city, ic=None):
    """排序后用相邻跳真实值复核容量，超容摘点。

    ic 为城际段参数（{"hours": ...}）或 None；跨城日容量按实际城际时长扣减。
    摘点优先级：低分先摘 → 同分非必游先摘 → 再非夜间先摘（夜间点是压轴体验）。
    每次摘点后重算 content，直到满足容量；不允许摘到当天一个点都不剩。
    必须在 emit 选点 decision 之前调用，保证事件流就是最终结果。
    返回新列表，不修改调用方的 ordered。
    """
    capacity = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - ((ic or {}).get("hours", 0.0))
    kept = list(ordered)
    while len(kept) > 1 and _content_hours(kept, city) > capacity + 1e-9:
        # 升序键：低分先摘；同分时非必游（False=0）先摘、再非夜间（False=0）先摘
        drop_rank = sorted(kept, key=lambda p: (
            p.get("_score", 0), p.get("must_see", False), p.get("night_friendly", False)))
        kept.remove(drop_rank[0])
    return kept


def _build_timeline(day_pois, hub, ic=None):
    """时间线推算：逐点累加交通+游玩，12:00 午餐 / 18:00 晚餐各 1h。

    ic 为城际段参数（{"hours": ..., "label": ...}）或 None；跨城日以城际车次开场。
    """
    items, t, cur = [], DAY_START, hub
    if ic:
        items.append({"type": "intercity", "label": ic["label"],
                      "arrival": _fmt(DAY_START), "departure": _fmt(DAY_START + ic["hours"])})
        t = DAY_START + ic["hours"]
    lunch, dinner = False, False
    for p in day_pois:
        leg = leg_time(cur, p)
        arrival = t + leg
        if not lunch and arrival > 12.0 - p["visit_hours"] * 0.2:
            lunch = True
            items.append({"type": "meal", "label": "午餐", "arrival": "12:00", "departure": "13:00"})
            arrival = max(arrival, 13.0)
        if not dinner and arrival > 18.0:
            dinner = True
            items.append({"type": "meal", "label": "晚餐", "arrival": "18:00", "departure": "19:00"})
            arrival = max(arrival, 19.0)
        departure = arrival + p["visit_hours"]
        items.append({
            "type": "poi", "poi_id": p["id"], "name": p["name"], "city": p["city"],
            "arrival": _fmt(arrival), "departure": _fmt(departure),
            "leg_hours": round(leg, 2), "visit_hours": p["visit_hours"],
            "ticket": p["ticket"], "tags": p["tags"],
            "reasons": p.get("_reasons", []), "summary": p["summary"],
        })
        t, cur = departure, p
    if not dinner and items and t > 18.0:
        # 收尾补晚餐只在天结束时间确实晚于 18:00 时——03F 任务B实跑缺陷：
        # 某天仅 1 点 12:55 结束也被硬插「晚餐 12:55–13:55」的时间线荒谬
        items.append({"type": "meal", "label": "晚餐",
                       "arrival": _fmt(min(t, 20.0)), "departure": _fmt(min(t + 1, 21.0))})
    if not lunch and not dinner and items:
        # 全天无餐（中午前结束的半天）也至少补一个午餐条目：
        # 时间线口径「至少一餐」，与 _day_load 按实际餐数计的负载口径保持一致
        items.append({"type": "meal", "label": "午餐",
                      "arrival": _fmt(min(t, 11.5)), "departure": _fmt(min(t + 1, 12.5))})
    return items


def _day_load(day_pois, city, ic=None, meal_count=None):
    """日负载：含枢纽→首点的第一段交通，与 timeline 实际排程一致。

    meal_count（03H 任务H1）：该天时间线里实际出现的餐条目数——时间线只有 1 餐时
    负载不能再按 2 餐算（旧口径固定加 MEAL_HOURS=2，与时间线口径不一致）；
    None 时按 2 餐计（历史默认，既有单测依赖）。
    """
    hours = (meal_count if meal_count is not None else MEAL_HOURS) * 1.0 \
        + BUFFER + ((ic or {}).get("hours", 0.0))
    hours += sum(p["visit_hours"] for p in day_pois)
    prev = CITY_HUB[city]
    for p in day_pois:
        hours += leg_time(prev, p)
        prev = p
    intensity = sum(p["slope"] + p["crowd_level"] * 0.4 for p in day_pois)
    tickets = sum(p["ticket"] for p in day_pois)
    return {"hours": round(hours, 2), "intensity": round(intensity, 2), "tickets": tickets}


def offline_plan(request, bus: EventBus):
    """离线贪心规划：管线默认底座。"""
    bus.emit("plan", "thought", "解析行程需求",
             reason=f"{request.days}天 预算{request.budget}元 偏好{request.tags or '不限'}"
                    f"{' 亲子模式' if request.family else ''}")
    pools = {}
    city_list = _select_cities(request, bus)
    for city in city_list:
        r = poi_search(city=city, tags=request.tags, family=request.family)
        bus.emit("plan", "tool_call", f"poi_search({city})",
                 reason=f"检索{city}候选并按偏好打分", tool="poi_search", args={"city": city, "tags": request.tags})
        kept = _apply_avoid(r["pois"], request.avoid_tags)
        if len(kept) < len(r["pois"]):
            bus.emit("plan", "fallback", f"{city}候选排除 {len(r['pois']) - len(kept)} 个排斥点位",
                     reason=f"命中偏好记忆的排斥标签：{'、'.join(request.avoid_tags)}（硬排除，不参与打分）")
        pools[city] = kept
        bus.emit("plan", "tool_result", f"{city}候选 {len(kept)} 个",
                 reason="top3: " + "、".join(x["name"] for x in kept[:3]), count=len(kept))
    if all(not pools[c] for c in pools):
        bus.emit("plan", "fallback", "无匹配候选", reason="偏好过滤后为空，放宽标签重试")
        # 放宽只针对「喜欢」标签——排斥标签（avoid_tags）是硬约束，重试里也保持排除
        pools = {c: _apply_avoid(poi_search(city=c)["pois"], request.avoid_tags) for c in pools}

    alloc = _allocate_days(request.days, pools)
    alloc_desc = "、".join(f"{c}{n}天" for c, n in alloc.items())
    if len(alloc) > 1:
        n_txt = "两" if len(alloc) == 2 else str(len(alloc))
        reason = f"按{n_txt}城候选池总分比例分配"
    elif request.days == 1 and len(pools) > 1:
        best_city = next(iter(alloc))
        other = [c for c in pools if c != best_city][0]
        reason = f"单日行程聚焦{best_city}：候选池总分高于{other}"
    elif len(pools) == 1 and not request.cities:
        c0 = next(iter(pools))
        reason = f"单日行程聚焦{c0}：候选池总分最高（西南多城快照中自动选出）"
    else:
        reason = "单城深耕"
    bus.emit("plan", "decision", f"城市分天：{alloc_desc}", reason=reason, detail=alloc)

    wx = {c: weather(c) for c in alloc}
    bus.emit("plan", "tool_call", f"weather({'/'.join(alloc)})",
             reason="本地天气快照，校验段用于雨天调整", tool="weather")
    if set(alloc) == {"成都", "重庆"}:
        cd, cq = wx.get("成都", {}).get("day", ""), wx.get("重庆", {}).get("day", "")
        wx_summary = f"成都{cd} / 重庆{cq}"
        wx_reason = "11月成渝典型气候"
    else:
        wx_summary = " / ".join(f"{c}{wx[c]['day']}" for c in alloc)
        wx_reason = f"11月{'、'.join(alloc)}典型气候"
    bus.emit("plan", "tool_result", wx_summary, reason=wx_reason, detail=wx)

    itinerary_days, day_no, prev_city = [], 1, None
    for city, n_days in alloc.items():
        for i in range(n_days):
            switch = prev_city is not None and prev_city != city
            ic = _ic_leg(prev_city, city) if switch else None
            capacity = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - (ic["hours"] if ic else 0)
            pool = pools[city]
            picked = _pick_day_pois(pool, capacity, CITY_HUB[city])
            if not picked:
                # 候选用尽不再静默丢天（03G）：用户要 12 天可能只拿到 9 天，
                # 「这一天为什么没了」必须可回放；day_no 未自增，该天不占用序号
                bus.emit("plan", "fallback", f"{city} 候选点已用尽，无法安排第 {day_no} 天",
                         reason=f"{city} 的 POI 已全部排入前序天数（单城约撑 4–5 天，"
                                f"天数多建议多选城市）")
                continue
            ordered = _order_day(picked, CITY_HUB[city])
            # 相邻跳口径复核容量（与 validator 同尺），超容摘点在 emit 决策前完成
            ordered = _trim_to_capacity(ordered, city, ic=ic)
            if not ordered:
                bus.emit("plan", "fallback", f"第 {day_no} 天容量不足，整天空排",
                         reason="跨城日城际耗时挤占后装不下任何点位，该天不占用序号")
                continue
            bus.emit("plan", "decision", f"第{day_no}天选点 {len(ordered)} 个",
                     reason="；".join(f"{p['name']}({'/'.join(p.get('_reasons', ['基础候选']))})" for p in ordered),
                     detail=[p["id"] for p in ordered])
            items = _build_timeline(ordered, CITY_HUB[city], ic=ic)
            load = _day_load(ordered, city, ic=ic,
                             meal_count=sum(1 for it in items if it["type"] == "meal"))
            itinerary_days.append({
                "day": day_no, "city": city, "weather": wx[city], "items": items, "load": load,
            })
            for p in ordered:
                if p in pools[city]:
                    pools[city].remove(p)
            day_no += 1
            prev_city = city

    tickets_total = sum(d["load"]["tickets"] for d in itinerary_days)
    # 预算分母用实际行程天数（03G）：days=12 被候选密度截成 9 天时，餐饮/市内交通/日均
    # 都按 9 算——用 request.days 会系统性低估日均；城际费用本就按实际 days 序列计
    b = budget(len(itinerary_days), tickets_total, intercity_price=intercity_cost(itinerary_days),
               family=request.family)
    bus.emit("plan", "tool_call", "budget(...)", reason="核算门票+餐饮+交通", tool="budget")
    if len(itinerary_days) < request.days:
        bus.emit("plan", "tool_result", f"预估总花费 {b['total']} 元",
                 reason=f"按实际 {len(itinerary_days)} 天核算（请求 {request.days} 天，"
                        f"因候选点用尽未排满）", detail=b)
    else:
        bus.emit("plan", "tool_result", f"预估总花费 {b['total']} 元", reason=f"预算{request.budget}元", detail=b)
    return {"days": itinerary_days, "budget": b, "mode": "offline-planner"}


def fix(plan, violations, request, bus: EventBus):
    """按校验段违规清单定向修复。"""
    days = {d["day"]: d for d in plan["days"]}
    for v in violations:
        d = days.get(v["day"])
        if not d:
            continue
        poi_items = [it for it in d["items"] if it["type"] == "poi"]
        if v["rule"] == "V1-duration":
            drop = sorted(poi_items, key=lambda x: (x.get("must", 0), -x["visit_hours"]))
            drop = [x for x in drop if not _is_must(x)] or drop[:1]
            if drop:
                target = drop[0]
                d["items"] = [it for it in d["items"] if it is not target and it.get("poi_id") != target.get("poi_id")]
                bus.emit("plan", "fix", f"第{v['day']}天移除 {target.get('name')}",
                         reason=f"触发{v['rule']}：{v['detail']}", violation=v["rule"],
                         removed=[target.get("poi_id")])
                _refresh_day(d)

        elif v["rule"] == "V2-open-window":
            for it in poi_items:
                if it.get("poi_id") == v.get("poi"):
                    d["items"] = [x for x in d["items"] if x is not it]
                    bus.emit("plan", "fix", f"第{v['day']}天移除 {it['name']}",
                             reason=f"开放时间冲突：{v['detail']}", violation=v["rule"],
                             removed=[it.get("poi_id")])
            _refresh_day(d)
        elif v["rule"] == "V4-budget":
            cand = sorted(poi_items, key=lambda x: -x.get("ticket", 0))
            cand = [x for x in cand if not _is_must(x)]
            if cand:
                target = cand[0]
                d["items"] = [it for it in d["items"] if it is not target and it.get("poi_id") != target.get("poi_id")]
                bus.emit("plan", "fix", f"第{v['day']}天移除高票价点 {target.get('name')}",
                         reason=f"预算超限：{v['detail']}", violation=v["rule"],
                         removed=[target.get("poi_id")])
                _refresh_day(d)
    tickets_total = sum(dd["load"]["tickets"] for dd in plan["days"])
    plan["budget"] = budget(len(plan["days"]), tickets_total,
                            intercity_price=intercity_cost(plan["days"]), family=request.family)
    return plan


def _is_must(item):
    p = POI_INDEX.get(item.get("poi_id"))
    return bool(p and p.get("must_see"))


def _ic_of_day(d):
    """从 day 的既有 intercity 条目还原城际段参数（时间线是唯一事实源）。"""
    for it in d["items"]:
        if it["type"] == "intercity":
            h, m = it["departure"].split(":")
            dep = int(h) + int(m) / 60.0
            h, m = it["arrival"].split(":")
            arr = int(h) + int(m) / 60.0
            return {"hours": round(dep - arr, 2), "label": it["label"]}
    return None


def _refresh_day(d):
    day_pois = [POI_INDEX[it["poi_id"]] for it in d["items"] if it["type"] == "poi"]
    hub = CITY_HUB[d["city"]]
    ic = _ic_of_day(d)
    d["items"] = _build_timeline(day_pois, hub, ic=ic)
    d["load"] = _day_load(day_pois, d["city"], ic=ic,
                          meal_count=sum(1 for it in d["items"] if it["type"] == "meal"))


def _normalize_llm_plan(raw, request, bus: EventBus):
    """把 LLM 返回的 JSON 归一化为离线规划器同构结构。

    LLM 只保证 days/items/budget 骨架；字段以本地快照为准：
    - 非法 poi_id 丢弃（宁可少排，不让管线崩）
    - 同一 poi_id 只保留首次出现（跨天去重，03F 任务C：LLM 把同一点放进多天，
      fix 只修被报违规的天，残留重复点会同时出现在两天）
    - 整天无合法点位时发事件后跳过（静默丢天不可回放，违反「每条决策带 reason」内核）
    - 天号由我们连续分配（03I：模型原号在丢天后留洞——Day 1,2,4,5 跳号看起来像
      出错；编号连续才能让「编号=行程第几天」的直觉成立，模型原号只进事件 reason）
    - 时间线/负载/预算按离线同款口径重算，保证校验段可读
    - days 为空或无合法点位时抛 ValueError，由 llm_plan 统一降级离线
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("days"), list) or not raw["days"]:
        raise ValueError("LLM 计划 days 为空")
    days_out, prev_city, seen = [], None, {}
    day_seq = 0                      # 我们自己的连续天号，不信模型的
    for i, d in enumerate(raw["days"], start=1):
        if not isinstance(d, dict):
            continue
        model_day, day_city_hint = d.get("day"), d.get("city")
        day_pois, dropped, day_local = [], 0, set()
        for it in d.get("items") or []:
            if not isinstance(it, dict) or it.get("type", "poi") != "poi":
                continue
            pid = it.get("poi_id") or it.get("id")
            if pid not in POI_INDEX:
                dropped += 1
                continue
            if request.avoid_tags and (set(POI_INDEX[pid].get("tags", ())) & set(request.avoid_tags)):
                # 03J 兜底：LLM 仍选了排斥点位（幻觉/缓存语境）→ 丢弃并如实发事件
                bus.emit("plan", "fallback", f"丢弃排斥点位 {POI_INDEX[pid]['name']}",
                         reason=f"命中偏好记忆的排斥标签（{'、'.join(request.avoid_tags)}），硬排除")
                continue
            if pid in day_local:
                bus.emit("plan", "fallback", f"丢弃本天重复 POI {POI_INDEX[pid]['name']}",
                         reason="该点在本天已安排，只保留一次")
                continue
            if pid in seen:
                bus.emit("plan", "fallback", f"丢弃跨天重复 POI {POI_INDEX[pid]['name']}",
                         reason=f"该点已在第{seen[pid]}天安排（LLM 把同一点放进了多天）")
                continue
            day_local.add(pid)
            day_pois.append(POI_INDEX[pid])
        if dropped:
            bus.emit("plan", "fallback", f"丢弃 {dropped} 个非法 POI",
                     reason="不在本地快照中，宁可少排不崩管线")
        if not day_pois:
            extra = f"（模型原安排第 {model_day} 天）" if model_day else ""
            bus.emit("plan", "fallback", f"第{model_day or i}天未安排整天",
                     reason=f"{day_city_hint or '该城市'}无合法点位（候选全部非法或重复被清洗）{extra}",
                     day=model_day or i)
            continue
        city = day_city_hint if day_city_hint in CITY_HUB else day_pois[0]["city"]
        has_ic = prev_city is not None and prev_city != city
        ic = _ic_leg(prev_city, city) if has_ic else None
        day_seq += 1                 # 只给真正产出行程的天编号——被丢的不占号
        for pid in day_local:
            seen[pid] = day_seq       # 去重事件 reason 里的「第N天」= 最终显示号
        items = _build_timeline(day_pois, CITY_HUB[city], ic=ic)
        load = _day_load(day_pois, city, ic=ic,
                         meal_count=sum(1 for it in items if it["type"] == "meal"))
        days_out.append({
            "day": day_seq, "city": city,
            "weather": weather(city), "items": items, "load": load,
        })
        prev_city = city
    if not days_out:
        raise ValueError("LLM 计划无合法点位")
    tickets_total = sum(d["load"]["tickets"] for d in days_out)
    b = budget(len(days_out), tickets_total, intercity_price=intercity_cost(days_out), family=request.family)
    bus.emit("plan", "tool_call", "budget(...)", reason="归一化后按本地口径重算预算", tool="budget")
    bus.emit("plan", "tool_result", f"预估总花费 {b['total']} 元", reason=f"预算{request.budget}元", detail=b)
    return {"days": days_out, "budget": b, "mode": "llm-fc"}


def llm_plan(request, bus: EventBus):
    """在线规划：DeepSeek FC，工具结果来自本地快照。任何异常降级离线。"""
    try:
        city_list = _select_cities(request, bus)
        system = (
            "你是西南文旅行程规划师，只根据工具返回的真实数据规划，不得使用你自己的知识补充景点。"
            "流程：先 poi_search 获取候选（含 id/名称/开放时段/票价/游玩时长），"
            "必要时 route 估算交通，然后输出行程 JSON。"
            "硬约束：每日 08:30 出发、22:00 前结束；午晚餐各 1 小时；点位必须落在其 open_hour 内；"
            "跨城日需为城际交通预留时间；总花费不得超过用户预算，超预算时减少高票价点。"
            "禁造：poi_id 必须原样复制自 poi_search 返回的 id，禁止发明景点、票价、开放时段、天气；"
            "城市只能在用户给定的 cities 内选择。"
            "输出契约：只输出一个 JSON 对象，不要 markdown 代码块、不要任何解释文字。结构为 "
            '{"days":[{"day":1,"city":"城市名","items":[{"poi_id":"工具返回的id"}]}]}。'
            "days 长度必须等于用户天数；每天 items 2-5 个，只列 poi，不要输出用餐/城际条目；"
            "不要输出 arrival/departure/ticket/budget/narrative，这些由系统按本地数据重算。"
        )
        user = json.dumps({
            "days": request.days, "budget": request.budget, "tags": request.tags,
            "family": request.family, "cities": city_list,
        }, ensure_ascii=False) + "\n请按契约输出 days JSON，poi_id 只能来自 poi_search 返回。"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        def exec_tool(name, args):
            if name == "poi_search":
                r = poi_search(**args)
                # 03J：排斥标签硬排除在源头生效——LLM 看不到被排除的点，从根上断掉
                # 「模型选了博物馆再被清洗」的往返；归一化层还有兜底过滤
                kept = _apply_avoid(r["pois"], request.avoid_tags)
                return {"count": len(kept), "pois": [_poi_brief(p) for p in kept]}
            if name == "route":
                frm, to = POI_INDEX.get(args["from_id"]), POI_INDEX.get(args["to_id"])
                mode = args.get("mode", "city")
                if frm and to and mode == "intercity":
                    return route(frm, to, mode="intercity")
                if frm and to:
                    return route(frm, to)
                return {"error": "unknown poi id"}
            if name == "weather":
                return weather(args["city"], args.get("day_offset", 0))
            if name == "budget":
                return budget(args["days"], args["tickets_total"], args.get("intercity_price", 0),
                              args.get("family", request.family))
            return {"error": f"unknown tool {name}"}

        msg, kind = llm_mod.chat(messages, tools=llm_mod.TOOL_SCHEMAS)
        rounds = 0
        while kind == "tool_call" and rounds < 6:
            rounds += 1
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in msg.tool_calls]})
            for c in msg.tool_calls:
                args = json.loads(c.function.arguments or "{}")
                bus.emit("plan", "tool_call", f"{c.function.name}({json.dumps(args, ensure_ascii=False)})",
                         reason="LLM 自主决定调用", tool=c.function.name, args=args)
                result = exec_tool(c.function.name, args)
                bus.emit("plan", "tool_result", f"{c.function.name} 返回",
                         reason="本地快照执行结果", detail=str(result)[:200])
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": _tool_content(result)})
            msg, kind = llm_mod.chat(messages, tools=llm_mod.TOOL_SCHEMAS)
        content = (msg.content or "").strip()
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            start, end = content.find("{"), content.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM 输出中未找到 JSON")
            raw = json.loads(content[start:end + 1])
        plan = _normalize_llm_plan(raw, request, bus)
        bus.emit("plan", "done", "LLM 规划完成（已归一化）",
                 reason=f"{rounds} 轮工具调用，结构对齐离线规划器")
        return plan
    except Exception as e:
        bus.emit("plan", "fallback", "LLM 规划降级为离线规划器",
                 reason=f"{type(e).__name__}: {e}")
        return offline_plan(request, bus)
