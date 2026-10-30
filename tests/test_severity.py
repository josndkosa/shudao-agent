"""软硬分级 + 收敛检测 + 口径统一 的回归测试（Prompt 01 续篇）。

先红后绿：覆盖
  A1 severity 字段（V3=soft，V1/V2/V4/V5=hard）
  A2 soft 不进修复循环（advisory 事件），pass 只看 hard
  A3 新事件类型 advisory / unfixable
  B  hard 修复无效 → unfixable 跳出，无重复违规事件
  C  规划器自算内容时长与 validator 口径一致（5 组参数 V1 零误报）
  D  轻度强度惩罚不摘光必游地标
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus
from server.agent.planner import (
    BUFFER,
    CITY_HUB,
    DAY_END,
    DAY_START,
    MEAL_HOURS,
    POI_INDEX,
    _order_day,
    _trim_to_capacity,
)
from server.agent.validator import validate


def _day(day_no, items, city="成都", tickets=0):
    return {"day": day_no, "city": city, "weather": {},
            "items": items, "load": {"hours": 9.0, "intensity": 5.0, "tickets": tickets}}


def _poi_item(pid, arrival, departure, leg=0.3):
    p = POI_INDEX[pid]
    return {"type": "poi", "poi_id": pid, "name": p["name"], "arrival": arrival,
            "departure": departure, "visit_hours": p["visit_hours"], "ticket": p["ticket"],
            "leg_hours": leg, "tags": p["tags"]}


# ─────────────────── A1：severity 字段 ───────────────────

def test_severity_field_hard_rules():
    """V1/V2/V4/V5 全部标 hard。"""
    items = [_poi_item("CD-06", "19:00", "22:30")]   # V2 开放窗口
    plan = {"days": [_day(1, items)]}
    vs = validate(plan, TripRequest(days=1, budget=50))  # 预算低 → V4
    rules = {v["rule"] for v in vs}
    assert {"V2-open-window", "V4-budget"} <= rules
    for v in vs:
        assert v.get("severity") == "hard", f"{v['rule']} 应为 hard：{v}"


def test_severity_field_v3_soft():
    """V3 强度标 soft。"""
    items = [_poi_item("CQ-07", "09:00", "10:30"), _poi_item("CQ-01", "11:00", "13:00"),
             _poi_item("CQ-11", "14:00", "15:00")]
    plan = {"days": [_day(1, items, city="重庆")]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    v3 = [v for v in vs if v["rule"] == "V3-intensity"]
    assert v3 and all(v.get("severity") == "soft" for v in v3), f"V3 应为 soft：{v3}"


def test_severity_field_v5_family_hard():
    items = [_poi_item("CD-22", "20:00", "21:30")]
    plan = {"days": [_day(1, items)]}
    vs = validate(plan, TripRequest(days=1, budget=99999, family=True))
    v5 = [v for v in vs if v["rule"] == "V5-family"]
    assert v5 and v5[0].get("severity") == "hard"


# ─────────────────── A2：soft 不进修复循环 ───────────────────

def test_soft_violation_skips_fix_loop(monkeypatch):
    """纯 soft 违规：无修复回流事件，出现 advisory + pass。"""
    from server.agent import pipeline as pl

    soft_v = [{"rule": "V3-intensity", "severity": "soft", "day": 1, "poi": "CD-06",
               "detail": "强度 12.2 超过 8.5", "fix_hint": "drop"}]
    monkeypatch.setattr(pl.validator, "validate", lambda plan, req: soft_v)
    r = run_pipeline(TripRequest(days=1, budget=99999), EventBus())
    types = [(e["stage"], e["type"]) for e in r["timeline"]]
    assert ("plan", "fix") not in types, "soft 违规不得触发修复回流"
    assert ("validate", "advisory") in types, "应有 advisory 事件"
    pass_ev = [e for e in r["timeline"] if e["type"] == "pass"]
    assert pass_ev and "硬约束零违规" in pass_ev[0]["reason"]
    assert "软提醒" in pass_ev[0]["reason"]


# ─────────────────── A3/B：收敛检测 ───────────────────

def test_hard_fix_progresses_then_pass(monkeypatch):
    """hard 修复有效：第 1 轮违规 → fix → 第 2 轮清空 → pass。"""
    from server.agent import pipeline as pl

    seq = [{"rule": "V1-duration", "severity": "hard", "day": 1, "poi": "CD-01",
            "detail": "内容时长 12.0h 超过容量 11.0h", "fix_hint": "drop"}]

    def fake_validate(plan, req):
        return [seq.pop(0)] if seq else []

    monkeypatch.setattr(pl.validator, "validate", fake_validate)
    monkeypatch.setattr(pl.planner, "fix", lambda plan, vs, req, bus: plan)
    r = run_pipeline(TripRequest(days=1, budget=99999), EventBus())
    types = [(e["stage"], e["type"]) for e in r["timeline"]]
    assert types.count(("plan", "fix")) == 1, "恰好一轮修复回流"
    assert ("validate", "violation") in types
    assert any(e["type"] == "pass" for e in r["timeline"])


def test_unfixable_breaks_without_duplicate(monkeypatch):
    """hard 修复无效：违规集合不变 → unfixable 跳出，同一条违规只出现一次。"""
    from server.agent import pipeline as pl

    hard_v = [{"rule": "V1-duration", "severity": "hard", "day": 1, "poi": None,
               "detail": "内容时长 12.0h 超过容量 11.0h", "fix_hint": "drop"}]
    monkeypatch.setattr(pl.validator, "validate", lambda plan, req: list(hard_v))
    monkeypatch.setattr(pl.planner, "fix", lambda plan, vs, req, bus: plan)  # no-op 修复
    r = run_pipeline(TripRequest(days=1, budget=99999), EventBus())
    types = [(e["stage"], e["type"]) for e in r["timeline"]]
    assert types.count(("validate", "violation")) == 1, "违规事件不得重复"
    assert ("validate", "unfixable") in types, "应发 unfixable 事件"
    unf = [e for e in r["timeline"] if e["type"] == "unfixable"][0]
    assert "未变" in unf["reason"] or "停止" in unf["reason"]


def test_default_scenario_no_duplicate_violations():
    """默认 3 天场景：事件流不存在两条内容完全相同的违规/提醒事件。"""
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"]), EventBus())
    marks = [(e["stage"], e["type"], e["title"], e["reason"])
             for e in r["timeline"] if e["type"] in ("violation", "advisory", "unfixable")]
    assert len(marks) == len(set(marks)), f"存在重复违规事件：{marks}"


# ─────────────────── C：口径统一（5 组参数 V1 零误报） ───────────────────

import pytest

PARAMS = [
    {"days": 3, "budget": 3000, "tags": ["美食", "文化"]},
    {"days": 2, "budget": 2500, "tags": ["亲子", "遛娃"], "family": True},
    {"days": 2, "budget": 2000, "tags": ["夜景"]},
    {"days": 1, "budget": 2000},
    {"days": 4, "budget": 5000, "tags": ["博物馆", "历史"]},
]


@pytest.mark.parametrize("kw", PARAMS)
def test_v1_zero_false_positive(kw):
    """规划器自算内容时长与 validator 同口径：任何参数组合下 V1 零误报。"""
    r = run_pipeline(TripRequest(**kw), EventBus())
    v1 = [e for e in r["timeline"]
          if e["type"] in ("violation", "advisory") and "V1-duration" in e["title"]]
    assert not v1, f"V1 误报：{[(e['title'], e['reason']) for e in v1]}"
    # 每日内容时长（相邻跳口径）≤ 容量
    for d in r["itinerary"]["days"]:
        has_ic = any(it["type"] == "intercity" for it in d["items"])
        cap = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - (1.8 if has_ic else 0)
        content = sum(it.get("leg_hours", 0) + it.get("visit_hours", 0)
                     for it in d["items"] if it["type"] == "poi")
        assert content <= cap + 0.01, \
            f"第{d['day']}天内容 {content:.2f}h > 容量 {cap:.2f}h（两把尺子不一致）"


# ─────────────────── C：摘点逻辑单元测试 ───────────────────

def test_trim_to_capacity_drops_low_score_keeps_must_night():
    """超容摘点：低分先摘、保 must_see、保夜间点、不摘光。"""
    from server.tools import leg_time
    pois = [POI_INDEX[i] for i in ("CQ-01", "CQ-03", "CQ-07", "CQ-09", "CQ-11", "CQ-14", "CQ-16")]
    for p in pois:
        p.setdefault("_score", 5.0)
    POI_INDEX["CQ-14"]["_score"] = 0.5   # 山城步道（低分应最先摘）
    POI_INDEX["CQ-16"]["_score"] = 1.0   # 重庆动物园（次低分）
    POI_INDEX["CQ-01"]["_score"] = 9.0   # 洪崖洞 must+夜间
    POI_INDEX["CQ-07"]["_score"] = 8.0   # 南山 must+夜间
    ordered = _order_day(pois, CITY_HUB["重庆"])
    trimmed = _trim_to_capacity(ordered, "重庆", has_intercity=True)
    ids = [p["id"] for p in trimmed]
    assert len(trimmed) < len(ordered), "应摘掉至少一个点"
    assert "CQ-01" in ids and "CQ-07" in ids, "must/夜间点必须保留"
    assert ids, "不允许摘光"
    prev, total = CITY_HUB["重庆"], 0.0
    for p in trimmed:
        total += leg_time(prev, p) + p["visit_hours"]
        prev = p
    cap = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - 1.8
    assert total <= cap + 0.01


def test_trim_noop_when_within_capacity():
    """容量内：原样返回，不摘点。"""
    pois = [POI_INDEX["CD-01"], POI_INDEX["CD-05"]]
    for p in pois:
        p.setdefault("_score", 5.0)
    ordered = _order_day(pois, CITY_HUB["成都"])
    assert _trim_to_capacity(ordered, "成都") == ordered


# ─────────────────── D：强度惩罚不摘光必游地标 ───────────────────

def test_intensity_penalty_keeps_must_see():
    """轻度强度惩罚后：默认场景重庆天的 must_see 点（洪崖洞/南山一棵树）仍在。"""
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"]), EventBus())
    cq_days = [d for d in r["itinerary"]["days"] if d["city"] == "重庆"]
    assert cq_days, "默认场景应含重庆天"
    ids = {it["poi_id"] for d in cq_days for it in d["items"] if it["type"] == "poi"}
    must_ids = {pid for pid, p in POI_INDEX.items()
                if p["city"] == "重庆" and p.get("must_see")}
    assert must_ids & ids, f"必游地标被摘光：{must_ids} ∩ {ids} 为空"

# ─────────────────── 01C：恢复夜景收尾 + 摘点排序键 ───────────────────

def test_intensity_penalty_keeps_every_must_see_night_poi():
    """默认场景重庆天：必游地标逐个点名，南山一棵树必须在（经典夜景机位）。"""
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"]), EventBus())
    cq = [d for d in r["itinerary"]["days"] if d["city"] == "重庆"]
    ids = {it["poi_id"] for d in cq for it in d["items"] if it["type"] == "poi"}
    assert "CQ-07" in ids, "南山一棵树（必游+夜间+经典夜景机位）必须在行程中"
    assert "CQ-01" in ids, "洪崖洞（必游+夜间）必须在行程中"


def test_night_finale_and_narrative_consistency():
    """夜景收尾断言：默认场景至少一天有 arrival ≥ 19:00 的 poi；
    叙事文案提到夜景的当天，必须确有夜景时段的点位（文案与行程一致）。"""
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"]), EventBus())
    days = r["itinerary"]["days"]

    def h(s):
        return int(s.split(":")[0])

    night_poi = any(
        it["type"] == "poi" and h(it["arrival"]) >= 19
        for d in days for it in d["items"]
    )
    assert night_poi, "默认场景应有夜景收尾（某点位 arrival ≥ 19:00）"
    for d in days:
        nar = d.get("narrative", "")
        # 精确匹配收尾句式，避免点位 summary 里的"夜景"字样误判
        if "夜景收尾" in nar:
            has_night_slot = any(
                it["type"] == "poi" and h(it["arrival"]) >= 18 for it in d["items"]
            )
            assert has_night_slot, f"第{d['day']}天文案提夜景但当天无夜景时段点位"


def test_trim_drop_rank_same_score():
    """同分场景摘点顺序：非必游非夜间最先摘，必游+夜间最后摘（排序键回归）。"""
    from server.agent.planner import _trim_to_capacity
    # 5 个同分点：A(必游+夜间) B(必游) C(夜间) D(非必游非夜间) E(非必游非夜间)
    combo = [("CD-01", 9.0, True, True), ("CD-06", 5.0, True, False),
             ("CD-20", 5.0, False, True), ("CD-09", 5.0, False, False),
             ("CD-19", 5.0, False, False)]
    pois = [POI_INDEX[pid] for pid, *_ in combo]
    saved = {}
    for pid, score, must, night in combo:
        saved[pid] = (POI_INDEX[pid].get("_score"), POI_INDEX[pid]["must_see"], POI_INDEX[pid]["night_friendly"])
        POI_INDEX[pid]["_score"] = score
    try:
        from server.agent.planner import _content_hours, _order_day
        ordered = _order_day(pois, CITY_HUB["成都"])
        cap = (DAY_END - DAY_START - MEAL_HOURS - BUFFER) - 1.8   # 跨城容量，确保要摘 2 个
        assert _content_hours(ordered, "成都") > cap, "测试前提：构造必须超容"
        trimmed = _trim_to_capacity(ordered, "成都", has_intercity=True)
        ids = [p["id"] for p in trimmed]
        # D、E（非必游非夜间）应最先被摘；A（必游+夜间）必须保留
        assert "CD-09" not in ids and "CD-19" not in ids, f"同分下应先摘非必游非夜间：{ids}"
        assert "CD-01" in ids, "必游+夜间点必须最后摘"
    finally:
        for pid, (score, must, night) in saved.items():
            if score is None:
                POI_INDEX[pid].pop("_score", None)
            else:
                POI_INDEX[pid]["_score"] = score


def test_advisory_shown_once_in_default():
    """默认场景（01C 修复后）：软提醒恰好 1 条且 reason 含软约束说明，事件流无重复。"""
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"]), EventBus())
    adv = [e for e in r["timeline"] if e["type"] == "advisory"]
    assert len(adv) == 1, f"默认场景应恰好 1 条软提醒，实际 {len(adv)}"
    assert "软约束" in adv[0]["reason"]
    marks = [(e["stage"], e["type"], e["title"], e["reason"])
             for e in r["timeline"] if e["type"] in ("violation", "advisory", "unfixable")]
    assert len(marks) == len(set(marks)), "事件流不得出现重复违规/提醒"


# ─────────────────── 03B-F2：fix 事件携带被移除 POI id ───────────────────

def test_fix_events_carry_removed_poi_ids():
    """fix 事件 detail 必须带 removed 的 poi_id 列表（前端地图打叉联动）。"""
    r = run_pipeline(TripRequest(days=2, budget=2000, tags=["夜景"]), EventBus())
    fixes = [e for e in r["timeline"] if e["type"] == "fix" and "移除" in e["title"]]
    assert fixes, "夜景场景应有移除事件（V2 硬违规修复）"
    for f in fixes:
        removed = f["detail"].get("removed")
        assert removed, f"fix 事件缺 removed 字段：{f['title']}"
        assert all(pid in POI_INDEX for pid in removed), f"removed 含非法 id：{removed}"
