"""weather 工具：本地快照 + 华为云 FunctionGraph 可选数据源。

数据源选择（FG 调用已独立成层 server/cloud/functiongraph.py，任务 E）：
- 环境变量 FG_WEATHER_URL 存在 → cloud.functiongraph.fg_weather()（2s 超时），返回带 source=functiongraph
- 未配置 / 超时 / 失败 → 静默回落本地快照（source=local-snapshot），绝不打断管线
接口形态与 scripts/export_demo_assets.py 的本地口径完全一致，前端无感。
"""
from ..cloud.functiongraph import fg_weather

NOVEMBER = {
    "成都": {"day": "多云", "night": "阴", "temp": [10, 17], "rain_prob": 0.35,
             "advice": "早晚微凉备薄外套，偶有小雨备伞"},
    "重庆": {"day": "阴转多云", "night": "多云", "temp": [12, 19], "rain_prob": 0.4,
             "advice": "江边风大，观景台看夜景建议加件外套"},
}


def weather(city, day_offset=0):
    fg = fg_weather(city)
    if fg is not None:
        w = {
            "day": fg.get("day", "多云"), "night": fg.get("night", "阴"),
            "temp": fg.get("temp", [10, 18]), "rain_prob": fg.get("rain_prob", 0.3),
            "advice": fg.get("advice", "出行关注天气"),
            "city": city, "day_offset": day_offset, "source": "functiongraph",
        }
        return w
    base = NOVEMBER.get(city, {"day": "多云", "night": "阴", "temp": [10, 18],
                              "rain_prob": 0.3, "advice": "出行关注天气"})
    w = dict(base)
    w["city"] = city
    w["day_offset"] = day_offset
    w["source"] = "local-snapshot"
    return w
