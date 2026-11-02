"""03J 显式偏好画像测试：读写容错 / 意图识别 / 生效 / 事件可观察 / 回归隔离。

设计决定（对应任务单验收逐条）：
- 显式指令式：只有「记住：xxx」触发写入，无黑盒推断
- 诚实边界：口味/具体景点记不了 → 如实提示 + 画像零污染
- 显式优先：这次说了预算五千就用五千
- 回归锁：无画像时管线行为与改造前逐字一致（conftest 全局隔离保证基线干净）
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SD_LLM_MODE", "offline")

from server.agent import TripRequest, run_pipeline
from server.agent.events import EventBus
from server.agent.parse_request import parse_request
from server.agent.planner import POI_INDEX
from server.agent.preferences import (
    clear_prefs,
    load_prefs,
    merge_prefs,
    read_profile,
    save_prefs,
)


def _pref_file(tmp_path):
    return tmp_path / "preferences.json"


def _isolated(monkeypatch, tmp_path):
    p = _pref_file(tmp_path)
    monkeypatch.setenv("SD_PREFERENCES_PATH", str(p))
    return p


# ── 任务 A：偏好文件读写与容错 ──────────────────────────────

def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    p = _isolated(monkeypatch, tmp_path)
    assert save_prefs({"family": True, "budget": 2000, "tags": ["夜景"],
                       "avoid_tags": ["博物馆"]})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == 1 and "updated_at" in data
    assert load_prefs() == {"family": True, "budget": 2000,
                            "tags": ["夜景"], "avoid_tags": ["博物馆"]}
    # 原子写：不留 .tmp 残骸
    assert not p.with_suffix(".tmp").exists()


def test_load_missing_or_corrupt_file_degrades_to_empty(monkeypatch, tmp_path):
    """文件不存在 / 内容损坏 → 空画像，绝不抛异常。"""
    p = _isolated(monkeypatch, tmp_path)
    assert load_prefs() == {}                       # 不存在
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{这不是合法JSON", encoding="utf-8")
    assert load_prefs() == {}                       # 损坏
    p.write_text(json.dumps({"prefs": {"family": "yes"}}), encoding="utf-8")
    assert load_prefs() == {}                       # 类型非法的键被丢弃


def test_save_to_unwritable_path_returns_false(monkeypatch, tmp_path):
    """目录不可写 → 保存失败返回 False，不抛异常（规划照常跑完由管线测试覆盖）。"""
    # 父路径是一个文件 → mkdir 必然失败，模拟不可写
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SD_PREFERENCES_PATH", str(blocker / "sub" / "p.json"))
    assert save_prefs({"family": True}) is False


def test_merge_prefs_explicit_overrides_memory():
    """显式指定的值优先于记忆：这次说预算五千 → 用五千。"""
    prefs = {"family": True, "budget": 2000, "tags": ["美食"], "avoid_tags": ["博物馆"]}
    # 显式 5000 覆盖记忆 2000；显式 tags 与记忆合并；未说的 family 由记忆填
    out, applied = merge_prefs({"budget": 5000, "tags": ["夜景"], "family": False}, prefs)
    assert out["budget"] == 5000 and out["family"] is True
    assert set(out["tags"]) == {"夜景", "美食"}
    assert out["avoid_tags"] == ["博物馆"]
    assert any("偏好" in a for a in applied) and any("避开" in a for a in applied)
    # 无记忆 → 原样返回零应用（回归口径）
    out2, applied2 = merge_prefs({"budget": 3000, "tags": ["美食"], "family": False}, {})
    assert out2 == {"budget": 3000, "tags": ["美食"], "family": False} and applied2 == []
    # budget=None（自然语言未说）→ 记忆填空缺
    out3, applied3 = merge_prefs({"budget": None}, {"budget": 2000})
    assert out3["budget"] == 2000 and applied3 == ["预算 2000"]


# ── 任务 B/C：记住 / 忘掉 / 查看（意图识别 + 增量画像） ─────────────

def test_remember_family_and_avoid(monkeypatch, tmp_path):
    p = _isolated(monkeypatch, tmp_path)
    r = parse_request("记住：我带娃，不去博物馆", EventBus())
    assert r["remember"] and not r["forget"] and not r["view"]
    assert r["prefs"] == {"family": True, "avoid_tags": ["博物馆"]}
    saved = json.loads(p.read_text(encoding="utf-8"))["prefs"]
    assert saved == {"family": True, "avoid_tags": ["博物馆"]}


def test_remember_budget_chinese_number(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    r = parse_request("记住：预算两千", EventBus())
    assert r["prefs"]["budget"] == 2000
    r2 = parse_request("记住：预算一万五", EventBus())
    assert r2["prefs"]["budget"] == 15000      # 新值覆盖


def test_remember_taste_honest_refusal(monkeypatch, tmp_path):
    """「记住：我不吃辣」→ 如实提示记不了，且画像里没有多出任何东西。"""
    p = _isolated(monkeypatch, tmp_path)
    r = parse_request("记住：我不吃辣", EventBus())
    assert r["remember"]
    assert "数据维度还不支持" in r["note"]
    assert not p.exists()                       # 空画像不落盘


def test_remember_partial_success_honest_note(monkeypatch, tmp_path):
    """部分可记部分记不了：如实说清记住了什么、什么记不下来。"""
    _isolated(monkeypatch, tmp_path)
    r = parse_request("记住：我带娃，不吃辣", EventBus())
    assert r["prefs"] == {"family": True}
    assert "已记住：亲子模式" in r["note"]
    assert "口味偏好" in r["note"]


def test_remember_accumulates(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    parse_request("记住：喜欢夜景", EventBus())
    r = parse_request("记住：喜欢徒步，避开博物馆", EventBus())
    assert r["prefs"]["tags"] == ["夜景", "徒步"]
    assert r["prefs"]["avoid_tags"] == ["博物馆"]


def test_view_lists_prefs(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    parse_request("记住：我带娃，不去博物馆", EventBus())
    r = parse_request("我记住了什么", EventBus())
    assert r["view"] and "亲子模式" in r["note"] and "博物馆" in r["note"]


def test_forget_all_and_single_item(monkeypatch, tmp_path):
    p = _isolated(monkeypatch, tmp_path)
    parse_request("记住：我带娃，不去博物馆，喜欢夜景", EventBus())
    r = parse_request("忘掉博物馆", EventBus())          # 只删指定项
    assert r["forget"] and "博物馆" not in json.dumps(r["prefs"])
    assert r["prefs"].get("family") is True and r["prefs"].get("tags") == ["夜景"]
    r2 = parse_request("忘掉我的偏好", EventBus())        # 全清
    assert r2["prefs"] == {} and not p.exists()
    assert "已忘掉全部偏好" in r2["note"]


def test_memory_intent_events(monkeypatch, tmp_path):
    """可观察验收：记住/忘掉的瞬间，事件流里有对应事件（含 reason）。"""
    _isolated(monkeypatch, tmp_path)
    bus = EventBus()
    parse_request("记住：我带娃，不去博物馆", bus)
    evs = [e for e in bus.events if e.title == "已记住偏好"]
    assert evs and "亲子模式" in evs[0].reason and "不随作品分发" in evs[0].reason
    bus2 = EventBus()
    parse_request("忘掉我的偏好", bus2)
    assert any(e.title == "已忘掉全部偏好" for e in bus2.events)


def test_normal_parse_merges_memory_into_note(monkeypatch, tmp_path):
    """自然语言规划语句：未说的字段由记忆填空缺 + note 说明「已按上次的偏好」。"""
    _isolated(monkeypatch, tmp_path)
    parse_request("记住：我带娃，预算两千", EventBus())
    r = parse_request("去大理玩两天", EventBus())   # 「两」天：03J 顺手补的口语边界
    assert not r["remember"]
    assert r["days"] == 2 and r["family"] is True and r["budget"] == 2000
    assert "已按上次的偏好" in r["note"]
    # 显式优先：这次说了预算五千 → 用五千
    r2 = parse_request("去大理玩三天，预算五千", EventBus())
    assert r2["budget"] == 5000


# ── 任务 D：avoid_tags 生效（候选硬排除，V1–V5 零触碰） ──────────────

def test_avoid_tags_excludes_museum_pois(monkeypatch, tmp_path):
    """记住「不去博物馆」之后规划 → 行程里没有博物馆类 POI。"""
    _isolated(monkeypatch, tmp_path)
    parse_request("记住：我带娃，不去博物馆", EventBus())
    r = run_pipeline(TripRequest(days=2, budget=5000, tags=["文化"],
                                 cities=["成都", "重庆"]), EventBus())
    for d in r["itinerary"]["days"]:
        for it in d["items"]:
            if it["type"] == "poi":
                assert "博物馆" not in (POI_INDEX[it["poi_id"]].get("tags") or []), \
                    f"博物馆点位 {it['name']} 未被排斥过滤"
    assert any("候选排除" in e["title"] for e in r["timeline"])
    assert any("应用偏好记忆" in e["title"] for e in r["timeline"])


def test_family_memory_enforces_v5(monkeypatch, tmp_path):
    """记住「带娃」之后规划 → 行程里没有亲子友好度 < 2 的点（V5 生效）。"""
    _isolated(monkeypatch, tmp_path)
    parse_request("记住：我带娃", EventBus())
    r = run_pipeline(TripRequest(days=2, budget=5000, cities=["成都"]), EventBus())
    for d in r["itinerary"]["days"]:
        for it in d["items"]:
            if it["type"] == "poi":
                assert POI_INDEX[it["poi_id"]]["family"] >= 2, \
                    f"亲子不友好点 {it['name']} 混入（V5 未生效）"


def test_memory_event_reason_contains_content_and_time(monkeypatch, tmp_path):
    """「应用偏好记忆」事件：reason 写清记住了什么、什么时候记的。"""
    _isolated(monkeypatch, tmp_path)
    parse_request("记住：我带娃，不去博物馆", EventBus())
    bus = EventBus()
    run_pipeline(TripRequest(days=1, budget=5000, cities=["成都"]), bus)
    ev = next(e for e in bus.events if e.title == "应用偏好记忆")
    assert "亲子模式" in ev.reason and "避开 博物馆" in ev.reason
    assert "上次记录于" in ev.reason and "显式指定的值优先于记忆" in ev.reason


def test_no_memory_pipeline_identical_to_before():
    """回归锁：无画像 → 管线请求的行为与 03J 改造前一致（conftest 全局隔离保证基线干净）。

    直接证据：avoid_tags 恒空时 _apply_avoid 原样返回 + merge_prefs 零应用——
    再叠加既有全部回归测试（双城 fixture / baseline 口径）在同一基线上全绿。
    """
    from server.agent.planner import _apply_avoid

    pois = [{"id": "X", "tags": ["博物馆"]}]
    assert _apply_avoid(pois, []) is pois          # 空列表原样返回（同一对象，零开销）
    out, applied = merge_prefs({"budget": 3000, "tags": [], "family": False}, {})
    assert out == {"budget": 3000, "tags": [], "family": False} and applied == []
    assert load_prefs() == {}                        # 测试基线无画像


# ── API 端点契约（含 timeline 返回） ──────────────────────────

def test_parse_endpoint_memory_contract(monkeypatch, tmp_path):
    """/api/parse：记住指令返回 remember=true + prefs + timeline（事件流可见）。"""
    from fastapi.testclient import TestClient

    from server.app import app
    _isolated(monkeypatch, tmp_path)
    client = TestClient(app)
    r = client.post("/api/parse", json={"text": "记住：我带娃，不去博物馆"})
    body = r.json()
    assert r.status_code == 200 and body["remember"] is True
    assert body["prefs"]["family"] is True and body["prefs"]["avoid_tags"] == ["博物馆"]
    assert any(e["title"] == "已记住偏好" for e in body["timeline"])
    # 隐私：画像不进仓库/提交包——物理上位于仓库外（tmp_path），git 看不到
    r2 = client.post("/api/parse", json={"text": "去成都玩三天"})
    assert r2.json()["days"] == 3 and "已按上次的偏好" in r2.json()["note"]


def test_clear_prefs_removes_file(monkeypatch, tmp_path):
    p = _isolated(monkeypatch, tmp_path)
    save_prefs({"family": True})
    assert p.exists()
    assert clear_prefs() and not p.exists()
    assert read_profile() is None
