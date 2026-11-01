"""LLM 客户端：DeepSeek(OpenAI兼容) Function Calling + 离线兜底开关。

模式：
- auto   有 DEEPSEEK_API_KEY 走在线，否则离线
- online 强制在线（无 key 抛错）
- offline 强制离线（答辩现场网络不稳时的保命开关）
"""
from __future__ import annotations

import os

from ..tools.poi_search import _load_meta, load_pois

# 城市列表动态来自数据层（meta.json + POI 快照），与离线路径同源——
# 03E 多城化前这里硬编码 ["成都","重庆"]，在线 LLM 会以为只有两城可选
_META = _load_meta()
_ALL_CITIES = list(_META["cities"])                                   # 15 城总表（weather 全有快照）
_POI_CITIES = [c for c in _ALL_CITIES if c in {p["city"] for p in load_pois()}]   # 有 POI 快照的城市（poi_search 可用）

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "poi_search",
            "description": f"检索西南赛区城市的POI候选并按偏好打分。规划行程前必须先调用。"
                           f"当前有完整快照的城市：{'、'.join(_POI_CITIES)}。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "enum": _POI_CITIES},
                    "tags": {"type": "array", "items": {"type": "string"},
                            "description": "偏好标签：美食/亲子/文化/夜景/山水/民族等"},
                    "family": {"type": "boolean", "description": "是否亲子模式"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route",
            "description": "估算两点间交通耗时（市内）或城际列车。"
                           "from_id/to_id 必须来自 poi_search 返回的 id；返回小时数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_id": {"type": "string"},
                    "to_id": {"type": "string"},
                    "mode": {"type": "string", "enum": ["city", "walk", "intercity"]},
                },
                "required": ["from_id", "to_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "查询城市天气（本地快照，可切换华为云FunctionGraph数据源）。",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "enum": _ALL_CITIES}, "day_offset": {"type": "integer"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "budget",
            "description": "按天数与门票总额核算预算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer"},
                    "tickets_total": {"type": "number"},
                    "intercity_price": {"type": "number"},
                    "family": {"type": "boolean"},
                },
                "required": ["days", "tickets_total"],
            },
        },
    },
]


def resolve_mode():
    mode = os.environ.get("SD_LLM_MODE", "auto").lower()
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    if mode == "online":
        if not has_key:
            raise RuntimeError("SD_LLM_MODE=online 但未设置 DEEPSEEK_API_KEY")
        return "online"
    if mode == "offline":
        return "offline"
    return "online" if has_key else "offline"


def chat(messages, tools=None, temperature=0.3, json_mode=False):
    """在线 FC 对话：单次调用，多轮循环由调用方（planner）驱动。返回 (msg, kind)。

    json_mode 只用于无 tools 的纯 JSON 调用点——DeepSeek 文档标注 JSON 模式与
    function calling 不能同开，故 planner 的工具循环不传；若 API 拒绝
    response_format，去掉该参数重试一次而不是硬闯。
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        timeout=30.0,
        max_retries=2,
    )
    kwargs = dict(model="deepseek-chat", messages=messages, temperature=temperature)
    if tools:
        kwargs["tools"] = tools
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:
        if not json_mode:
            raise
        kwargs.pop("response_format", None)
        resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    if msg.tool_calls:
        return msg, "tool_call"
    return msg, "final"
