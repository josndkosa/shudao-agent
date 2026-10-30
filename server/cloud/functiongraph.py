"""functiongraph.py — FunctionGraph 天气函数的 HTTP 调用层（华为云可选接入）。

启用条件：环境变量 FG_WEATHER_URL 存在。
降级行为：未配置 / 超时（2s）/ 返回异常 → 返回 None，调用方静默回落本地快照。
绝不拖慢或打断管线——这是「可选增强」的边界。
"""
import json
import os
import urllib.request

FG_URL_ENV = "FG_WEATHER_URL"
FG_TIMEOUT = 2.0


def fg_weather(city):
    """POST {city} 到 FG 函数，返回规范化天气 dict；失败/未配置返回 None（回落本地）。"""
    url = os.environ.get(FG_URL_ENV)
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"city": city}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=FG_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        if isinstance(data, dict) and "day" in data and "temp" in data:
            return data
        return None
    except Exception:
        return None
