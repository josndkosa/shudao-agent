"""export_demo_assets.py：一次性导出前端静态演示数据。

产物（全部为修复后代码的真实运行结果，不手写任何字段）：
  static/demo.json          cli.py --days 3 --budget 3000 --tags 美食,文化 --json
  static/demo-revised.json  cli.py --days 3 --budget 1200 --tags 美食 --json（"改行程后"数据）
  static/demo-geo.json      读 pois.json，按城各建一个 Projector 投影（口径唯一，前端不重算）

用法：python scripts/export_demo_assets.py [--out static]
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.tools.geo import Projector
from server.tools.poi_search import load_pois


def run_cli(days, budget, tags):
    """真实调用 CLI 产出 JSON（与 `python cli.py --json` 同构）。"""
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "cli.py",
         "--days", str(days), "--budget", str(budget), "--tags", tags, "--json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if r.returncode != 0:
        raise RuntimeError(f"CLI 失败：{r.stderr[:300]}")
    return json.loads(r.stdout)


def export_geo():
    """按城分别投影：成渝直线距离远，合投影会挤成一团，各城各建 Projector。"""
    out = {}
    for city in ("成都", "重庆"):
        pois = [p for p in load_pois() if p["city"] == city]
        pr = Projector(pois)
        out[city] = [
            {**{k: p[k] for k in ("id", "name", "city", "lat", "lng", "tags", "ticket",
                                  "open_hour", "slope", "crowd_level", "family", "must_see",
                                  "night_friendly", "summary")},
             **dict(zip(("x", "y"), pr.project(p["lat"], p["lng"])))}
            for p in pois
        ]
    return out


def dump(path, data):
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return len(raw), hashlib.sha256(raw).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="static")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    print("正在真实运行管线导出演示资产（离线模式）...")
    assets = {
        "demo.json": run_cli(3, 3000, "美食,文化"),
        "demo-revised.json": run_cli(3, 1200, "美食"),
        "demo-geo.json": export_geo(),
    }
    for name, data in assets.items():
        size, sha = dump(out / name, data)
        print(f"  {out / name}  {size} bytes  sha256:{sha}")
    print("完成。")


if __name__ == "__main__":
    main()
