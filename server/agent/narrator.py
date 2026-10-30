"""叙事段：为每日行程生成导游文案。LLM 在线 + 模板兜底。"""
from __future__ import annotations

import json

from .events import EventBus

NIGHT_TAGS = {"夜景", "夜生活"}


def _template_narrate(day, bus: EventBus):
    pois = [it for it in day["items"] if it["type"] == "poi"]
    if not pois:
        return ""
    names = "、".join(p["name"] for p in pois)
    wx = day["weather"]
    load = day["load"]
    picks = pois[:2]
    lines = [
        f"第{day['day']}天·{day['city']}：{names}。",
        f"天气{wx['day']}、{wx['temp'][0]}~{wx['temp'][1]}℃，{wx['advice']}。",
    ]
    for p in picks:
        lines.append(f"{p['name']}——{p['summary']}。")
    if load["intensity"] >= 6:
        lines.append("今日步行强度偏高，晚上回酒店泡个脚刚好。")
    # 文案与行程一致：只有真实落在夜间时段（arrival ≥ 18:00）的夜景点，才说夜景收尾
    def _arr_h(it):
        try:
            return int(it.get("arrival", "00:00").split(":")[0])
        except (ValueError, IndexError):
            return 0
    if any(NIGHT_TAGS & set(p.get("tags", [])) and _arr_h(p) >= 18 for p in pois):
        lines.append("行程以夜景收尾，记得提前给相机充满电。")
    return "".join(lines)


def narrate(plan, bus: EventBus, mode="offline"):
    for day in plan.get("days", []):
        if mode == "online":
            try:
                from . import llm as llm_mod
                system = "你是本地导游，为当日行程写一段 80 字内的中文导览词，语气亲切，点出亮点与提示。"
                payload = {
                    "day": day["day"], "city": day["city"],
                    "items": [{k: it.get(k) for k in ("name", "arrival", "departure", "summary")}
                              for it in day["items"] if it["type"] == "poi"],
                }
                msg, _ = llm_mod.chat([{"role": "system", "content": system},
                                       {"role": "user",
                                        "content": json.dumps(payload, ensure_ascii=False)}], tools=None)
                text = (msg.content or "").strip()
                if not text:
                    raise ValueError("LLM 返回空文案")
                day["narrative"] = text
                bus.emit("narrate", "done", f"第{day['day']}天文案生成", reason="LLM 在线生成")
                continue
            except Exception as e:
                bus.emit("narrate", "fallback", f"第{day['day']}天 LLM 文案降级模板",
                         reason=f"{type(e).__name__}: {e}")
        day["narrative"] = _template_narrate(day, bus)
        bus.emit("narrate", "done", f"第{day['day']}天文案生成", reason="模板兜底，串联快照 summary")
    return plan
