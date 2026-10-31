"""三段式管线：规划 → 校验 → 叙事。

- 规划段：LLM FC（在线）或贪心装箱（离线兜底）
- 校验段：纯规则引擎，独立可测，违规回流规划段修复（最多 3 轮）
- 叙事段：LLM 文案（在线）或模板（兜底）
全程事件流 EventBus 输出，前端据此渲染可倒带时间轴。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import llm as llm_mod
from . import narrator, planner, validator
from .events import EventBus


@dataclass
class TripRequest:
    days: int = 3
    budget: int = 3000
    tags: list[str] = field(default_factory=list)
    family: bool = False
    cities: list[str] = field(default_factory=list)   # 空 = 按候选池总分自动选城


def _load_dotenv():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def run_pipeline(request: TripRequest, bus: EventBus | None = None, on_event=None):
    """on_event：可选事件回调（SSE 推流），在 EventBus.emit 内部触发；
    不改 emit 签名语义，cli.py 与现有测试传 bus 的用法完全不受影响。"""
    _load_dotenv()
    if bus is None:
        bus = EventBus(on_emit=on_event)
    elif on_event is not None and bus.on_emit is None:
        bus.on_emit = on_event
    mode = llm_mod.resolve_mode()
    bus.emit("system", "start", "蜀道智行·三段式管线启动",
             reason=f"LLM 模式 {mode}（auto/offline/online 可切换，离线为断网演示保底）", mode=mode)

    # ── 规划段 ──
    bus.emit("plan", "start", "规划段开始", reason="偏好打分→城市分天→逐日装箱→时间线推算")
    if mode == "online":
        plan = planner.llm_plan(request, bus)
    else:
        plan = planner.offline_plan(request, bus)

    # ── 校验段（软硬分流 + 收敛检测）──
    bus.emit("validate", "start", "校验段开始",
             reason="纯规则引擎：V1时长/V2开放窗口/V4预算/V5亲子为硬约束，V3强度为软提醒")
    prev_hard_sig = None
    for rnd in range(1, 4):
        try:
            violations = validator.validate(plan, request)
        except Exception as e:
            # 校验异常不中断管线：发事件如实标注，继续叙事段（宁可标注也不白屏）
            bus.emit("validate", "fallback", "校验段异常，跳过本轮校验",
                     reason=f"{type(e).__name__}: {e}")
            break
        hard = [v for v in violations if v.get("severity", "hard") == "hard"]
        soft = [v for v in violations if v.get("severity") == "soft"]
        hard_sig = {(v["rule"], v["day"], v.get("poi")) for v in hard}
        if prev_hard_sig is not None and hard_sig == prev_hard_sig:
            # 收敛检测：fix 后 hard 违规集合未变 → 无可用自动修复策略，立即停止重试
            for v in soft:
                bus.emit("validate", "advisory", f"[{v['rule']}] 第{v['day']}天",
                         reason=f"{v['detail']}；强度是软约束，自动删点会误伤必游地标，故保留行程并提示", detail=v)
            bus.emit("validate", "unfixable", "存在无自动修复策略的硬违规",
                     reason="该违规无可用自动修复策略，修复后状态未变，已停止重试")
            break
        if not hard:
            for v in soft:
                bus.emit("validate", "advisory", f"[{v['rule']}] 第{v['day']}天",
                         reason=f"{v['detail']}；强度是软约束，自动删点会误伤必游地标，故保留行程并提示", detail=v)
            extra = f"；另有 {len(soft)} 条软提醒（已如实标注）" if soft else ""
            bus.emit("validate", "pass", f"第{rnd}轮校验通过", reason=f"硬约束零违规{extra}")
            break
        for v in hard:
            bus.emit("validate", "violation", f"[{v['rule']}] 第{v['day']}天",
                     reason=v["detail"], detail=v)
        if rnd == 3:
            for v in soft:
                bus.emit("validate", "advisory", f"[{v['rule']}] 第{v['day']}天",
                         reason=f"{v['detail']}；强度是软约束，自动删点会误伤必游地标，故保留行程并提示", detail=v)
            bus.emit("validate", "done", "校验结束（仍残留违规，如实标注）",
                     reason="修复上限 3 轮，残留项将在前端高亮提示")
            break
        bus.emit("plan", "fix", f"第{rnd}轮修复回流规划段", reason="定向修复硬违规点位后重排时间线")
        plan = planner.fix(plan, hard, request, bus)
        prev_hard_sig = hard_sig

    # ── 叙事段 ──
    bus.emit("narrate", "start", "叙事段开始", reason="每日导览词生成")
    plan = narrator.narrate(plan, bus, mode="online" if mode == "online" else "offline")
    bus.emit("system", "done", "管线完成",
             reason=f"共 {len(plan.get('days', []))} 天行程，预估花费 {plan.get('budget', {}).get('total', '?')} 元")

    return {"itinerary": plan, "timeline": bus.timeline(), "mode": mode, "budget": plan.get("budget")}
