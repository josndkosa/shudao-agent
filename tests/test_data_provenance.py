"""数据溯源旁挂（03K 任务D）：provenance.json 与 15 个数据文件零耦合。

原则（任务单口径）：
  - 只有逐条核对过出处的点才登记进 provenance.json——**不出现 = 未核对**，
    比给 237 条批量写「人工整理」更干净；
  - 数据文件（chengdu.json 等 15 个）一行不改——为一个 5 行的抽查
    造 232 行 diff 不值得；
  - 不许编：source 必须可追溯（官方渠道名/现场核对的说明），日期必须真实。
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.tools.poi_search import load_pois

PROV_PATH = Path(__file__).resolve().parent.parent / "server" / "data" / "provenance.json"


def _load():
    return json.loads(PROV_PATH.read_text(encoding="utf-8"))


def test_provenance_ids_exist_in_poi_table():
    """防手抖锁：provenance 里每个 id 都真实存在于 POI 表（写错 id = 白领核对功劳）。"""
    known = {p["id"] for p in load_pois()}
    for pid, _ in _load()["pois"].items():
        assert pid in known, f"provenance.json 的 id {pid} 不存在于数据层（手抖写错？）"


def test_provenance_entries_have_source_and_valid_date():
    """每条：source 非空、verified_at 是合法 ISO 日期。宁可空缺也不写追溯不了的措辞。"""
    for pid, rec in _load()["pois"].items():
        assert isinstance(rec.get("source"), str) and rec["source"].strip(), \
            f"{pid} 的 source 为空——没有出处就不要登记"
        try:
            date.fromisoformat(rec["verified_at"])
        except (ValueError, TypeError):
            raise AssertionError(f"{pid} 的 verified_at 不是合法日期：{rec.get('verified_at')!r}")
