"""对话式改行程：纯规则意图解析 + 定向重排（离线可用，可倒带第二幕）。

意图解析（不依赖 LLM，断网保命）：
  目标天：第N天 / 第X天（中文一~七）/ day N；未指定天数时对「太赶/太松」取负载最高天
  动作：太赶/太满/太累/太紧/太多 → 减载（容量×0.8 重选）
        太松/太闲/加一个/加个/多排 → 加长（容量×1.15 重选，含未用候选）
        换掉X/去掉X/不想去X/删掉 → 移除点位（名称模糊匹配）
        先去X/放最前/放前面 → 重排顺序
执行：只动目标天，复用 planner 既有函数（_pick_day_pois/_build_timeline/_day_load），
      改后 validator 复查 + planner.fix 定向修复，全程发 revise/* 事件。
兜底：无法解析 → 原行程 + 友好提示事件，绝不报错。
"""
from __future__ import annotations

import re
from copy import deepcopy

from ..tools import poi_search
from .events import EventBus
from .narrator import narrate
from .planner import (
    BUFFER,
    CITY_HUB,
    DAY_END,
    DAY_START,
    MEAL_HOURS,
    POI_INDEX,
    _build_timeline,
    _day_load,
    _ic_of_day,
    _order_day,
    _pick_day_pois,
    _trim_to_capacity,
    fix,
)
from .validator import validate

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
REMOVE_WORDS = ("换掉", "去掉", "不想去", "删掉")
REORDER_WORDS = ("先去", "放最前", "放前面", "放最前面")
REDUCE_WORDS = ("太赶", "太满", "太累", "太紧", "太多")
EXTEND_WORDS = ("太松", "太闲", "加一个", "加个", "多排")


def _parse_day(msg: str):
    m = re.search(r"第([一二三四五六七1-7])天", msg)
    if m:
        tok = m.group(1)
        return CN_NUM.get(tok) or (int(tok) if tok.isdigit() else None)
    m = re.search(r"day\s*([1-7])", msg.lower())
    if m:
        return int(m.group(1))
    return None


def _parse_action(msg: str):
    for w in REMOVE_WORDS:
        if w in msg:
            return "remove", w
    for w in REORDER_WORDS:
        if w in msg:
            return "reorder", w
    for w in REDUCE_WORDS:
        if w in msg:
            return "reduce", w
    for w in EXTEND_WORDS:
        if w in msg:
            return "extend", w
    return "unknown", None


def _match_poi(day_pois, msg):
    """名称模糊匹配：POI 名按 ·/空格分段，任一段（≥2字）出现在消息里即命中。"""
    for p in day_pois:
        for part in p["name"].replace("·", " ").split():
            if len(part) >= 2 and part in msg:
                return p
    return None


def _fallback(entry, message, note):
    """兜底：原行程 + 友好提示事件，不报错（答辩演示稳定性优先）。"""
    bus: EventBus = entry["bus"]
    bus.emit("revise", "fallback", "未理解修改意图", reason=note)
    return {
        "itinerary": entry["itinerary"],
        "timeline": bus.timeline(),
        "revised_day": None,
        "message": note,
    }


