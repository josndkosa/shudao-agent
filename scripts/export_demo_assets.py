"""export_demo_assets.py：一次性导出前端静态演示数据。

产物（全部为修复后代码的真实运行结果，不手写任何字段）：
  static/demo.json          cli.py --days 3 --budget 3000 --tags 美食,文化 --cities 成都,重庆 --json
                            （多城化后显式锁成渝——默认演示数据最扎实，城市多选是运行时能力）
  static/demo-revised.json  cli.py --days 3 --budget 1200 --tags 美食 --cities 成都,重庆 --json（"改行程后"数据）
  static/demo-geo.json      全量城市分城投影（含 _city_meta 图幅注记行；前端按行程城市动态渲染图幅）

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
from server.tools.poi_search import _load_meta, load_pois


def run_cli(days, budget, tags):
    """真实调用 CLI 产出 JSON（与 `python cli.py --json` 同构；演示资产锁定成渝双城）。"""
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "cli.py",
         "--days", str(days), "--budget", str(budget), "--tags", tags,
         "--cities", "成都,重庆", "--json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if r.returncode != 0:
        raise RuntimeError(f"CLI 失败：{r.stderr[:300]}")
    return json.loads(r.stdout)


def export_geo():
    """按城分别投影：城际距离远，合投影会挤成一团，各城各建 Projector。

    多城化（03E）：导出全部有快照的城市 + 每城图幅注记行（_city_meta），
    前端 CityMaps.setCities 按行程涉及城市动态渲染图幅卡。
    """
    meta = _load_meta()
    lines = {c: v["line"] for c, v in meta["city_info"].items()}
    out = {}
    for c in meta["cities"]:
        pois = [p for p in load_pois() if p["city"] == c]
        if not pois:
            continue
        pr = Projector(pois)
        out[c] = [
            {**{k: p[k] for k in ("id", "name", "city", "lat", "lng", "tags", "ticket",
                                  "open_hour", "slope", "crowd_level", "family", "must_see",
                                  "night_friendly", "summary")},
             **dict(zip(("x", "y"), pr.project(p["lat"], p["lng"])))}
            for p in pois
        ]
    return {"_city_meta": lines, **out}


def dump(path, data):
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return len(raw), hashlib.sha256(raw).hexdigest()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
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
