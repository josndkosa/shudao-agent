"""事件流：可倒带时间轴的数据源。

每个事件带 stage / type / reason —— 前端倒带时回答「为什么第二天排这三个点」。
W2 的 SSE 直接序列化 emit 出的事件序列。
"""
from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass, field, asdict

_t0 = time.time()   # 进程级时间基准：跨实例共享，保证 t 单调不减


@dataclass
class Event:
    stage: str            # plan / validate / narrate / system
    type: str             # start / thought / tool_call / tool_result / decision / violation / fix / pass / done / fallback
    title: str
    reason: str = ""      # 决策依据，倒带回放的核心字段
    detail: dict = field(default_factory=dict)

    def __post_init__(self):
        self.t = round(time.time() - _t0, 3)

    def to_dict(self):
        d = asdict(self)
        d["seq"] = getattr(self, "seq", None)   # seq 是 emit 时动态赋值，asdict 抓不到
        return d


class EventBus:
    def __init__(self, on_emit=None):
        self.events: list[Event] = []
        self._seq = itertools.count(1)   # 实例级序号：每次实例化从 1 重新计数
        self.on_emit = on_emit           # 可选事件回调（SSE 推流用）；不改 emit 签名语义

    def emit(self, stage, type_, title, reason="", **detail):
        e = Event(stage=stage, type=type_, title=title, reason=reason, detail=detail)
        e.seq = next(self._seq)
        self.events.append(e)
        if self.on_emit is not None:
            try:
                self.on_emit(e.to_dict())   # 回调异常不毁管线（推流失败不影响规划）
            except Exception:
                pass
        return e

    def to_json(self):
        return json.dumps([e.to_dict() for e in self.events], ensure_ascii=False, indent=2)

    def timeline(self):
        """按阶段分组的事件时间线（CLI 与前端通用）。"""
        return [
            {
                "seq": e.seq,
                "stage": e.stage,
                "type": e.type,
                "title": e.title,
                "reason": e.reason,
                "detail": e.detail,
            }
            for e in self.events
        ]


def reset_bus():
    """重置进程时间基准。seq 已随 EventBus 实例化重置，无需全局处理。"""
    global _t0
    _t0 = time.time()