def revise_plan(entry, message: str) -> dict:
    """entry：缓存条目 {itinerary, timeline, request, bus}；返回 API 契约结构。"""
    bus: EventBus = entry["bus"]
    request = entry["request"]
    plan = deepcopy(entry["itinerary"])
    days = plan.get("days", [])

    bus.emit("revise", "start", f"用户介入：{message}",
             reason="对话式改行程（纯规则意图解析，离线可用）")

    day_no = _parse_day(message)
    action, _w = _parse_action(message)
    if action == "unknown":
        return _fallback(entry, message, "没听懂想怎么改，请说明例如『第二天太赶』或『换掉九眼桥』")
    if day_no is None and action in ("reduce", "extend"):
        if not days:
            return _fallback(entry, message, "当前没有可修改的行程")
        day_no = max(days, key=lambda d: d["load"]["hours"])["day"]
        d = next(x for x in days if x["day"] == day_no)
        bus.emit("revise", "decision", f"未指定天数，选负载最高的第{day_no}天",
                 reason=f"该天负载 {d['load']['hours']}h 为全程最高")
    if day_no is None or not any(d["day"] == day_no for d in days):
        return _fallback(entry, message, "没听懂是第几天想改，请说明例如『第二天太赶』")

    d = next(x for x in days if x["day"] == day_no)
    city = d["city"]
    hub = CITY_HUB[city]
    ic = _ic_of_day(d)
    cur_pois = [POI_INDEX[it["poi_id"]] for it in d["items"] if it["type"] == "poi"]
    if not cur_pois:
        return _fallback(entry, message, f"第{day_no}天没有可调整的点位")
    base_cap = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - ((ic or {}).get("hours", 0.0))

    # 偏好分与规划段同口径（poi_search 打分），保证重选决策一致；显式覆盖防跨请求残留
    scored = poi_search(city=city, tags=list(request.tags), family=request.family)["pois"]
    smap = {p["id"]: p["_score"] for p in scored}
    for p in cur_pois:
        p["_score"] = smap.get(p["id"], 3.0)

    if action == "reduce":
        cap = base_cap * 0.8
        picked = _pick_day_pois(cur_pois, cap, hub)
        reason = f"因为你说第{day_no}天太赶，把当天容量收紧到 {cap:.1f}h 后从 {len(cur_pois)} 个点重选"
    elif action == "extend":
        cap = base_cap * 1.15
        used = {it["poi_id"] for x in days for it in x["items"] if it["type"] == "poi"}
        extra = [p for pid, p in POI_INDEX.items() if p["city"] == city and pid not in used]
        for p in extra:
            p["_score"] = smap.get(p["id"], 3.0)
        picked = _pick_day_pois(cur_pois + extra, cap, hub)
        reason = f"因为你说第{day_no}天太松，把容量放宽到 {cap:.1f}h 并纳入 {len(extra)} 个未用候选"
    elif action == "remove":
        target = _match_poi(cur_pois, message)
        if target is None:
            return _fallback(entry, message, f"没在第{day_no}天找到你想去掉的点位，请直接说景点名")
        picked = [p for p in cur_pois if p["id"] != target["id"]]
        reason = f"因为你说{message}，移除 {target['name']}"
    else:  # reorder
        target = _match_poi(cur_pois, message)
        if target is None:
            return _fallback(entry, message, f"没在第{day_no}天找到想提前的点位，请直接说景点名")
        picked = [target] + [p for p in cur_pois if p["id"] != target["id"]]
        reason = f"因为你说{message}，把 {target['name']} 提到当天最先"

    before_n = len(cur_pois)
    ordered = _order_day(picked, hub)
    ordered = _trim_to_capacity(ordered, city, ic=ic)
    d["items"] = _build_timeline(ordered, hub, ic=ic)
    d["load"] = _day_load(ordered, city, ic=ic)

    bus.emit("revise", "decision", f"第{day_no}天重排：{before_n} → {len(ordered)} 个点", reason=reason)
    bus.emit("revise", "tool_call", "rebuild_timeline(...)",
             reason="复用规划段 _build_timeline / _day_load 重算该天时间线与负载")
    bus.emit("revise", "tool_result", f"第{day_no}天重建完成",
             reason=f"负载 {d['load']['hours']}h · 强度 {d['load']['intensity']} · 门票 ¥{d['load']['tickets']}")

    # 复查：validate → 有硬违规则 fix → 再确认（复用管线同款逻辑）
    violations = validate(plan, request)
    hard = [v for v in violations if v.get("severity", "hard") == "hard"]
    soft = [v for v in violations if v.get("severity") == "soft"]
    if hard:
        for v in hard:
            bus.emit("validate", "violation", f"[{v['rule']}] 第{v['day']}天",
                     reason=f"改排后复查：{v['detail']}", detail=v)
        fix(plan, hard, request, bus)
        remain = [v for v in validate(plan, request) if v.get("severity", "hard") == "hard"]
        if remain:
            bus.emit("validate", "violation", "改排后仍残留硬违规", reason="已定向修复一次，残留项如实标注")
        else:
            bus.emit("validate", "pass", "改排后复查通过", reason="硬约束零违规")
    else:
        extra = f"；另有 {len(soft)} 条软提醒" if soft else ""
        bus.emit("validate", "pass", "改排后复查通过", reason=f"硬约束零违规{extra}")

    # 该天导览词刷新（离线模板，确定性）
    narrate(plan, bus, mode="offline")
    bus.emit("revise", "done", f"第{day_no}天修订完成",
             reason=f"{len(ordered)} 个点 · 负载 {d['load']['hours']}h · 强度 {d['load']['intensity']}")

    msg = f"已调整第{day_no}天：{before_n} → {len(ordered)} 个点，负载 {d['load']['hours']}h"
    return {"itinerary": plan, "timeline": bus.timeline(), "revised_day": day_no, "message": msg}
