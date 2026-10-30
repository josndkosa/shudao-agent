"""规划段：LLM Function Calling 在线规划 + 离线贪心兜底 + 修复。

离线规划器是"断网仍能演示"的保命底座：
偏好打分 -> 城市分天 -> 逐日贪心装箱 -> 最近邻排序 -> 时间线推算。
每一步都向 EventBus 发带 reason 的决策事件，供前端可倒带时间轴回放。
"""
from __future__ import annotations

import json

from ..tools import budget, leg_time, load_pois, poi_search, route, weather
from . import llm as llm_mod
from .events import EventBus

DAY_START = 8.5
DAY_END = 22.0
MEAL_HOURS = 2.0
BUFFER = 0.5
CITY_HUB = {
    "成都": {"lat": 30.6606, "lng": 104.0558, "name": "人民公园"},
    "重庆": {"lat": 29.5568, "lng": 106.5770, "name": "解放碑"},
}
POI_INDEX = {p["id"]: p for p in load_pois()}


def _fmt(h):
    return f"{int(h):02d}:{int(round((h - int(h)) * 60)):02d}"


def _poi_brief(p):
    return {
        "id": p["id"], "name": p["name"], "city": p["city"], "tags": p["tags"],
        "ticket": p["ticket"], "visit_hours": p["visit_hours"], "open_hour": p["open_hour"],
        "score": p.get("_score", 0), "reasons": p.get("_reasons", []),
    }


def _allocate_days(days, pools):
    """按候选池总分比例给两城分配天数；days=1 时聚焦总分更高的单一城市。"""
    cities = [c for c in pools if pools[c]]
    if not cities:
        return {}
    if len(cities) == 1:
        return {cities[0]: days}
    if days == 1:
        # 单日行程无法双城：只选候选池总分更高的城市，避免天数超发
        best = max(cities, key=lambda c: sum(x["_score"] for x in pools[c]))
        return {best: 1}
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


def _trim_to_capacity(ordered, city, has_intercity=False):
    """排序后用相邻跳真实值复核容量，超容摘点。

    摘点优先级：低分先摘 → 同分非必游先摘 → 再非夜间先摘（夜间点是压轴体验）。
    每次摘点后重算 content，直到满足容量；不允许摘到当天一个点都不剩。
    必须在 emit 选点 decision 之前调用，保证事件流就是最终结果。
    返回新列表，不修改调用方的 ordered。
    """
    capacity = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - (1.8 if has_intercity else 0)
    kept = list(ordered)
    while len(kept) > 1 and _content_hours(kept, city) > capacity + 1e-9:
        # 升序键：低分先摘；同分时非必游（False=0）先摘、再非夜间（False=0）先摘
        drop_rank = sorted(kept, key=lambda p: (
            p.get("_score", 0), p.get("must_see", False), p.get("night_friendly", False)))
        kept.remove(drop_rank[0])
    return kept


def _build_timeline(day_pois, hub, has_intercity=False):
    """时间线推算：逐点累加交通+游玩，12:00 午餐 / 18:00 晚餐各 1h。"""
    items, t, cur = [], DAY_START, hub
    if has_intercity:
        items.append({"type": "intercity", "label": "成渝高铁",
                       "arrival": _fmt(DAY_START), "departure": _fmt(DAY_START + 1.8)})
        t = DAY_START + 1.8
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
    if not dinner and items:
        items.append({"type": "meal", "label": "晚餐",
                       "arrival": _fmt(min(t, 20.0)), "departure": _fmt(min(t + 1, 21.0))})
    return items


