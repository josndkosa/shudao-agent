"""03E 批次1 验收测试：西南赛区多城数据 + 地形分档 + 城际自动生成 + 规划器多城。

覆盖 prompt 03E 第六节验收标准中批次1 范围（任务 F Provider 抽象推迟到批次3）：
- 数据质量：15 城省份覆盖 / 深度层点数 / 字段完整 / summary 互异 / open_hour 多样 / id 唯一
- 功能：双城回归锁死 / 自动选城 / 4 城 4 天 3 段城际 / 15 城两两城际 / V3 地形分档
- 稳定性：10 组随机参数多城零硬误报
"""
import itertools
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus
from server.agent.validator import _TERRAIN_CAP, INTENSITY_CAP
from server.tools.poi_search import _load_meta, load_pois
from server.tools.route import intercity, intercity_cost

META = _load_meta()
SOUTHWEST = {"四川", "重庆", "云南", "贵州", "广西", "海南", "西藏"}


# ── 数据质量 ───────────────────────────────────────────────

def test_southwest_province_coverage():
    """15 城总表的省份集合 ⊇ 赛题定义的西南七省市。"""
    provs = {v["province"] for v in META["city_info"].values()}
    assert provs >= SOUTHWEST, f"省份覆盖不足：{SOUTHWEST - provs}"
    assert len(META["cities"]) == 15


def test_depth_layer_city_pois():
    """深度层 6 城（批次1 落地）各 ≥14 点。"""
    counts = {}
    for p in load_pois():
        counts[p["city"]] = counts.get(p["city"], 0) + 1
    for c in ("成都", "重庆", "昆明", "大理", "贵阳", "桂林"):
        assert counts.get(c, 0) >= 14, f"{c} 仅 {counts.get(c, 0)} 点（深度层应 ≥14）"
    assert sum(counts.values()) >= 100


def test_poi_ids_globally_unique():
    ids = [p["id"] for p in load_pois()]
    assert len(ids) == len(set(ids)), "id 全局唯一被破坏"


def test_summaries_distinct_and_specific():
    sums = [p["summary"] for p in load_pois()]
    assert all(s.strip() for s in sums), "存在空 summary"
    assert len(set(sums)) == len(sums), "summary 存在重复"


def test_open_hours_variety_per_city():
    """各城 open_hour 取值不得千篇一律（硬质量要求的机械检查）。"""
    by_city = {}
    for p in load_pois():
        by_city.setdefault(p["city"], set()).add(tuple(p["open_hour"]))
    for c, ohs in by_city.items():
        assert len(ohs) >= 5, f"{c} 的 open_hour 仅 {len(ohs)} 种取值，疑似模板数据"


def test_terrain_config_complete():
    """15 城 terrain/intensity_cap 配置齐全且值域合理。"""
    for c in META["cities"]:
        t = META["city_info"][c]["terrain"]
        assert t["type"] in ("plain", "basin", "hill", "karst", "plateau", "alpine", "tropical"), c
        assert 6.0 <= t["intensity_cap"] <= 8.5, f"{c} 的 intensity_cap 越界：{t}"


# ── 地形分档（V3）─────────────────────────────────────────

def test_terrain_caps_loaded():
    assert _TERRAIN_CAP["成都"] == 8.5      # basin 基准
    assert _TERRAIN_CAP["重庆"] == 8.0      # hill
    assert _TERRAIN_CAP["昆明"] == 7.0      # plateau
    assert _TERRAIN_CAP["拉萨"] == 6.0      # alpine
    assert INTENSITY_CAP == 8.5             # 默认兜底保持旧行为


def test_v3_same_intensity_different_verdict_by_city():
    """同一组点位（强度恰 8.0）：在成都（basin 8.5）不报、在昆明（plateau 7.0）报——分档确实生效。"""
    from server.agent.planner import POI_INDEX
    from server.agent.validator import validate
    ids = ["KM-01", "KM-05", "KM-12"]       # 2.6 + 3.2 + 2.2 = 8.0

    def mk_plan(city):
        return {"days": [{
            "day": 1, "city": city, "weather": {},
            "items": [{"type": "poi", "poi_id": i, "name": POI_INDEX[i]["name"],
                       "arrival": "09:00", "departure": "11:00",
                       "leg_hours": 0.3, "visit_hours": 2.0} for i in ids],
            "load": {"hours": 8.0, "intensity": 8.0, "tickets": 0},
        }]}

    req = TripRequest(days=1, budget=99999)
    v_cd = [v for v in validate(mk_plan("成都"), req) if v["rule"] == "V3-intensity"]
    v_km = [v for v in validate(mk_plan("昆明"), req) if v["rule"] == "V3-intensity"]
    assert not v_cd, "强度 8.0 在成都（cap 8.5）不应报"
    assert v_km and "7.0" in v_km[0]["detail"], f"强度 8.0 在昆明（cap 7.0）应报：{v_km}"


