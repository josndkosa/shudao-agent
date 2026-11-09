"""03M 审查修复回归锁（外部审查报告 2026-11-09 的 P0/P1 修复固化）。

背景：外部审查（Codex）独立复现了 5 个 P0 与多个 P1。本文件把修复后的正确行为
钉成回归锁——没有这些测试，下次重构又会把「不可执行时间表判通过」「超预算写通过」
这类问题改回去。每条都对应一次真实复现过的事故，先红后绿。

覆盖：
  P0-01 geo 的 null 字符串参数不得导致空图幅
  P0-03 所有活动（poi/meal/intercity）时间单调不重叠
  P0-04 超预算时报告不得写「V4 预算校验通过」；费用统一用「预估」
  P0-05 合法空候选不崩溃、有明确降级事件；budget(0) 不除零
  P1-04 否定词（不带娃/不要亲子）、城市文本顺序、阿拉伯+中文混合金额（2千）
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from fastapi.testclient import TestClient

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus
from server.agent.parse_request import parse_request
from server.agent.report import render_report
from server.app import app
from server.tools.budget import budget as budget_tool


def test_geo_null_param_returns_full_snapshot():
    """P0-01：历史客户端 encodeURIComponent(null) 产生的 "null" 字符串不得被当城市名过滤。"""
    client = TestClient(app)
    r = client.get("/api/geo", params={"plan_id": "null", "city": "null"})
    assert r.status_code == 200
    assert len(r.json()["cities"]) == 15, "city=null 应视为未指定，返回全部图幅"
    assert sum(len(v) for v in r.json()["points"].values()) == 237


def test_activities_never_overlap_default_scene():
    """P0-03：默认场景所有活动（poi/meal/intercity）时间单调不重叠——
    此前武侯祠 10:10-12:10 与固定 12:00 午餐重叠，却被判校验通过。"""
    bus = EventBus()
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"],
                                 cities=["成都", "重庆"]), bus)
    for d in r["itinerary"]["days"]:
        items = d["items"]
        for a, b in zip(items, items[1:]):
            if a.get("departure") and b.get("arrival"):
                assert a["departure"] <= b["arrival"], \
                    f"Day{d['day']} 活动重叠：{a.get('name') or a.get('label')} " \
                    f"{a['arrival']}-{a['departure']} 与 {b.get('name') or b.get('label')} {b['arrival']}"


def test_report_overbudget_never_claims_pass():
    """P0-04：超预算时报告必须写超额与差额，不得写「V4 预算校验通过」；费用用「预估」。"""
    bus = EventBus()
    r = run_pipeline(TripRequest(days=7, budget=500, tags=[], cities=["成都", "重庆"]), bus)
    md = render_report(r["itinerary"], [e.to_dict() for e in bus.events], {})
    assert "超出预算" in md and "未通过 V4 预算校验" in md, "超预算必须如实报出"
    assert "（V4 预算校验通过）" not in md, "超预算不得写通过"
    assert "预估总花费" in md and "实际总花费" not in md, "费用为估算，统一用「预估」"


def test_report_in_budget_still_passes():
    """预算内的正常场景仍应写通过（不误伤正常结论）。"""
    bus = EventBus()
    r = run_pipeline(TripRequest(days=3, budget=3000, tags=["美食", "文化"],
                                 cities=["成都", "重庆"]), bus)
    md = render_report(r["itinerary"], [e.to_dict() for e in bus.events], {})
    assert "V4 预算校验通过" in md


def test_empty_candidates_no_crash_and_honest_fallback():
    """P0-05：排斥标签把候选清空是合法输入——不得崩溃，应有明确「无法规划」事件。"""
    bus = EventBus()
    r = run_pipeline(TripRequest(
        days=2, budget=2000, tags=[], cities=["成都"],
        avoid_tags=["美食", "园林", "博物馆", "亲子", "夜景", "宗教", "文创"]), bus)
    assert r["itinerary"]["days"] == [], "空候选应返回空行程，不是崩溃"
    fb = [e for e in bus.events if e.type == "fallback" and "无法规划" in e.title]
    assert fb, "空候选必须有明确的无法规划事件（诚实收尾，不静默放宽排斥）"
    assert budget_tool(0, 0)["per_day"] == 0.0, "budget(0) 不得除零"


def test_family_negation_phrases():
    """P1-04：「不带娃」「不要亲子」是否定，不得误判为亲子模式；「一个人带娃」仍是亲子。"""
    assert parse_request("不带娃去成都玩3天", EventBus())["family"] is False
    assert parse_request("我一个人去成都，不要亲子", EventBus())["family"] is False
    assert parse_request("我带娃去成都玩3天", EventBus())["family"] is True
    assert parse_request("一个人带娃去成都", EventBus())["family"] is True, "「一个人带娃」不能误判"


def test_city_order_follows_text_order():
    """P1-04：城市顺序按用户表达（先说先走），不按 meta 表顺序。"""
    r = parse_request("先去重庆再去成都玩三天", EventBus())
    assert r["cities"] == ["重庆", "成都"], f"应按文本顺序：{r['cities']}"


def test_budget_arabic_chinese_mixed_amount():
    """P1-04：「2千」=2000（阿拉伯+中文混合单位）；既有中文金额能力不回潮。"""
    assert parse_request("预算2千去成都3天", EventBus())["budget"] == 2000
    assert parse_request("预算两千去成都", EventBus())["budget"] == 2000
    assert parse_request("预算一万五去成都", EventBus())["budget"] == 15000