def _day_load(day_pois, city, has_intercity=False):
    """日负载：含枢纽→首点的第一段交通，与 timeline 实际排程一致。"""
    hours = MEAL_HOURS + BUFFER + (1.8 if has_intercity else 0)
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
    for city in ("成都", "重庆"):
        r = poi_search(city=city, tags=request.tags, family=request.family)
        bus.emit("plan", "tool_call", f"poi_search({city})",
                 reason=f"检索{city}候选并按偏好打分", tool="poi_search", args={"city": city, "tags": request.tags})
        pools[city] = r["pois"]
        bus.emit("plan", "tool_result", f"{city}候选 {r['count']} 个",
                 reason="top3: " + "、".join(x["name"] for x in r["pois"][:3]), count=r["count"])
    if all(not pools[c] for c in pools):
        bus.emit("plan", "fallback", "无匹配候选", reason="偏好过滤后为空，放宽标签重试")
        pools = {c: poi_search(city=c)["pois"] for c in pools}

    alloc = _allocate_days(request.days, pools)
    alloc_desc = "、".join(f"{c}{n}天" for c, n in alloc.items())
    if len(alloc) > 1:
        reason = "按两城候选池总分比例分配"
    elif request.days == 1 and len(pools) > 1:
        best_city = next(iter(alloc))
        other = [c for c in pools if c != best_city][0]
        reason = f"单日行程聚焦{best_city}：候选池总分高于{other}"
    else:
        reason = "单城深耕"
    bus.emit("plan", "decision", f"城市分天：{alloc_desc}", reason=reason, detail=alloc)

    wx = {c: weather(c) for c in alloc}
    bus.emit("plan", "tool_call", "weather(成都/重庆)", reason="本地天气快照，校验段用于雨天调整", tool="weather")
    cd, cq = wx.get("成都", {}).get("day", ""), wx.get("重庆", {}).get("day", "")
    bus.emit("plan", "tool_result", f"成都{cd} / 重庆{cq}",
             reason="11月成渝典型气候", detail=wx)

    itinerary_days, day_no, prev_city = [], 1, None
    for city, n_days in alloc.items():
        for i in range(n_days):
            switch = prev_city is not None and prev_city != city
            capacity = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - (1.8 if switch else 0)
            pool = pools[city]
            picked = _pick_day_pois(pool, capacity, CITY_HUB[city])
            if not picked:
                continue
            ordered = _order_day(picked, CITY_HUB[city])
            # 相邻跳口径复核容量（与 validator 同尺），超容摘点在 emit 决策前完成
            ordered = _trim_to_capacity(ordered, city, has_intercity=switch)
            if not ordered:
                continue
            bus.emit("plan", "decision", f"第{day_no}天选点 {len(ordered)} 个",
                     reason="；".join(f"{p['name']}({'/'.join(p.get('_reasons', ['基础候选']))})" for p in ordered),
                     detail=[p["id"] for p in ordered])
            items = _build_timeline(ordered, CITY_HUB[city], has_intercity=switch)
            load = _day_load(ordered, city, has_intercity=switch)
            itinerary_days.append({
                "day": day_no, "city": city, "weather": wx[city], "items": items, "load": load,
            })
            for p in ordered:
                if p in pools[city]:
                    pools[city].remove(p)
            day_no += 1
            prev_city = city

    tickets_total = sum(d["load"]["tickets"] for d in itinerary_days)
    b = budget(request.days, tickets_total, intercity_price=154 if len(alloc) > 1 else 0, family=request.family)
    bus.emit("plan", "tool_call", "budget(...)", reason="核算门票+餐饮+交通", tool="budget")
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
    multi = len({dd["city"] for dd in plan["days"]}) > 1
    plan["budget"] = budget(request.days, tickets_total, intercity_price=154 if multi else 0,
                            family=request.family)
    return plan


def _is_must(item):
    p = POI_INDEX.get(item.get("poi_id"))
    return bool(p and p.get("must_see"))


def _refresh_day(d):
    day_pois = [POI_INDEX[it["poi_id"]] for it in d["items"] if it["type"] == "poi"]
    hub = CITY_HUB[d["city"]]
    has_ic = any(it["type"] == "intercity" for it in d["items"])
    d["items"] = _build_timeline(day_pois, hub, has_intercity=has_ic)
    d["load"] = _day_load(day_pois, d["city"], has_intercity=has_ic)


