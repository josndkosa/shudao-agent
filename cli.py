"""蜀道智行 CLI：三段式管线命令行入口（答辩演示的保命形态）。

用法：
  python cli.py --days 3 --budget 3000 --tags 美食,文化 --family
  python cli.py --days 2 --budget 2000 --tags 亲子 --json
  SD_LLM_MODE=offline python cli.py --days 3   # 强制离线
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus

STAGE_COLOR = {"plan": "\033[36m", "validate": "\033[33m", "narrate": "\033[35m", "system": "\033[32m"}
TYPE_MARK = {
    "start": "▶", "thought": "◌", "tool_call": "⚙", "tool_result": "✓",
    "decision": "◆", "violation": "✗", "fix": "↻", "pass": "✔",
    "done": "■", "fallback": "▽", "advisory": "⚠", "unfixable": "⊘",
}
RESET = "\033[0m"
DIM = "\033[2m"


def _c(s, code):
    return f"{code}{s}{RESET}"


def print_timeline(timeline):
    print(_c("── Agent 执行事件流（前端可倒带时间轴的数据源）──", DIM))
    for e in timeline:
        color = STAGE_COLOR.get(e["stage"], "")
        mark = TYPE_MARK.get(e["type"], "·")
        line = f" #{e['seq']:03d} {color}[{e['stage']:8s}]{RESET} {mark} {e['title']}"
        print(line)
        if e["reason"]:
            print(f"      {_c('└ 因为 ' + e['reason'], DIM)}")
    print()


def print_itinerary(itinerary, mode):
    b = itinerary.get("budget", {})
    print(_c(f"════════ 行程单（模式：{mode}）════════", "\033[1m"))
    for d in itinerary.get("days", []):
        wx = d.get("weather", {})
        print(_c(f"\nDay {d['day']} · {d['city']}", "\033[1m\033[36m") + _c(
            f"  {wx.get('day', '')} {wx.get('temp', [''])[0]}~{wx.get('temp', [''])[1]}℃", DIM))
        for it in d["items"]:
            if it["type"] == "meal":
                print(f"   {it['arrival']} ── {it['label']} ──")
            elif it["type"] == "intercity":
                print(f"   {it['arrival']} ── {it['label']} → {it['departure']} ──")
            else:
                price = f" ¥{it['ticket']}" if it.get("ticket") else ""
                print(f"   {it['arrival']} ─ {it['name']}{price}（{it['visit_hours']}h，车乘 {it['leg_hours']}h）")
                if it.get("reasons"):
                    print(f"        {_c('入选理由：' + '；'.join(it['reasons']), DIM)}")
        load = d.get("load", {})
        print(_c(f"   本日负载：{load.get('hours', '?')}h · 强度 {load.get('intensity', '?')}"
                 f" · 门票 ¥{load.get('tickets', 0)}", DIM))
        if d.get("narrative"):
            print(f"   {d['narrative']}")
    if b:
        print(_c(f"\n预算核算：门票 ¥{b['tickets']} + 餐饮 ¥{b['meals']} + 交通 ¥{b['transit']}"
                 f" = ¥{b['total']}（日均 ¥{b['per_day']}）", "\033[1m"))


def main():
    ap = argparse.ArgumentParser(description="蜀道智行·三段式行程规划管线 CLI")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--budget", type=int, default=3000)
    ap.add_argument("--tags", default="", help="偏好标签，逗号分隔，如 美食,亲子,夜景")
    ap.add_argument("--family", action="store_true", help="亲子模式")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供前端/W2 SSE 联调）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    req = TripRequest(days=args.days, budget=args.budget,
                      tags=[t for t in args.tags.split(",") if t.strip()],
                      family=args.family)
    result = run_pipeline(req, EventBus())

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print_timeline(result["timeline"])
    print_itinerary(result["itinerary"], result["mode"])


if __name__ == "__main__":
    main()
