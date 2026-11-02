"""蜀道智行 FastAPI 应用：API 服务 + SSE 事件流 + 对话式改行程。

契约与 static/js/api.js 的 LiveApi 严格对齐（前端零改动切换）：
  GET  /api/health   → {status, mode, llm}
  POST /api/plan     → {plan_id, itinerary, timeline, mode, budget}
  POST /api/stream   → SSE 逐条事件，倒数第二帧 {"type":"plan_result", plan_id, itinerary,
                        budget, mode}（行程随流返回），最后 {"type":"done"}
  POST /api/revise   → {itinerary, timeline, revised_day, message}
  GET  /api/geo      → {points: {城市: [...]}, cities: [...]}（分城投影）
  GET  /api/meta     → {cities, tags, meta}
  GET  /             → static/index.html（零构建前端）
断网保命：SD_LLM_MODE=offline 默认完整可用；在线分支失败一律降级不报错。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from .agent import TripRequest, run_pipeline
from .agent import llm as llm_mod
from .agent.events import EventBus
from .agent.pipeline import _load_dotenv
from .agent.revise import revise_plan
from .tools import obs
from .tools.geo import Projector
from .tools.poi_search import _ensure_aliases, _load_meta, load_pois

# 服务启动即加载 .env（run_pipeline 内也会再 load 一次，setdefault 幂等）——
# 否则 /api/health 的 resolve_mode() 在首次规划前读不到 key，徽标谎报「引擎离线」
# 而实际规划走在线（如实标注原则：徽标必须与真实模式一致）
_load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="蜀道智行 API", version="1.0.0")

# ── 计划缓存：plan_id → {itinerary, timeline, request, bus} ──
# FIFO 淘汰（上限 50），防内存泄漏；只为「改行程」拿原计划，不是用户系统
_PLANS: dict[str, dict] = {}
_PLAN_CAP = 50


class PlanRequest(BaseModel):
    """输入长度上限（任务F）：公网开放后 tags/cities 无限堆与超长串都会打到管线。"""
    days: int = Field(3, ge=1, le=7)
    budget: int = Field(3000, ge=500)
    tags: list[Annotated[str, StringConstraints(max_length=24)]] = Field(
        default_factory=list, max_length=8)
    family: bool = False
    cities: list[Annotated[str, StringConstraints(max_length=16)]] = Field(
        default_factory=list, max_length=16)   # 空 = 按候选池总分自动选城


class ReviseRequest(BaseModel):
    plan_id: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=500)


# ── IP 限流（任务F）：滑动窗口计数，标准库实现，零新依赖 ──
# 仅在线模式限流（离线跑管线不烧钱，本地演示/答辩断网不能被自己的限流挡住）；
# 进程内 dict 在多 worker 下是 per-worker 的——配合单 worker 部署口径（README 部署章节）
_RATE_WINDOW = 1.0      # 秒
_RATE_MAX = 5           # 每 IP 每窗口内最多 5 次规划类调用
_rate_hits: dict[str, list[float]] = {}


def _rate_limited(ip: str) -> bool:
    if llm_mod.resolve_mode() != "online":
        return False
    now = time.monotonic()
    if len(_rate_hits) > 10000:     # 防字典膨胀：异常多 IP 时整体重置（宁松勿崩）
        _rate_hits.clear()
    hits = [t for t in _rate_hits.get(ip, []) if now - t < _RATE_WINDOW]
    hits.append(now)
    _rate_hits[ip] = hits
    return len(hits) > _RATE_MAX


async def _rate_guard(request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=429,
                            detail="请求过于频繁（每秒限 5 次），请稍后再试")


def _to_trip(req: PlanRequest) -> TripRequest:
    return TripRequest(days=req.days, budget=req.budget, tags=req.tags,
                       family=req.family, cities=req.cities)


def _cache_plan(req: PlanRequest, result: dict, bus: EventBus) -> str:
    plan_id = uuid.uuid4().hex[:12]
    _PLANS[plan_id] = {
        "itinerary": result["itinerary"],
        "timeline": result["timeline"],
        "request": _to_trip(req),
        "bus": bus,
    }
    while len(_PLANS) > _PLAN_CAP:              # FIFO 淘汰最旧
        _PLANS.pop(next(iter(_PLANS)))
    return plan_id


@lru_cache(maxsize=1)
def _build_geo(city: str | None = None) -> dict:
    """分城投影：每城各建一个 Projector，坐标口径与 static/demo-geo.json 完全一致。

    城市集合 = 当前有 POI 快照的城市（meta 顺序），前端按行程涉及城市动态渲染图幅。
    city_meta 为每城图幅注记行（如 "CHENGDU · 30.67°N 104.07°E"）。
    """

    meta = _load_meta()
    lines = {c: v["line"] for c, v in meta["city_info"].items()}
    poi_cities = {p["city"] for p in load_pois()}
    order = [c for c in meta["cities"] if c in poi_cities]
    out = {}
    for c in order:
        if city and c != city:
            continue
        pois = [p for p in load_pois() if p["city"] == c]
        pr = Projector(pois)
        out[c] = [
            {**{k: p[k] for k in ("id", "name", "city", "lat", "lng", "tags", "ticket",
                                  "open_hour", "slope", "crowd_level", "family", "must_see",
                                  "night_friendly", "summary")},
             **dict(zip(("x", "y"), pr.project(p["lat"], p["lng"])))}
            for p in pois
        ]
    return {"points": out, "cities": list(out.keys()),
            "city_meta": {c: lines.get(c, c) for c in out}}


# ── 基础端点 ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    mode = llm_mod.resolve_mode()
    return {"status": "ok", "mode": mode, "llm": mode == "online"}


@app.post("/api/plan", dependencies=[Depends(_rate_guard)])
async def plan(req: PlanRequest):
    """同步跑完三段式管线，返回完整行程 + 事件流。

    asyncio.to_thread（任务 B）：在线模式下 run_pipeline → llm.chat 是阻塞 HTTP，
    async def 里直接同步调用会卡住整个事件循环（一次请求最长占住 30 秒、其他请求全排队）；
    线程池执行与 /api/stream 同款语义。
    """
    bus = EventBus()
    result = await asyncio.to_thread(run_pipeline, _to_trip(req), bus)
    plan_id = _cache_plan(req, result, bus)
    return {"plan_id": plan_id, **result}


@app.post("/api/stream", dependencies=[Depends(_rate_guard)])
async def stream(req: PlanRequest, request: Request):
    """SSE 流式：管线在线程池跑，emit 回调实时推事件。

    结束前推 plan_result 控制帧（行程随流返回）再发 done 哨兵（任务 A 方案 B）——
    前端一次「开始规划」只调本端点：在线模式下省一半 token，且行程与事件流必然同源
    （旧路径 plan + stream 各跑一次独立管线，temperature 0.3 非确定性下行程卡与事件流
    描述的是两个不同的行程）。plan_id 随流缓存，/api/revise 依赖它。
    """
    q: asyncio.Queue = asyncio.Queue()

    def on_event(ev: dict):
        q.put_nowait(ev)

    def run_and_signal():
        bus = EventBus(on_emit=on_event)
        result = run_pipeline(_to_trip(req), bus)
        plan_id = _cache_plan(req, result, bus)
        q.put_nowait({"type": "plan_result", "plan_id": plan_id,
                      "itinerary": result["itinerary"], "budget": result["budget"],
                      "mode": result["mode"]})
        q.put_nowait({"type": "stream_end"})   # 流结束哨兵：与业务 done 事件（narrate/system）区分

    asyncio.get_running_loop().run_in_executor(None, run_and_signal)

    async def gen():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break                  # 客户端断连：停止推流（线程自然跑完，结果丢弃）
                    continue
                if ev.get("type") == "stream_end":
                    # 转换为前端契约的最终信号；业务事件里的 done（阶段事件）原样透传
                    yield 'data: {"type": "done"}\n\n'
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)         # 让出事件循环，防背压
        finally:
            pass

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/revise", dependencies=[Depends(_rate_guard)])
async def revise(req: ReviseRequest):
    """对话式改行程：纯规则意图解析（离线可用），只重排目标天并复查。"""
    entry = _PLANS.get(req.plan_id)
    if not entry:
        return JSONResponse({"error": "plan_id 不存在或已过期"}, status_code=404)
    result = revise_plan(entry, req.message)
    entry["itinerary"] = result["itinerary"]   # 缓存更新为新行程（可继续 revise）
    entry["timeline"] = result["timeline"]
    return {**result, "budget": result["itinerary"].get("budget")}


@app.get("/api/geo")
async def geo(plan_id: str | None = None, city: str | None = None):
    """plan_id 兼容参数（当前投影与具体计划无关，全局快照）；city 为空返回全部分城分组。"""
    return _build_geo(city)


@app.get("/api/plan/{plan_id}/geo")
async def geo_alias(plan_id: str, city: str | None = None):
    """别名端点（/api/geo 的同构包装）。"""
    return _build_geo(city)


@app.get("/api/meta")
async def meta():
    pois = load_pois()
    return {
        "cities": sorted({p["city"] for p in pois}),
        "tags": sorted(_ensure_aliases().keys()),
        "meta": {"source": "local-snapshot", "count": len(pois)},
    }


@app.post("/api/plan/{plan_id}/save")
async def save_plan(plan_id: str):
    """OBS 可选接入：把缓存的行程 JSON 上传华为云 OBS，结果进事件流。"""
    entry = _PLANS.get(plan_id)
    if not entry:
        return JSONResponse({"error": "plan_id 不存在或已过期"}, status_code=404)
    bus: EventBus = entry["bus"]
    bus.emit("system", "tool_call", "obs.save_plan(...)",
             reason="华为云 OBS 可选接入：持久化行程 JSON")
    result = obs.save_plan(json.dumps(entry["itinerary"], ensure_ascii=False), plan_id)
    bus.emit("system", "tool_result",
             "OBS 上传成功" if result.get("ok") else "OBS 未启用/失败（已跳过）",
             reason=str(result.get("reason") or result.get("url") or "OBS_ENABLED"), detail=result)
    entry["timeline"] = bus.timeline()
    return result


# ── 静态前端（零构建：原生单页 + demo 资产，Live/Mock 同源）──
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="front")
