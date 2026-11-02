"""事件流与数据层契约回归锁（03H 任务 C/E/H3）。

每一锁都对应一次真实翻过车的事故，先红后绿：
  - 四集合一致：meta 承诺的城必须有数据/hub/可查（承诺与兑现同口径）
  - 零代码新增城市：load_city_pois 自动索引（开发指南承诺）
  - 新城市数据完整性：字段/坐标/开放时段与批次1/2 同标准
  - （后续任务 H3 的单跑锁/去重锁/丢天锁/餐数锁也写在本文件）
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from server.tools.poi_search import (
    _city_file_map,
    _load_meta,
    load_city_pois,
    load_pois,
)

NEW_CITIES = ["西江千户苗寨", "北海", "三亚", "拉萨"]   # 批次3 收口的 4 城


def test_four_layer_city_consistency():
    """四层口径一致：meta.city_info == 有数据文件的城 == CITY_HUB == load_city_pois 可查。

    meta 承诺 14 城但 poi_search 查不到 → LLM 工具 schema 让模型以为可选，
    一调就返回空 → 幻觉 POI 温床；CITY_HUB 缺城 → 城际走 3.0h 兜底 → 物理不可能的行程。
    """
    meta = _load_meta()
    info = set(meta["city_info"])
    hub = set(meta["city_hub"])
    files = set(_city_file_map())
    loadable = {c for c in files if load_city_pois(c)}
    assert info == hub, f"city_info 与 city_hub 不一致：{info ^ hub}"
    assert info == files, f"city_info 与数据文件不一致：{info ^ files}"
    assert info == loadable, f"数据文件存在但 load_city_pois 查不到：{files ^ loadable}"


def test_new_cities_data_integrity():
    """批次3 四城字段完整性：与批次1/2 同一把尺子（厚字段 + 坐标范围 + 开放时段合法）。"""
    ids = set()
    for city in NEW_CITIES:
        pois = load_city_pois(city)
        assert len(pois) >= 15, f"{city} 点位不足 15：{len(pois)}"
        for p in pois:
            assert p["id"] not in ids, f"id 重复：{p['id']}"
            ids.add(p["id"])
            for k in ("id", "name", "city", "lat", "lng", "tags", "ticket", "visit_hours",
                      "open_hour", "reserve", "crowd_peak", "crowd_level", "slope",
                      "family", "night_friendly", "must_see", "summary"):
                assert k in p, f"{p['id']} 缺字段 {k}"
            assert p["city"] == city, f"{p['id']} city 字段与所在文件城不符"
            assert 18 <= p["lat"] <= 34 and 85 <= p["lng"] <= 110, \
                f"{p['id']} 坐标超出西南赛区范围：{p['lat']}, {p['lng']}"
            o = p["open_hour"]
            assert 0 <= o[0] < o[1] <= 24, f"{p['id']} open_hour 非法：{o}"
            assert 0.5 <= p["visit_hours"] <= 6, f"{p['id']} visit_hours 越界"
    total = len(load_pois())
    assert total >= 230, f"15 城 POI 总数应 ≥230（11 城 176 + 新 4 城 ≥60）：{total}"


def test_load_city_pois_auto_index_new_city(tmp_path, monkeypatch):
    """零代码新增城市：丢一个含 city 字段的 json 进数据目录即可被收录（开发指南承诺）。"""
    import importlib

    # 包 __init__ 里 from .poi_search import poi_search（同名函数）覆盖了子模块属性，
    # import server.tools.poi_search as ps 拿到的是函数——必须走 importlib 取真模块
    ps = importlib.import_module("server.tools.poi_search")

    fake = tmp_path / "xx.json"
    fake.write_text(json.dumps([{
        "id": "XX-01", "name": "测试点", "city": "测试城", "lat": 30.0, "lng": 105.0,
        "tags": ["自然"], "ticket": 0, "visit_hours": 1.0, "open_hour": [8, 18],
        "reserve": 0, "crowd_peak": [10, 15], "crowd_level": 1, "slope": 0,
        "family": 3, "night_friendly": False, "must_see": False, "summary": "自动索引测试",
    }], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ps, "DATA_DIR", tmp_path)
    ps._city_file_map.cache_clear()
    ps.load_city_pois.cache_clear()
    try:
        assert load_city_pois("测试城")[0]["id"] == "XX-01", "自动索引未收录新城市"
        assert load_city_pois("不存在城") == [], "未收录城市应返回空"
    finally:
        ps._city_file_map.cache_clear()
        ps.load_city_pois.cache_clear()
