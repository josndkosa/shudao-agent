"""事件契约校验（03K 任务A）：event.schema.json 的纯标准库实现。

为什么不用 jsonschema 库：校验要进 CI 链，主依赖按 requirements.txt 锁死五包，
不为一段 50 行的校验引入新依赖。规则范围 = 字段存在性 + 枚举成员 + 类型 +
下界/非空——足够拦住「事件发错形状」这一类事故（P0 复核轮的教训：消费端
读错层级，路线从未渲染过；契约把形状钉死后，发错形状在测试期就红）。

事件总线 events.py 与本文件零耦合：契约只读 schema 文件，不反向修改事件实现。
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "event.schema.json"

# JSON Schema 类型子集 → Python 判定（bool 是 int 的子类，须显式排除）
_TYPES = {
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "object": lambda v: isinstance(v, dict),
}


def load_schema() -> dict:
    """加载事件契约（version 1.0.0）。schema 文件是契约的唯一真相源。"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_event(ev, schema: dict | None = None) -> list[str]:
    """校验单条事件，返回错误列表（空列表 = 通过）。不抛异常——由调用方决定失败策略。"""
    sc = schema or load_schema()
    if not isinstance(ev, dict):
        return [f"事件必须是对象，实际是 {type(ev).__name__}"]
    errors: list[str] = []
    for key in sc["required"]:
        if key not in ev:
            errors.append(f"缺少必填字段 {key}")
    for key, spec in sc["properties"].items():
        if key not in ev:
            continue          # 非必填字段（如 t）缺失不算错
        v = ev[key]
        if not _TYPES[spec["type"]](v):
            errors.append(f"字段 {key} 类型错误：期望 {spec['type']}，实际 {type(v).__name__}")
            continue
        if "enum" in spec and v not in spec["enum"]:
            errors.append(f"字段 {key} 取值 {v!r} 不在枚举 {spec['enum']}")
        if "minimum" in spec and v < spec["minimum"]:
            errors.append(f"字段 {key}={v} 低于下界 {spec['minimum']}")
        if "minLength" in spec and len(v) < spec["minLength"]:
            errors.append(f"字段 {key} 不能为空（minLength={spec['minLength']}）")
    return errors
