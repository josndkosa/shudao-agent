"""03G 自然语言抽取器测试：离线规则实现 + 在线 LLM 实现（mock）+ 降级链 + 受控词表。

抽取与规划分离的架构锁：
- 两种实现返回完全同构（前端零分叉）
- 城市只认 meta.city_info、标签必须落受控词表（模型自造语义在此拦死）
- LLM 失败 → 规则实现，不抛异常
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from server.agent import llm as llm_mod
from server.agent.events import EventBus
from server.agent.parse_request import (
    _controlled_tags,
    _finalize,
    parse_request,
)

MAIN = "我在北京，想去成都和重庆玩3天，预算3000，喜欢美食和夜景"


def test_offline_full_sentence():
    """主验收用例：一句话抽全参数，离线（无 key）下 source=rules。"""
    r = parse_request(MAIN, EventBus())
    assert r["source"] == "rules"
    assert r["origin"] == "北京"
    assert r["cities"] == ["成都", "重庆"]
    assert r["days"] == 3 and r["budget"] == 3000
    assert set(r["tags"]) == {"美食", "夜景"}
    assert r["family"] is False
    assert "暂未计入行程时间与交通费" in r["note"]


def test_offline_family_and_days():
    r = parse_request("带娃去成都玩5天", EventBus())
    assert r["family"] is True and r["days"] == 5 and r["cities"] == ["成都"]


def test_offline_budget_with_unit():
    r = parse_request("预算800块", EventBus())
    assert r["budget"] == 800


def test_offline_cn_number_and_aliases():
    """中文数字「五天」、城市别名「春城/山城」「从X出发」。"""
    r = parse_request("从上海出发去春城和山城玩五天，预算5000元，喜欢徒步和博物馆", EventBus())
    assert r["days"] == 5 and r["budget"] == 5000
    assert set(r["cities"]) == {"昆明", "重庆"}
    assert r["origin"] == "上海"
    assert set(r["tags"]) == {"徒步", "博物馆"}


def test_offline_unrelated_text_fallback():
    r = parse_request("今天天气不错啊哈哈哈哈", EventBus())
    assert r["source"] == "fallback"
    assert not any([r["days"], r["budget"], r["cities"], r["tags"], r["origin"], r["family"]])


def test_origin_unsupported_region_honest_note():
    """「我在新疆」：出发地仅记录 + 如实提示（不参与计算）。"""
    r = parse_request("我在新疆", EventBus())
    assert r["origin"] == "新疆"
    assert "新疆" in r["note"] and "暂未计入" in r["note"]


def test_finalize_filters_unknown_city_and_tags():
    """归一层：城市只认 city_info、标签必须落受控词表——模型自造语义在此拦死。"""
    raw = {"origin": "北京", "cities": ["成都", "纽约", "火星"],
           "days": 99, "budget": 1, "tags": ["美食", "自造标签", "夜景"], "family": True}
    out = _finalize(raw)
    assert out["cities"] == ["成都"]
    assert "纽约" in out["note"] and "火星" in out["note"]
    assert out["days"] == 30                      # clamp 到上限
    assert out["budget"] == 500                   # clamp 到下限
    assert set(out["tags"]) == {"美食", "夜景"}    # 自造标签被丢弃
    assert out["family"] is True


def test_all_tags_within_controlled_vocabulary():
    """验收：所有 tags 都落在受控词表内，无一例外。"""
    sentences = [
        MAIN, "带娃去成都玩5天", "喜欢美食文化夜景亲子山水民族博物馆徒步骑行摄影购物",
        "想去版纳和西江看梯田和溶洞", "预算800块玩10天，喝茶看雪山",
    ]
    for s in sentences:
        r = parse_request(s, EventBus())
        for t in r["tags"]:
            assert t in _controlled_tags(), f"标签 {t} 逸出受控词表（输入：{s}）"


def _mk_llm_chat(payload, fail=False):
    class FakeMsg:
        def __init__(self, c):
            self.content = c
    if fail:
        def _raise(*a, **k):
            raise RuntimeError("simulated llm outage")
        return _raise
    return lambda *a, **k: (FakeMsg(payload), "final")


def test_llm_happy_path(monkeypatch):
    """在线实现：纯 JSON 调用（json_mode）→ 校验/归一同离线路径。"""
    monkeypatch.setattr(llm_mod, "resolve_mode", lambda: "online")
    monkeypatch.setattr(llm_mod, "chat", _mk_llm_chat(
        '{"origin": "北京", "cities": ["成都", "重庆", "纽约"], "days": 3,'
        ' "budget": 3000, "tags": ["美食", "夜景"], "family": false}'))
    r = parse_request(MAIN, EventBus())
    assert r["source"] == "llm"
    assert r["origin"] == "北京" and r["days"] == 3 and r["budget"] == 3000
    assert r["cities"] == ["成都", "重庆"]       # 纽约被过滤
    assert "纽约" in r["note"]
    assert set(r["tags"]) == {"美食", "夜景"}


def test_llm_invalid_json_falls_back_to_rules(monkeypatch):
    """模型返回非法 JSON → 降级规则实现，不抛异常（source=rules）。"""
    monkeypatch.setattr(llm_mod, "resolve_mode", lambda: "online")
    monkeypatch.setattr(llm_mod, "chat", _mk_llm_chat("这不是JSON {{{ 烂尾"))
    r = parse_request(MAIN, EventBus())
    assert r["source"] == "rules"
    assert r["cities"] == ["成都", "重庆"] and r["days"] == 3


def test_llm_exception_falls_back_to_rules(monkeypatch):
    """调用本身抛异常（网络/超时）→ 降级规则实现。"""
    monkeypatch.setattr(llm_mod, "resolve_mode", lambda: "online")
    monkeypatch.setattr(llm_mod, "chat", _mk_llm_chat(None, fail=True))
    r = parse_request("想去成都玩3天", EventBus())
    assert r["source"] == "rules" and r["days"] == 3


def test_parse_emits_readable_events():
    """「每条决策带 reason」的延伸：AI 的理解用户看得见。"""
    bus = EventBus()
    parse_request(MAIN, bus)
    dec = [e for e in bus.events if e.type == "decision"]
    assert dec and "从你的话里读到了" in dec[0].title
    assert "3 天" in dec[0].title and "成都、重庆" in dec[0].title
