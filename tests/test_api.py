"""Prompt 02 API 测试：FastAPI 六端点契约 + SSE + 对话式改行程（TestClient，不启真实端口）。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SD_LLM_MODE"] = "offline"

from fastapi.testclient import TestClient

from server.app import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "mode" in body and "llm" in body


def test_plan_days_match_request():
    r = client.post("/api/plan", json={"days": 3, "budget": 3000, "tags": ["美食", "文化"]})
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"]
    assert len(body["itinerary"]["days"]) == 3
    assert isinstance(body["timeline"], list) and body["timeline"]
    assert body["mode"]


def test_plan_deterministic():
    """相同请求必须产出完全一致的行程（确定性，录屏与答辩复现依赖）。"""
    a = client.post("/api/plan", json={"days": 2, "budget": 2000, "tags": ["夜景"]}).json()
    b = client.post("/api/plan", json={"days": 2, "budget": 2000, "tags": ["夜景"]}).json()
    assert json.dumps(a["itinerary"], ensure_ascii=False, sort_keys=True) == \
           json.dumps(b["itinerary"], ensure_ascii=False, sort_keys=True)


def test_stream_sse_frames_and_done():
    r = client.post("/api/stream", json={"days": 2, "budget": 2000, "tags": ["夜景"]})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    frames = [f for f in r.text.strip().split("\n\n") if f]
    assert frames and all(f.startswith("data: ") for f in frames)
    events = [json.loads(f[len("data: "):]) for f in frames]
    assert events[0]["stage"] == "system"          # 与 MockApi 同构：管线启动开头
    # 哨兵帧必须是纯 {"type":"done"}（无 stage/seq），且业务事件全部在其之前送达
    assert events[-1].get("type") == "done" and "stage" not in events[-1], \
        f"末帧应为流结束哨兵，实际：{events[-1]}"
    # 契约演进（任务A方案B）：哨兵前新增 plan_result 控制帧（行程随流返回），它之前才是业务事件
    assert events[-2].get("type") == "plan_result" and "stage" not in events[-2], \
        f"倒数第二帧应为 plan_result，实际：{events[-2]}"
    assert events[-3]["stage"] in ("narrate", "system"), \
        f"plan_result 之前应完整送达业务事件，实际：{events[-3]}"
    for ev in events[:-2]:
        for k in ("seq", "stage", "type", "title"):
            assert k in ev, f"事件缺字段 {k}：{ev}"


def test_stream_plan_result_carries_itinerary_and_supports_revise():
    """任务A核心：行程随事件流回来（一次规划只跑一次管线），plan_id 可直接喂 /api/revise。"""
    r = client.post("/api/stream", json={"days": 3, "budget": 3000, "tags": ["美食", "文化"],
                                         "cities": ["成都", "重庆"]})
    events = [json.loads(f[len("data: "):]) for f in r.text.strip().split("\n\n") if f]
    pr = next(e for e in events if e.get("type") == "plan_result")
    assert pr["plan_id"] and pr["budget"] and pr["mode"]
    days = pr["itinerary"]["days"]
    assert len(days) == 3
    # 同源断言：事件流「第N天选点」的 poi 集合 ⊆ 行程单 Day N 的 poi 集合
    # （plan_result 与事件流出自同一次 run_pipeline，天然同源——锁的是契约不被改回去）
    import re
    for e in events:
        m = re.match(r"第(\d+)天选点", e.get("title", ""))
        if m and isinstance(e.get("detail"), list):
            day = next(d for d in days if d["day"] == int(m.group(1)))
            day_pids = {it["poi_id"] for it in day["items"] if it["type"] == "poi"}
            assert set(e["detail"]) <= day_pids, \
                f"事件流与行程不同源：Day{m.group(1)} 事件 {e['detail']} vs 行程 {day_pids}"
    # revise 链路：stream 缓存的 plan_id 必须能用（对话改行程是 30 分展示项）
    rv = client.post("/api/revise", json={"plan_id": pr["plan_id"], "message": "第二天太赶"})
    assert rv.status_code == 200
    assert rv.json()["revised_day"] == 2


def test_stream_single_pipeline_run():
    """单跑锁：一次 stream 只跑一次管线——事件流里 plan 阶段 start 事件恰 1 条。

    旧路径前端先 plan 后 stream（两次独立管线），在线模式下 DeepSeek 成本 ×2。
    """
    r = client.post("/api/stream", json={"days": 2, "budget": 2000, "tags": ["夜景"]})
    events = [json.loads(f[len("data: "):]) for f in r.text.strip().split("\n\n") if f]
    starts = [e for e in events if e.get("stage") == "plan" and e.get("type") == "start"]
    assert len(starts) == 1, f"plan start 应只有 1 条（单跑语义），实际 {len(starts)}"


def test_plan_runs_in_threadpool(monkeypatch):
    """任务B锁：/api/plan 的 run_pipeline 必须经 asyncio.to_thread（不阻塞事件循环）。"""
    import asyncio as _asyncio

    import server.app as app_mod

    calls = []
    orig_to_thread = _asyncio.to_thread

    def fake_pipeline(request, bus):
        return {"itinerary": {"days": [], "budget": {}}, "timeline": [], "mode": "offline"}

    async def spy_to_thread(fn, *a, **k):
        calls.append(getattr(fn, "__name__", str(fn)))
        return await orig_to_thread(fn, *a, **k)

    monkeypatch.setattr(app_mod, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(_asyncio, "to_thread", spy_to_thread)
    r = client.post("/api/plan", json={"days": 1, "budget": 2000})
    assert r.status_code == 200
    # spy 记录到的是 patch 后的 fn 名——恰好证明「端点里的 run_pipeline（此刻为 fake）
    # 经由 asyncio.to_thread 执行」这条链路本身
    assert "fake_pipeline" in calls, f"run_pipeline 未走 asyncio.to_thread：{calls}"


def test_revise_reduce_day2():
    # 双城场景（多城化后默认演示仍是成渝，revise 减载语义锁死在双城行程上）
    p = client.post("/api/plan", json={"days": 3, "budget": 3000, "tags": ["美食", "文化"],
                                       "cities": ["成都", "重庆"]}).json()
    pid = p["plan_id"]
    d2 = p["itinerary"]["days"][1]
    before_n = len([it for it in d2["items"] if it["type"] == "poi"])
    before_h = d2["load"]["hours"]

    r = client.post("/api/revise", json={"plan_id": pid, "message": "第二天太赶"})
    assert r.status_code == 200
    body = r.json()
    assert body["revised_day"] == 2
    d2a = body["itinerary"]["days"][1]
    after_n = len([it for it in d2a["items"] if it["type"] == "poi"])
    assert after_n < before_n or d2a["load"]["hours"] < before_h, \
        f"减载未生效：{before_n}→{after_n} 点，{before_h}→{d2a['load']['hours']}h"
    assert any(e["stage"] == "revise" for e in body["timeline"]), "事件流须含 revise 分组（第二幕）"
    assert any(e["type"] == "start" and e["stage"] == "revise" for e in body["timeline"])


def test_revise_unparseable_keeps_plan():
    p = client.post("/api/plan", json={"days": 2, "budget": 2500, "tags": ["亲子"]}).json()
    pid = p["plan_id"]
    r = client.post("/api/revise", json={"plan_id": pid, "message": "随便改改"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["itinerary"]["days"]) == 2, "无法解析时行程不得被破坏"
    assert body["message"], "须有友好提示"


def test_revise_remove_poi_by_name():
    p = client.post("/api/plan", json={"days": 3, "budget": 3000, "tags": ["美食", "文化"]}).json()
    pid = p["plan_id"]
    r = client.post("/api/revise", json={"plan_id": pid, "message": "第一天换掉文殊院"})
    assert r.status_code == 200
    d1 = r.json()["itinerary"]["days"][0]
    names = [it["name"] for it in d1["items"] if it["type"] == "poi"]
    assert all("文殊院" not in n for n in names), f"文殊院应被移除：{names}"


def test_geo_dual_city_projection_range():
    r = client.get("/api/geo")
    assert r.status_code == 200
    body = r.json()
    # 多城化后 geo 返回全部有快照的城市（仍为城市分组对象，不是数组），成渝必在
    assert set(body["points"].keys()) >= {"成都", "重庆", "昆明", "大理", "贵阳", "桂林"}
    for city, pts in body["points"].items():
        assert len(pts) > 0
        for p in pts:
            assert 0 <= p["x"] <= 1000 and 0 <= p["y"] <= 700, f"{p['id']} 坐标越界"
            for k in ("id", "name", "must_see", "slope", "crowd_level", "open_hour", "ticket", "tags"):
                assert k in p, f"{p['id']} 缺字段 {k}"


def test_geo_city_filter_keeps_shape():
    r = client.get("/api/geo", params={"city": "重庆"})
    body = r.json()
    assert list(body["points"].keys()) == ["重庆"]              # 外层结构不变
    assert body["cities"] == ["重庆"]


def test_meta():
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert set(body["cities"]) >= {"成都", "重庆"}
    assert "美食" in body["tags"]


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "蜀道智行" in r.text

# ─────────────────── 03G：自然语言抽取端点 + 天数上限放开 ───────────────────

def test_parse_endpoint_offline_rules():
    """POST /api/parse（离线规则实现）：返回只含契约 schema 字段。"""
    r = client.post("/api/parse", json={"text": "我在北京，想去成都和重庆玩3天，预算3000，喜欢美食和夜景"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"origin", "cities", "days", "budget", "tags",
                                "family", "source", "note"}, f"返回逸出契约 schema：{body.keys()}"
    assert body["source"] in ("rules", "llm", "fallback")
    assert body["origin"] == "北京" and body["days"] == 3 and body["budget"] == 3000
    assert body["cities"] == ["成都", "重庆"]


def test_parse_text_limits():
    r = client.post("/api/parse", json={"text": "长" * 5000})
    assert r.status_code == 422
    r = client.post("/api/parse", json={"text": ""})
    assert r.status_code == 422


def test_plan_days_up_to_30():
    """days le=7 → le=30：12 天请求合法进入管线（前端 max=7 同步放开）。"""
    r = client.post("/api/plan", json={"days": 12, "budget": 8000, "tags": ["文化"],
                                       "cities": ["成都", "重庆", "贵阳", "桂林", "昆明",
                                                  "大理", "乐山", "阆中", "安顺", "丽江"]})
    assert r.status_code == 200
    days = r.json()["itinerary"]["days"]
    assert len(days) >= 10, f"12 天请求应产出 ≥10 天，实际 {len(days)}"
    r = client.post("/api/plan", json={"days": 31})
    assert r.status_code == 422

# ─────────────────── 任务F：公网防护（输入上限 / IP限流 / 在线开关） ───────────────────

def test_input_length_limits_return_422():
    """超长输入返回 422 而非 500：message ≤500、tags ≤8 项且每项 ≤24 字、cities ≤16 项。"""
    p = client.post("/api/plan", json={"days": 1, "budget": 2000}).json()
    r = client.post("/api/revise", json={"plan_id": p["plan_id"], "message": "长" * 5000})
    assert r.status_code == 422, f"超长 message 应 422，实际 {r.status_code}"
    r = client.post("/api/plan", json={"days": 1, "budget": 2000,
                                       "tags": [f"标签{i}" for i in range(20)]})
    assert r.status_code == 422, f"tags 超项数应 422，实际 {r.status_code}"
    r = client.post("/api/plan", json={"days": 1, "budget": 2000, "tags": ["超" * 100]})
    assert r.status_code == 422, f"tags 项超长应 422，实际 {r.status_code}"
    r = client.post("/api/plan", json={"days": 1, "budget": 2000,
                                       "cities": [f"城市{i}" for i in range(20)]})
    assert r.status_code == 422, f"cities 超项数应 422，实际 {r.status_code}"


def test_rate_limit_429_online_not_offline(monkeypatch):
    """同 IP 高频：在线模式第 N+1 次起 429；离线模式不受限流（本地演示不被自己挡住）。

    run_pipeline 打桩为即时返回——本测只测限流判定，mock resolve_mode=online
    会让端点真跑 DeepSeek 在线管线（初版测试就这样烧了 27 秒真实调用）。
    """
    import server.app as app_mod
    from server.agent import llm as llm_mod

    def fast_pipeline(request, bus=None, on_event=None):
        return {"itinerary": {"days": [], "budget": {}}, "timeline": [],
                "mode": "online", "budget": {}}

    monkeypatch.setattr(app_mod, "run_pipeline", fast_pipeline)
    monkeypatch.setattr(llm_mod, "resolve_mode", lambda: "online")
    app_mod._rate_hits.clear()
    try:
        codes = [client.post("/api/plan", json={"days": 1, "budget": 2000}).status_code
                 for _ in range(8)]
        assert 429 in codes, f"在线模式高频应触发 429：{codes}"
        assert codes[:5] == [200] * 5, f"前 5 次（窗口上限）不应被限：{codes[:5]}"
    finally:
        app_mod._rate_hits.clear()

    monkeypatch.setattr(llm_mod, "resolve_mode", lambda: "offline")
    app_mod._rate_hits.clear()
    try:
        codes = [client.post("/api/plan", json={"days": 1, "budget": 2000}).status_code
                 for _ in range(8)]
        assert 429 not in codes, f"离线模式不应被限流：{codes}"
    finally:
        app_mod._rate_hits.clear()


def test_resolve_mode_allow_online_gate(monkeypatch):
    """SD_ALLOW_ONLINE 开关：auto+key 无开关 → offline；有开关 → online；
    显式 SD_LLM_MODE=online 是明确意图不受开关约束；无 key 时 online 仍报错。"""
    from server.agent import llm as llm_mod

    monkeypatch.setenv("SD_LLM_MODE", "auto")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("SD_ALLOW_ONLINE", raising=False)
    assert llm_mod.resolve_mode() == "offline", "auto+key 但无 SD_ALLOW_ONLINE 应回落 offline"
    monkeypatch.setenv("SD_ALLOW_ONLINE", "1")
    assert llm_mod.resolve_mode() == "online", "auto+key+SD_ALLOW_ONLINE=1 应在线"
    monkeypatch.setenv("SD_ALLOW_ONLINE", "0")
    assert llm_mod.resolve_mode() == "offline", "SD_ALLOW_ONLINE=0 等价于未开"
    monkeypatch.setenv("SD_LLM_MODE", "online")
    monkeypatch.setenv("SD_ALLOW_ONLINE", "0")
    assert llm_mod.resolve_mode() == "online", "显式 online 是明确意图，不受开关约束"
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    try:
        llm_mod.resolve_mode()
        assert False, "online 无 key 应抛 RuntimeError"
    except RuntimeError:
        pass