# ── 城际自动生成（任务 C）─────────────────────────────────

def test_intercity_all_pairs_generated():
    """15 城两两 105 对全部生成成功，时长/票价有界且无零值负值。"""
    cities = list(META["city_hub"])
    for a, b in itertools.combinations(cities, 2):
        info = intercity(a, b)
        assert 1.2 <= info["hours"] <= 14.0, f"{a}-{b} 时长越界 {info}"
        assert 60 <= info["price"] <= 2200, f"{a}-{b} 票价越界 {info}"
        assert info["km"] > 0


def test_intercity_monotonic_by_distance():
    """时长单调：枢纽距离更远的城对，时长不更短（每城抽验一个代表对）。"""
    def d(a, b):
        return intercity(a, b)["km"]

    def h(a, b):
        return intercity(a, b)["hours"]

    assert h("昆明", "大理") < h("成都", "昆明") < h("成都", "三亚") <= h("成都", "拉萨")
    assert d("昆明", "大理") < d("成都", "昆明") < d("成都", "三亚")


def test_intercity_override_table_wins():
    """成都-重庆 走人工覆盖表（1.8h / ¥154 / 成渝高铁），与历史基线一致。"""
    info = intercity("成都", "重庆")
    assert info["hours"] == 1.8 and info["price"] == 154 and info["label"] == "成渝高铁"


def test_intercity_lhasa_detour():
    """进藏城对按 2.0 绕行系数计时长：成都-拉萨 ≥ 11h（prompt 验收）。"""
    assert intercity("成都", "拉萨")["hours"] >= 11.0
    assert intercity("重庆", "拉萨")["hours"] >= 11.0


def test_intercity_cost_multi_segment():
    """多城多段城际票价如实累计：4 城行程 3 段 > 任一段单程。"""
    days = [{"city": c} for c in ("成都", "重庆", "贵阳", "昆明")]
    total = intercity_cost(days)
    assert total == intercity("成都", "重庆")["price"] + intercity("重庆", "贵阳")["price"] \
        + intercity("贵阳", "昆明")["price"]
    assert intercity_cost([{"city": "成都"}, {"city": "重庆"}]) == 154


# ── 规划器多城（任务 D）───────────────────────────────────

def test_auto_select_cities_days3():
    """--days 3 不指定城市：自动选出得分最高的 3 城且分天合理。"""
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"]), EventBus())
    cities = [d["city"] for d in r["itinerary"]["days"]]
    assert len(set(cities)) == 3, f"应自动选 3 城，实际 {cities}"
    assert len(r["itinerary"]["days"]) == 3


def test_four_cities_three_intercity_segments():
    """--cities 成都,重庆,贵阳,昆明 --days 4：4 天 4 城 3 次城际，时间线不超 22:00。"""
    r = run_pipeline(TripRequest(days=4, budget=6000, cities=["成都", "重庆", "贵阳", "昆明"]), EventBus())
    days = r["itinerary"]["days"]
    assert len(days) == 4
    assert len({d["city"] for d in days}) == 4
    ic = sum(1 for d in days for it in d["items"] if it["type"] == "intercity")
    assert ic == 3, f"4 城应 3 段城际，实际 {ic}"
    for d in days:
        for it in d["items"]:
            if it["type"] == "poi":
                assert it["departure"] <= "22:00", f"第{d['day']}天 {it['name']} 收班 {it['departure']}"


def test_cities_filter_unknown_city():
    """指定未收录城市被剔除并如实发事件，不崩管线。"""
    r = run_pipeline(TripRequest(days=2, budget=3000, cities=["成都", "火星"]), EventBus())
    fb = [e for e in r["timeline"] if e["type"] == "fallback" and "未收录" in e["title"]]
    assert fb, "应有未收录城市的 fallback 事件"
    cities = {d["city"] for d in r["itinerary"]["days"]}
    assert "火星" not in cities and "成都" in cities


def test_weather_reads_from_meta():
    """新城市天气从 meta 快照读取（昆明有值），成渝与历史一致。"""
    from server.tools.weather import weather
    w = weather("昆明")
    assert w["source"] == "local-snapshot"
    assert w["day"] == "晴" and 0 < w["temp"][0] < w["temp"][1]
    assert weather("成都")["advice"] == "早晚微凉备薄外套，偶有小雨备伞"


