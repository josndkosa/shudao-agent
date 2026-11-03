"""事件契约协议化（03K 任务A）：event.schema.json + 标准库校验的三条锁。

  1. 真跑一次管线，所有事件通过校验——契约描述的是实际产出，不是想象的形状
  2. 造一条 type 非法的事件，校验必须报错——证明校验不是恒真（只写 return True
     的校验器是虚假安全感，和当年冒烟脚本手工造 revealed 一个性质）
  3. 缺必填字段同样报错——字段存在性是契约的一部分
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from server.agent import TripRequest, run_pipeline
from server.agent.event_contract import load_schema, validate_event
from server.agent.events import EventBus


def _run_default_events():
    """离线默认场景真跑管线（conftest 已强制 offline + 画像隔离，确定性输出）。"""
    bus = EventBus()
    run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"],
                             cities=["成都", "重庆"]), bus)
    return [e.to_dict() for e in bus.events]


def test_all_pipeline_events_conform_to_schema():
    events = _run_default_events()
    assert len(events) >= 20, f"默认场景事件数异常少（管线可能没跑全）：{len(events)}"
    schema = load_schema()
    bad = [(ev.get("seq"), validate_event(ev, schema)) for ev in events]
    bad = [b for b in bad if b[1]]
    assert not bad, f"违反事件契约的事件：{bad[:3]}"


def test_schema_declares_version_and_enums():
    sc = load_schema()
    assert sc["version"] == "1.0.0", "契约必须带版本号（协议化的前提）"
    assert set(sc["properties"]["type"]["enum"]) == {
        "start", "thought", "tool_call", "tool_result", "decision",
        "violation", "fix", "pass", "advisory", "unfixable", "fallback", "done"}
    assert sc["properties"]["stage"]["enum"] == [
        "plan", "validate", "narrate", "revise", "system"]
    assert "t" not in sc["required"], "t 是可选字段（SSE/timeline 序列化帧不含它）"


def test_invalid_type_is_rejected():
    ev = {"seq": 1, "t": 0.001, "type": "explosion", "stage": "plan",
          "title": "非法类型探针", "reason": "", "detail": {}}
    errors = validate_event(ev)
    assert any("type" in e and "枚举" in e for e in errors), \
        f"type 非法必须报错（校验不是恒真）：{errors}"


def test_missing_required_field_is_rejected():
    ev = {"type": "start", "stage": "plan", "title": "缺 seq 探针", "reason": "", "detail": {}}
    errors = validate_event(ev)
    assert any("seq" in e for e in errors), f"缺必填字段必须报错：{errors}"
