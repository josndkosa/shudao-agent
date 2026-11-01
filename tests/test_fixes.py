"""缺陷修复回归测试：先红后绿的「调试排错过程记录」证据。

覆盖四个缺陷：
  1. V1 时长规则跨城日误报（判定口径与规划器容量模型对齐）
  2. days=1 生成 2 天（单日聚焦总分更高城市）
  3. 在线模式 KeyError: load（LLM 计划归一化 + 管线防御）
  4. 杂项（死代码 / EventBus seq 实例级重置 / _day_load 首段 leg）
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
    MEAL_HOURS,
    POI_INDEX,
    _allocate_days,
    _day_load,
)
from server.agent.validator import validate
from server.tools import leg_time


def _day(day_no, items, city="重庆", tickets=0, load=None):
    return {"day": day_no, "city": city, "weather": {},
            "items": items,
            "load": load or {"hours": 9.0, "intensity": 5.0, "tickets": tickets}}


def _poi_item(pid, arrival, departure, leg=0.3):
    p = POI_INDEX[pid]
    return {"type": "poi", "poi_id": pid, "name": p["name"], "arrival": arrival,
            "departure": departure, "visit_hours": p["visit_hours"], "ticket": p["ticket"],
            "leg_hours": leg, "tags": p["tags"]}


# ─────────────────── 缺陷 1：V1 跨城日误报 ───────────────────

def test_v1_crosscity_no_false_positive():
    """跨城日：内容 8.8h ≤ 容量 9.2h、收班 20:30 —— 旧口径必误报。"""
    items = [
        {"type": "intercity", "label": "成渝高铁", "arrival": "08:30", "departure": "10:18"},
        _poi_item("CQ-03", "10:30", "13:30", leg=0.2),   # 磁器口 3.0h
        _poi_item("CQ-11", "15:00", "16:00", leg=0.3),   # 湖广会馆 1.0h
        _poi_item("CQ-01", "16:30", "18:30", leg=0.3),   # 洪崖洞 2.0h
        _poi_item("CQ-07", "19:00", "20:30", leg=0.5),   # 南山一棵树 1.5h
    ]
    # 内容时长 = 0.2+3.0 + 0.3+1.0 + 0.3+2.0 + 0.5+1.5 = 8.8h ≤ 容量 11.0-1.8=9.2h
    # 旧口径 span = 20.5-8.5+1.8 = 13.8 → 13.8-2-0.5 = 11.3 > 11.01 → 误报
    plan = {"days": [_day(1, items)]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    assert not any(v["rule"] == "V1-duration" for v in vs), \
        f"V1 跨城日误报：{[v for v in vs if v['rule'] == 'V1-duration']}"


def test_v1_content_overflow_reports_with_reason():
    """非跨城日：内容时长超容量但收班未超 —— 应报 V1 且 detail 指明『内容时长』。"""
    items = [
        _poi_item("CD-01", "08:30", "11:00", leg=0),   # 宽窄巷子 2.5h（0-24 全天）
        _poi_item("CD-07", "11:30", "14:00", leg=0),   # 春熙路太古里 2.5h（0-24）
        _poi_item("CD-05", "14:30", "16:00", leg=0),   # 人民公园 1.5h（6-22）
        _poi_item("CD-02", "16:30", "18:30", leg=0),   # 锦里 2.0h（0-24）
        _poi_item("CD-16", "18:50", "20:20", leg=0),   # 铁像寺水街 1.5h（0-24）
        _poi_item("CD-17", "20:30", "22:00", leg=0),   # 奎星楼街 1.5h（10-24）
    ]
    # 内容 = 2.5+2.5+1.5+2+1.5+1.5 = 11.5h > 11.0h；last_dep 22:00 不超收班
    plan = {"days": [_day(1, items, city="成都")]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    v1 = [v for v in vs if v["rule"] == "V1-duration"]
    assert len(v1) == 1 and "内容时长" in v1[0]["detail"], f"应报一条内容时长违规：{v1}"


def test_v1_close_time_still_reported():
    """收班硬上限保留：last_dep > 22:00 仍报 V1 且 detail 指明『收班』。"""
    items = [_poi_item("CD-01", "08:30", "11:00"), _poi_item("CD-02", "21:00", "23:00")]
    plan = {"days": [_day(1, items, city="成都")]}
    vs = validate(plan, TripRequest(days=1, budget=99999))
    v1 = [v for v in vs if v["rule"] == "V1-duration"]
    assert any("收班" in v["detail"] or "22:00" in v["detail"] for v in v1), f"应收班违规：{v1}"


# ─────────────────── 缺陷 2：days=1 生成 2 天 ───────────────────

def test_days1_exactly_one_day():
    """days=1 时恰生成 1 天，且城市分天 reason 说明选择依据。"""
    r = run_pipeline(TripRequest(days=1, budget=2000), EventBus())
    days = r["itinerary"]["days"]
    assert len(days) == 1, f"days=1 应生成 1 天，实际 {len(days)} 天"
    ev = [e for e in r["timeline"] if "城市分天" in e["title"]]
    assert ev and ("总分" in ev[0]["reason"] or "更高" in ev[0]["reason"]), \
        f"分天 reason 应说明总分依据：{ev[0]['reason'] if ev else '无事件'}"


def test_days3_allocation_unchanged():
    """days=3 多城比例分配行为不受缺陷2修复影响（回归保护）。"""
    r = run_pipeline(TripRequest(days=3, budget=5000, tags=["美食", "文化"]), EventBus())
    assert len(r["itinerary"]["days"]) == 3
    cities = [d["city"] for d in r["itinerary"]["days"]]
    assert len(set(cities)) >= 1


# ─────────────────── 缺陷 3：在线模式 KeyError: load ───────────────────

def test_normalize_llm_plan_adds_load():
    """LLM 计划无 load 字段：归一化补全后 validator.validate 不抛。"""
    from server.agent.planner import _normalize_llm_plan
    raw = {"days": [{"city": "成都", "items": [
        {"type": "poi", "poi_id": "CD-01", "arrival": "09:00", "departure": "11:30"},
        {"type": "poi", "poi_id": "CD-05"},
        {"type": "poi", "poi_id": "NOT-EXIST"},   # 非法 id 必须丢弃
    ]}], "budget": {"total": 999}}
    req = TripRequest(days=1, budget=5000)
    plan = _normalize_llm_plan(raw, req, EventBus())
    d = plan["days"][0]
    assert "load" in d and "tickets" in d["load"], f"load 未补全：{d.keys()}"
    pids = [it["poi_id"] for it in d["items"] if it["type"] == "poi"]
    assert "NOT-EXIST" not in pids and "CD-01" in pids
    for it in d["items"]:
        if it["type"] == "poi":
            for k in ("name", "arrival", "departure", "visit_hours", "ticket", "leg_hours", "tags"):
                assert k in it, f"item 缺字段 {k}"
    vs = validate(plan, req)   # 关键：不抛 KeyError
    assert isinstance(vs, list)


def test_llm_plan_empty_days_fallback(monkeypatch):
    """LLM 返回 {"days": []} 时降级离线规划器，事件流出现 plan/fallback。"""
    from server.agent import llm as llm_mod
    from server.agent import planner as planner_mod

    class FakeMsg:
        def __init__(self, c):
            self.content = c

    monkeypatch.setattr(llm_mod, "chat", lambda *a, **k: (FakeMsg('{"days": []}'), "final"))
    bus = EventBus()
    plan = planner_mod.llm_plan(TripRequest(days=2, budget=3000, tags=["美食"]), bus)
    assert plan["mode"] == "offline-planner", f"应降级离线：{plan.get('mode')}"
    assert any(e.type == "fallback" for e in bus.events), "事件流应有 plan/fallback"


def test_pipeline_survives_validate_crash(monkeypatch):
    """校验段抛异常：管线不崩，发 validate/fallback 事件并继续叙事段。"""
    from server.agent import pipeline as pl

    def boom(plan, request):
        raise RuntimeError("模拟校验崩溃")

    monkeypatch.setattr(pl.validator, "validate", boom)
    r = run_pipeline(TripRequest(days=1, budget=5000), EventBus())
    assert any(e["stage"] == "validate" and e["type"] == "fallback" for e in r["timeline"])
    assert r["itinerary"].get("days"), "叙事段应照常产出"


def test_narrator_none_content_falls_back(monkeypatch):
    """narrator 在线分支 msg.content=None：显式兜底走模板，不依赖 AttributeError。"""
    from server.agent import llm as llm_mod
    from server.agent.narrator import narrate

    class FakeMsg:
        content = None

    monkeypatch.setattr(llm_mod, "chat", lambda *a, **k: (FakeMsg(), "final"))
    plan = {"days": [{"day": 1, "city": "成都",
                      "weather": {"day": "多云", "temp": [10, 17], "advice": ""},
                      "items": [{"type": "poi", "poi_id": "CD-01", "name": "宽窄巷子",
                                 "arrival": "09:00", "departure": "11:30",
                                 "tags": ["美食"], "summary": "清代街巷"}],
                      "load": {"hours": 5, "intensity": 1, "tickets": 0}}]}
    bus = EventBus()
    narrate(plan, bus, mode="online")
    assert plan["days"][0]["narrative"], "模板兜底文案应为非空"
    assert any(e.type == "fallback" for e in bus.events)


# ─────────────────── 缺陷 3b：工具结果截断 → 幻觉 POI（03F 缺陷A） ───────────────────

def test_llm_tool_result_projected_not_truncated(monkeypatch):
    """03F 缺陷A回归锁：poi_search 工具结果必须经 _poi_brief 投影后再进 messages——
    全量厚字段（大理 15 点 ≈ 5651 字符）超 [:4000] 截成烂尾 JSON，模型只能
    「补全」出幻觉 POI id（在线实测 17 个非法 POI 的根因）。"""
    import json
    from types import SimpleNamespace

    from server.agent import llm as llm_mod
    from server.agent import planner as planner_mod

    state = {"n": 0}
    tool_msgs = []

    def fake_chat(messages, tools=None, temperature=0.3, json_mode=False):
        state["n"] += 1
        tool_msgs.extend(m for m in messages if m["role"] == "tool")
        if state["n"] == 1:
            call = SimpleNamespace(id="call_1", function=SimpleNamespace(
                name="poi_search", arguments='{"city": "大理"}'))
            return SimpleNamespace(content=None, tool_calls=[call]), "tool_call"
        return SimpleNamespace(content=json.dumps(
            {"days": [{"day": 1, "city": "大理", "items": [{"poi_id": "DL-01"}]}]},
            ensure_ascii=False), tool_calls=None), "final"

    monkeypatch.setattr(llm_mod, "chat", fake_chat)
    plan = planner_mod.llm_plan(
        TripRequest(days=1, budget=3000, tags=["文化"], cities=["大理"]), EventBus())

    assert plan["mode"] == "llm-fc", f"应走在线规划：{plan.get('mode')}"
    assert len(tool_msgs) == 1, "第二轮 chat 应携带一条 tool 消息"
    content = tool_msgs[0]["content"]
    payload = json.loads(content)            # 烂尾 JSON 会在这里炸
    assert len(content) < 3000, f"投影后工具结果仍超长：{len(content)} 字符"
    pois = payload["pois"]
    assert pois and all("id" in p for p in pois), "投影必须保留 id（LLM 回抄依据）"
    assert all("lat" not in p and "summary" not in p and "slope" not in p for p in pois), \
        "厚字段未投影掉——_poi_brief 没接上会重新撞截断"


def test_tool_content_truncates_whole_elements():
    """超长工具结果按整点丢弃截断：输出仍是合法 JSON 且带 truncated 说明，
    绝不截在 JSON 结构中间（残缺 JSON 会被模型补全成幻觉）。"""
    import json

    from server.agent.planner import _tool_content

    big = {"count": 40, "pois": [
        {"id": f"X-{i:03d}", "name": "点" * 30, "city": "测试"} for i in range(40)]}
    s = _tool_content(big, limit=1000)
    payload = json.loads(s)
    assert payload["count"] == len(payload["pois"]) < 40, "count 应与实际保留数一致"
    assert "truncated" in payload, "截断必须显式说明，不让模型猜"
    assert len(s) <= 1000
    small = {"count": 2, "pois": [{"id": "A", "name": "甲"}, {"id": "B", "name": "乙"}]}
    assert json.loads(_tool_content(small)) == small, "未超长时原样返回"


# ─────────────────── 缺陷 4：杂项 ───────────────────

def test_eventbus_seq_resets_per_instance():
    """EventBus 实例各自 seq 从 1 开始；跨实例时间戳 t 不回退。"""
    b1 = EventBus()
    b1.emit("system", "start", "a")
    b1.emit("system", "done", "b")
    b2 = EventBus()
    b2.emit("system", "start", "c")
    assert [e.seq for e in b1.events] == [1, 2], "实例1 seq 应为 1,2"
    assert b2.events[0].seq == 1, "实例2 seq 应重新从 1 开始"
    assert b2.events[0].t >= b1.events[-1].t, "时间戳基准不应回退"


def test_day_load_includes_first_leg():
    """_day_load 必须计入枢纽→首点的第一段 leg。"""
    pois = [POI_INDEX["CD-01"], POI_INDEX["CD-03"]]
    load = _day_load(pois, "成都")
    expect = (MEAL_HOURS + BUFFER
              + sum(p["visit_hours"] for p in pois)
              + leg_time(CITY_HUB["成都"], pois[0])
              + leg_time(pois[0], pois[1]))
    assert abs(load["hours"] - expect) < 0.01, \
        f"hours={load['hours']} 应含首段 leg，期望 {expect:.2f}"


def test_allocate_days_single_day_single_city():
    """_allocate_days(1, ...) 只返回一个城市。"""
    pools = {"成都": [{"_score": 10.0}], "重庆": [{"_score": 6.0}]}
    alloc = _allocate_days(1, pools)
    assert len(alloc) == 1 and "成都" in alloc