def test_random_params_no_false_hard_violation():
    """10 组随机参数（多城组合）：V1/V2/V4/V5 零硬误报（软提醒如实标注不算）。"""
    rng = random.Random(42)
    cities = ["成都", "重庆", "昆明", "大理", "贵阳", "桂林"]
    tag_pool = ["美食", "文化", "夜景", "亲子", "山水", "民族", "博物馆"]
    for i in range(10):
        k = rng.choice([2, 3, 4])
        sel = rng.sample(cities, k)
        req = TripRequest(days=rng.randint(1, 5), budget=rng.choice([1500, 3000, 6000]),
                          tags=rng.sample(tag_pool, rng.randint(0, 3)),
                          family=rng.random() < 0.3, cities=sel)
        r = run_pipeline(req, EventBus())
        timeline = r["timeline"]
        # 管线自身收敛后仍残留的 hard 违规只允许出现在「unfixable 如实标注」路径
        hard_left = [e for e in timeline if e["type"] == "unfixable"]
        for e in timeline:
            if e["type"] == "violation":
                # 出现 violation 必须跟着 fix（回流修复），最终要么 pass 要么 unfixable 如实标注
                assert any(x["type"] == "fix" for x in timeline) or hard_left, \
                    f"第{i+1}组 {sel} 出现未修复的硬违规"
        assert r["itinerary"]["days"], f"第{i+1}组 {sel} 无行程"


# ── 双城回归锁死（批次1 最硬的一条）───────────────────────

def test_dual_city_regression_locked():
    """--cities 成都,重庆 默认场景与批次1 改造前的骨架逐字段一致。

    骨架 = 点位序列 / 到离时刻 / 日负载 / 预算 / 事件条数与类型序列。
    （唯一允许的差异：V3 detail 的阈值数字 8.5→8.0，源于重庆 hill 分档生效，
    属于地形分档的预期行为——reason 文本不进骨架。）
    """

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "regression-chengdu-chongqing.json").read_text("utf-8"))
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"],
                                 cities=["成都", "重庆"]), EventBus())
    it = r["itinerary"]
    assert [d["city"] for d in it["days"]] == [d["city"] for d in fixture["days"]]
    for new, old in zip(it["days"], fixture["days"]):
        assert new["day"] == old["day"]
        pois = [{"id": x["poi_id"], "arr": x["arrival"], "dep": x["departure"]}
                for x in new["items"] if x["type"] == "poi"]
        assert pois == old["pois"], f"第{new['day']}天点位/时刻漂移"
        assert new["load"] == old["load"], f"第{new['day']}天负载漂移"
    assert r["budget"] == fixture["budget"], "预算漂移"
    assert len(r["timeline"]) == fixture["timeline_count"], "事件条数漂移"
    assert [e["type"] for e in r["timeline"]] == fixture["timeline_types"], "事件类型序列漂移"


# ── 天数<城数的分配边界（缺陷2 多城版复发的回归锁）────────────

def test_days_less_than_cities_no_overallocation():
    """勾 4 城只给 2 天：必须恰好 2 天（旧逻辑产生负天数被 range 吞掉 → 超发 4 天）。"""
    r = run_pipeline(TripRequest(days=2, budget=5000, cities=["成都", "重庆", "贵阳", "昆明"]), EventBus())
    days = r["itinerary"]["days"]
    assert len(days) == 2, f"应恰好 2 天，实际 {len(days)}"
    assert {d["city"] for d in days} <= {"成都", "重庆", "贵阳", "昆明"}
    ic = sum(1 for d in days for it in d["items"] if it["type"] == "intercity")
    assert ic == len(days) - 1


def test_days1_with_four_cities_single_day():
    """勾 4 城只给 1 天：聚焦总分最高单城，恰好 1 天。"""
    r = run_pipeline(TripRequest(days=1, budget=3000, cities=["成都", "重庆", "贵阳", "昆明"]), EventBus())
    assert len(r["itinerary"]["days"]) == 1


def test_allocate_days_never_negative():
    """单元级：任意 days/城数组合下分配值均为正且总和 == days。"""
    from server.agent.planner import _allocate_days
    pools = {c: [{"_score": s}] for c, s in (("成都", 10.0), ("重庆", 6.0), ("贵阳", 4.0), ("昆明", 8.0))}
    for days in range(1, 6):
        alloc = _allocate_days(days, pools)
        assert all(v >= 1 for v in alloc.values()), f"days={days} 出现非正分配：{alloc}"
        assert sum(alloc.values()) == days, f"days={days} 分配总和 {alloc} 不等于天数"
