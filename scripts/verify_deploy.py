"""verify_deploy.py — 公网部署验证（03M 任务C）：地址一到就用，五件事红绿表。

用法：
  python scripts/verify_deploy.py http://<公网IP>:8000

依次打五件事，每件打印：状态码 / 耗时 / 一个关键字段：
  1. GET  /api/health → mode（offline 或 online，如实显示——部署机无 key 就是 offline）
  2. GET  /api/meta   → 城市数、POI 总数（应为 15 城 237 点）
  3. GET  /api/geo    → 点数
  4. GET  /plan.html  → 200
  5. POST /api/plan   → 行程天数、事件条数

只读，不写任何缓存、不改服务端状态（POST /api/plan 只读语义：生成即弃，
不上 revise、不触发 OBS）。超时 5 秒；失败时给三条最可能原因（按顺序）。
退出码：全过 0，任一失败 1。输出为纯文本（无颜色转义、列宽对齐）——直接截图存档。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 5
FAIL_HINTS = (
    "  可能原因（按顺序排查）：",
    "  1. 安全组没放行 8000 端口（ECS 控制台 → 安全组 → 入方向规则）",
    "  2. 起的是多 worker（--workers N）——计划缓存各持一份，/api/revise 会 404，须单 worker",
    "  3. 依赖没装全（干净 venv: pip install -r requirements.txt，pytest 收尾全绿即完整）",
)


def _hit(base: str, path: str, payload: dict | None = None) -> tuple[int, float, dict | str]:
    """打一发：返回 (状态码, 耗时秒, body)。异常时状态码给 0，body 给异常名。"""
    url = base.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, time.perf_counter() - t0, body
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:
        return 0, time.perf_counter() - t0, f"{type(e).__name__}: {e}"


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].startswith("http"):
        print(__doc__)
        print("示例：python scripts/verify_deploy.py http://124.xx.xx.xx:8000")
        return 2
    base = sys.argv[1].rstrip("/")

    results: list[tuple[str, bool, str]] = []

    code, dt, body = _hit(base, "/api/health")
    mode = json.loads(body).get("mode", "?") if code == 200 else "-"
    results.append(("health", code == 200, f"{code} · {dt:.2f}s · mode={mode}"
                    + ("" if code == 200 else f" · {body[:80]}")))

    code, dt, body = _hit(base, "/api/meta")
    ok = code == 200
    detail = f"{code} · {dt:.2f}s"
    if ok:
        j = json.loads(body)
        n_cities, n_pois = len(j.get("cities", [])), j.get("meta", {}).get("count", "?")
        detail += f" · {n_cities} 城 {n_pois} 点（应为 15 城 237 点）"
        ok = n_cities == 15 and str(n_pois) == "237"
    else:
        detail += f" · {body[:80]}"
    results.append(("meta", ok, detail))

    code, dt, body = _hit(base, "/api/geo")
    ok = code == 200
    detail = f"{code} · {dt:.2f}s"
    if ok:
        j = json.loads(body)
        n = sum(len(v) for v in j.get("points", {}).values())
        detail += f" · {n} 点"
        ok = n == 237
    else:
        detail += f" · {body[:80]}"
    results.append(("geo", ok, detail))

    code, dt, body = _hit(base, "/plan.html")
    results.append(("plan.html", code == 200, f"{code} · {dt:.2f}s · {len(body)} bytes"))

    code, dt, body = _hit(base, "/api/plan", {"days": 3, "budget": 3000, "tags": ["美食", "文化"]})
    ok = code == 200
    detail = f"{code} · {dt:.2f}s"
    if ok:
        j = json.loads(body)
        days, evs = len(j.get("itinerary", {}).get("days", [])), len(j.get("timeline", []))
        detail += f" · {days} 天行程 · {evs} 条事件"
        ok = days >= 1 and evs >= 1
    else:
        detail += f" · {body[:80]}"
    results.append(("plan", ok, detail))

    print(f"========== 公网部署验证 · {base} ==========")
    for name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name:<9s} {detail}")
    print("--------------------------------------------")
    if all(ok for _, ok, _ in results):
        print("结论：五项全过。")
        print("建议存档：codearts_proof/06-一键安装与部署验证/04-公网部署-health与meta实测.png")
        return 0
    print("结论：存在失败项——")
    print("\n".join(FAIL_HINTS))
    return 1


if __name__ == "__main__":
    sys.exit(main())