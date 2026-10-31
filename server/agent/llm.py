"""LLM 客户端：DeepSeek(OpenAI兼容) Function Calling + 离线兜底开关。

模式：
- auto   有 DEEPSEEK_API_KEY 走在线，否则离线
- online 强制在线（无 key 抛错）
- offline 强制离线（答辩现场网络不稳时的保命开关）
"""
from __future__ import annotations

import os

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "poi_search",
            "description": "检索成都/重庆的POI候选并按偏好打分。规划行程前必须先调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "enum": ["成都", "重庆"]},
                    "tags": {"type": "array", "items": {"type": "string"},
                            "description": "偏好标签：美食/亲子/文化/夜景"},
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
            "description": "估算两点间交通耗时（市内）或城际列车。",
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
                "properties": {"city": {"type": "string", "enum": ["成都", "重庆"]}, "day_offset": {"type": "integer"}},
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


def chat(messages, tools=None, temperature=0.3, max_tool_rounds=6):
    """在线 FC 对话。返回 (content, tool_calls, usage_note)。openai 延迟导入。"""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    kwargs = dict(model="deepseek-chat", messages=messages, temperature=temperature)
    if tools:
        kwargs["tools"] = tools
    for _ in range(max_tool_rounds):
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        if msg.tool_calls:
            return msg, "tool_call"
        return msg, "final"
    return resp.choices[0].message, "final"