def _normalize_llm_plan(raw, request, bus: EventBus):
    """把 LLM 返回的 JSON 归一化为离线规划器同构结构。

    LLM 只保证 days/items/budget 骨架；字段以本地快照为准：
    - 非法 poi_id 丢弃（宁可少排，不让管线崩）
    - 时间线/负载/预算按离线同款口径重算，保证校验段可读
    - days 为空或无合法点位时抛 ValueError，由 llm_plan 统一降级离线
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("days"), list) or not raw["days"]:
        raise ValueError("LLM 计划 days 为空")
    days_out, prev_city = [], None
    for i, d in enumerate(raw["days"], start=1):
        if not isinstance(d, dict):
            continue
        day_pois, dropped = [], 0
        for it in d.get("items") or []:
            if not isinstance(it, dict) or it.get("type", "poi") != "poi":
                continue
            pid = it.get("poi_id") or it.get("id")
            if pid in POI_INDEX:
                day_pois.append(POI_INDEX[pid])
            else:
                dropped += 1
        if dropped:
            bus.emit("plan", "fallback", f"丢弃 {dropped} 个非法 POI",
                     reason="不在本地快照中，宁可少排不崩管线")
        if not day_pois:
            continue
        city = d.get("city") if d.get("city") in CITY_HUB else day_pois[0]["city"]
        has_ic = prev_city is not None and prev_city != city
        items = _build_timeline(day_pois, CITY_HUB[city], has_intercity=has_ic)
        load = _day_load(day_pois, city, has_intercity=has_ic)
        days_out.append({
            "day": d.get("day") or i, "city": city,
            "weather": weather(city), "items": items, "load": load,
        })
        prev_city = city
    if not days_out:
        raise ValueError("LLM 计划无合法点位")
    tickets_total = sum(d["load"]["tickets"] for d in days_out)
    multi_city = len({d["city"] for d in days_out}) > 1
    b = budget(request.days, tickets_total, intercity_price=154 if multi_city else 0, family=request.family)
    bus.emit("plan", "tool_call", "budget(...)", reason="归一化后按本地口径重算预算", tool="budget")
    bus.emit("plan", "tool_result", f"预估总花费 {b['total']} 元", reason=f"预算{request.budget}元", detail=b)
    return {"days": days_out, "budget": b, "mode": "llm-fc"}


def llm_plan(request, bus: EventBus):
    """在线规划：DeepSeek FC，工具结果来自本地快照。任何异常降级离线。"""
    try:
        system = (
            "你是西南文旅行程规划师。规则：先调用 poi_search 获取两城候选并打分，"
            "再调用 route 估算交通，最后输出 JSON 行程（含 days/items/budget）。"
            "每日 08:30 出发 22:00 前结束，午晚餐各 1 小时，点位须在开放时段内。"
            "输出 JSON，不要输出其他文字。"
        )
        user = json.dumps({
            "days": request.days, "budget": request.budget, "tags": request.tags,
            "family": request.family, "cities": ["成都", "重庆"],
        }, ensure_ascii=False)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        def exec_tool(name, args):
            if name == "poi_search":
                return poi_search(**args)
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
                                 "content": json.dumps(result, ensure_ascii=False)[:4000]})
            msg, kind = llm_mod.chat(messages, tools=llm_mod.TOOL_SCHEMAS)
        content = msg.content or ""
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            plan = json.loads(content[start:end + 1])
            plan = _normalize_llm_plan(plan, request, bus)
            bus.emit("plan", "done", "LLM 规划完成（已归一化）",
                     reason=f"{rounds} 轮工具调用，结构对齐离线规划器")
            return plan
        raise ValueError("LLM 输出中未找到 JSON")
    except Exception as e:
        bus.emit("plan", "fallback", "LLM 规划降级为离线规划器",
                 reason=f"{type(e).__name__}: {e}")
        return offline_plan(request, bus)
