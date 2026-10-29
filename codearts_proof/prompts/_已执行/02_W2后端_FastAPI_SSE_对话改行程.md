# 码道 Prompt 02 · W2 后端：FastAPI + SSE + 对话式改行程

> 用法：整段粘贴给码道（IDE 模式）。
> **前置：Prompt 01（缺陷已修）已完成；Prompt 03（前端）已完成 —— 前端已把接口契约固化在 `static/js/api.js`，本条必须严格对齐它。**
> 执行完成后，把这段对话与码道的生成过程截图存进 `codearts_proof/`。

---

## ⚠️ 契约来源：以前端已实现的适配层为准

前端（Prompt 03）已经先行完成，并把这 6 个方法的**签名与返回结构**固化在 `static/js/api.js`：

```js
api.health()                                   // → {status, mode, llm}
api.plan({days, budget, tags, family})         // → {plan_id, itinerary, timeline, mode, budget}
api.stream(req, onEvent)                       // → 逐条回调 {seq,stage,type,title,reason,detail}，最后 {type:"done"}
api.revise(plan_id, message)                   // → {itinerary, timeline, revised_day, message}
api.geo(plan_id, city)                         // → {points:[{id,name,city,lat,lng,x,y}], cities:[...]}
api.meta()                                     // → {cities:[...], tags:[...], meta:{...}}
```

**动手前请先读 `static/js/api.js`**，后端的实现必须让前端的 `LiveApi` **无需任何改动**就能工作。
前端另有一个 `MockApi`（用 `static/demo*.json` 本地回放），它与真实后端**同构**——
你写完后，前端切到真实后端时必须行为一致（同样的事件顺序、同样的字段、同样的 `done` 收尾）。

前端还已经生成了这些**真实产物**，后端请复用而不是重造：
`static/demo.json`、`static/demo-revised.json`、`static/demo-geo.json`（后者含成渝**分城**的投影坐标 `x/y`）。

---

## 背景

项目根目录：`D:\项目代码\shudao-agent`

已有能力（**不要重写，只做包装与扩展**）：

| 模块 | 职责 |
|---|---|
| `server/agent/pipeline.py` | `run_pipeline(request, bus)` → `{itinerary, timeline, mode, budget}` |
| `server/agent/events.py` | `EventBus.emit(stage, type, title, reason, **detail)`，事件字段 `{seq, stage, type, title, reason, detail}` |
| `server/agent/planner.py` | `offline_plan` / `llm_plan` / `fix` / `POI_INDEX` / `CITY_HUB` / `_pick_day_pois` / `_build_timeline` |
| `server/agent/validator.py` | `validate(plan, request)` → violations 列表 |
| `server/agent/narrator.py` | `narrate(plan, bus, mode)` |
| `server/tools/` | `poi_search` / `route` / `leg_time` / `weather` / `budget` / `haversine` / `Projector` |

`EventBus` 的每个事件都带 `reason`，这正是前端"可倒带时间轴"的数据源——**本 prompt 的核心不是"做个 API"，而是"把决策过程变成可回放的数据流"**。

---

## 硬约束（不可违反）

1. **断网保命**：所有接口在**无外网、无 `DEEPSEEK_API_KEY`** 的情况下必须完整可用。`SD_LLM_MODE=offline` 是默认演示模式。在线分支只能作为可选增强，且**任何外部依赖失败都必须降级而不是报错**（参考现有 `llm_plan` 的 try/except 降级写法）。
2. **零构建前端**：后端只提供 API 与静态文件，不引入 Vue/React/npm 构建链。前端由 Prompt 03 负责，是原生单页。
3. **不加第三方依赖**：`requirements.txt` 现有 `fastapi / uvicorn / pydantic / openai / pytest` 已够用。若确需新依赖，先说明理由。
4. **确定性**：相同请求必须产出**完全相同**的行程（贪心算法本身是确定性的，不要引入随机数、字典序不稳定排序、或依赖当前时间做决策）。视频录制和答辩现场复现都依赖这一点。

---

## 交付物

### A. `server/app.py` — FastAPI 应用

#### 数据模型（pydantic）

```python
class PlanRequest(BaseModel):
    days: int = Field(3, ge=1, le=7)
    budget: int = Field(3000, ge=500)
    tags: list[str] = Field(default_factory=list)
    family: bool = False
```

#### 端点

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 返回 `{"status":"ok","mode":<当前模式>,"llm":bool}`；前端启动自检用 |
| POST | `/api/plan` | body = PlanRequest → **同步**跑完管线，返回 `{"plan_id": "...", "itinerary": {...}, "timeline": [...], "mode": "...", "budget": {...}}` |
| POST | `/api/stream` | body = PlanRequest → **SSE 流式**返回事件，见下 |
| POST | `/api/revise` | body = `{"plan_id": "...", "message": "第二天太赶"}` → 对话式改行程 |
| GET | `/api/geo` | query = `plan_id`、`city`（可空）→ 见下方 geo 契约 |
| GET | `/api/meta` | 返回 POI 快照的元信息（`meta` 字段 + 城市列表 + 标签词表 `TAG_ALIASES` 的键），给前端做筛选控件 |
| GET | `/` | 返回 `static/index.html`（前端由 Prompt 03 交付，放在 `static/`） |

> ⚠️ **路由以前端已实现的 `static/js/api.js` 为准，不要改成 `/api/plan/{plan_id}/xxx` 这种带路径参数的写法。**
> 前端 `LiveApi` 里写死的就是上面这 6 个路径（`/api/health`、`/api/plan`、`/api/stream`、
> `/api/revise`、`/api/geo`、`/api/meta`）。`plan_id` 一律走 **body 或 query 参数**。
> 后端可以额外保留 `/api/plan/{plan_id}` 之类的别名，但**必须保证这 6 个路径可用**。

### geo 契约（**必须严格一致**）

前端 `CityMaps` 期望拿到 **按城市分组**的对象——它对 `Object.entries(geoData)` 逐城建图。
**返回一个扁平数组会让前端直接渲染不出东西。**

```jsonc
{
  "points": {                                  // ← 必须是「城市 → 点位数组」的对象，不是数组
    "成都": [{"id":"CD-01","name":"宽窄巷子","city":"成都","lat":30.66,"lng":104.06,
              "x":384.9,"y":312.5,"must_see":true,"night_friendly":true,
              "ticket":0,"open_hour":[0,24],"slope":0,"crowd_level":3,
              "family":4,"tags":["历史文化","美食"],"summary":"..."}],
    "重庆": [ /* 同构 */ ]
  },
  "cities": ["成都", "重庆"]
}
```

- **成渝必须分城投影**：成渝直线 250km，合投影会把成都的点挤成一团。
  每城各建一个 `Projector`（`server/tools/geo.py`），坐标与 `static/demo-geo.json` 的口径一致。
- `city` 参数可空：**为空时返回上面这个「双城分组」完整结构**（前端启动时 `api.geo(planId, null)` 就是这么调的）；
  指定城市时**只返回该城**，但**外层结构保持不变**（仍是 `{"points": {"成都": [...]}, "cities": ["成都"]}`）。
- 字段必须齐全——前端 `map.js` 会用 `must_see`、`slope`、`crowd_level`、`open_hour`、`ticket`、`name`、`tags`、`x`、`y`，
  `api.js` 的 `meta()` 会用 `tags`。**缺一个前端就少一个效果**。
- 建议直接复用 `scripts/export_demo_assets.py` 里的 `export_geo()` 逻辑，保证后端与 mock 数据口径完全一致。


#### SSE 端点的关键设计

- 响应头：`text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
- 事件格式：每条 `data: {json}\n\n`，json 就是 `Event.to_dict()` 的结果（`{seq, stage, type, title, reason, detail}`）。
- **不要**用 `StreamingResponse` 一次把整个结果吐完。真实需求是让前端看到"Agent 正在思考"的过程：管线在跑的时候就实时推事件。
  - 实现方式：给 `run_pipeline` 增加一个**可选的事件回调参数**（如 `on_event=None`），在 `EventBus.emit` 内部触发；**不要**改 `EventBus` 的现有 `emit` 签名语义，保证 `cli.py` 与现有测试不受影响。
  - 推事件时用 `asyncio.to_thread` / `run_in_executor` 把同步管线放到线程池，避免阻塞事件循环。
- 推完最后一个事件后发送一条 `data: {"type":"done", ...}`，然后关闭流。
- 客户端断连要能干净地终止后台线程（用 `await request.is_disconnected()` 轮询或 `asyncio.CancelledError` 处理）。

#### 计划缓存

- `plan_id` 用 `uuid4().hex[:12]`。
- 用一个模块级 `dict` 缓存 `plan_id → {itinerary, timeline, request, bus}`，容量上限（如 50 条）做 LRU/FIFO 淘汰，防止内存泄漏。
- 缓存是为了「改行程」能拿到原计划，**不是**为了做用户系统——不要加数据库、不要加登录。

### B. 对话式改行程（`/revise`）

这是最能体现 Agent 能力的交互，务必实现且**离线可用**。

#### 离线实现（必须）

1. **意图解析**（纯规则，不依赖 LLM）：从用户消息里抽取
   - 目标天：`第N天` / `第二天` / `day N` → 解析成天序号（中文数字 1–7 要能识别）
   - 意图类型：
     - `太赶/太满/太累/太紧` → **减载**
     - `太松/太闲/加一个/加个` → **加长**
     - `换掉X` / `去掉X` / `不想去X` → **移除某点**（X 按 POI 名称模糊匹配）
     - `先去X` / `把X放前面` → **重排顺序**（X 按名称模糊匹配）
2. **重排执行**：只对**目标天**重跑，复用 `planner` 里的既有函数，不要另写一套装箱逻辑：
   - 减载：把该天容量收紧（如 ×0.8）后用 `_pick_day_pois` 重选，再 `_build_timeline` 重建时间线、`_day_load` 重算负载
   - 加长：容量放宽（如 ×1.15）后同上
   - 移除/重排：直接改该天的 POI 列表，再 `_build_timeline` 重建
   - 改完必须调 `validator.validate` 复查；若引入新违规，用现有 `planner.fix` 定向修复
3. **必须追加事件**（这是"可倒带"的第二幕，前端要能看到用户介入）：
   - `stage="revise"`, `type="start"`：用户说了什么
   - `stage="revise"`, `type="decision"`：为什么这么改（例如"因为你说第二天太赶，把当天容量收紧到 7.4h，移除 磁器口"）
   - `stage="revise"`, `type="tool_call"` / `"tool_result"`：调用了哪个内部能力
   - `stage="revise"`, `type="done"`：改完后该天点数/时长/强度
   - `stage="validate"`, `type="pass"` 或 `"violation"`：复查结果
4. 返回 `{"itinerary": <更新后的完整行程>, "timeline": <含新事件的完整时间线>, "revised_day": N, "message": "<一句中文回复>"}`

#### 在线实现（可选增强）

- 若 `SD_LLM_MODE=online` 且有 key：把该天的点位清单（id/name/open_hour/visit_hours 等）发给 LLM，要求**只返回新的点位 id 顺序 JSON**，不要让 LLM 编时间；时间线由本地 `_build_timeline` 重算。
- LLM 失败 → 自动回落到离线规则实现，并在事件流里发 `revise/fallback`。

#### 兜底

- 消息无法解析出意图时，**不要报错**：返回原行程 + 一条友好提示事件（如"没听懂是第几天想改，请说明例如『第二天太赶』"）。

### C. 华为云可选接入（评分项「是否结合华为云其他服务提升能力」）

**必须做成可选、且不影响主流程**——配了才用，没配就跳过。

1. **OBS（对象存储）**：新增 `server/tools/obs.py`
   - 环境变量 `OBS_ENDPOINT` / `OBS_BUCKET` / `OBS_AK` / `OBS_SK`
   - 4 个变量齐全才启用；未启用时 `save_plan()` 返回 `{"enabled": false, "reason": "未配置 OBS 环境变量，已跳过"}`
   - 启用时把 plan JSON 上传，返回可访问 URL
   - **不引入 `esdk-obs-python` 等新依赖**：用 `requests`/`httpx` 也需要新依赖，所以——**优先用标准库 `urllib.request` + S3 兼容签名**；如果实现签名过于复杂，允许改为「只实现上传接口的最小可用版本」并在 readme 里说明，或使用 `requests`（若可接受新增依赖，必须先说明理由并加入 `requirements.txt`）
   - 新增端点 `POST /api/plan/{plan_id}/save` → 触发保存并把结果放进事件流
2. **FunctionGraph（函数计算）**：`server/tools/weather.py` 已有 `_lookup` 预留注释
   - 改造为：若环境变量 `FG_WEATHER_URL` 存在 → 用标准库 `urllib.request` POST 到该 URL 取天气；超时（≤2s）或失败 → **静默回落到本地快照**
   - 不得让天气服务拖慢或打断整条管线
3. 每次华为云调用成功/失败都要发事件（`tool_call` / `tool_result`），让评委在时间轴上直接看到"这里接了华为云"。

---

## 交付要求

1. 新增测试文件 `tests/test_api.py`（用 `fastapi.testclient.TestClient`，**不启真实端口**）：
   - `/api/health` 返回 200 且含 `status`
   - `/api/plan` 返回合法行程 JSON，天数 == 请求天数
   - **同样请求两次，返回的 `itinerary` 完全一致**（确定性断言）
   - SSE 流能收到 `data: ` 开头的行，且**最后一条是 done**
   - `/revise` 传 `"第二天太赶"` → 行程里第 2 天点数减少 或 时长减少，且事件流里出现 `stage=="revise"` 的事件
   - `/revise` 传 `"随便改改"`（无法解析）→ 返回 200 且行程未被破坏
   - `/api/plan/{id}/geo` 返回的 x/y 全部落在 0–1000 / 0–700 内
2. 全量 `python -m pytest -q` 必须全绿。
3. 提供 `scripts/start_server.sh`（Linux/macOS）与 `scripts/start_server.bat`（Windows），内容：创建/激活 venv → 安装依赖 → 启动 `uvicorn server.app:app --host 0.0.0.0 --port 8000`。
4. 贴出一次 `/api/plan` 与 `/revise` 的**真实请求/响应示例**作为验收证据。
5. 代码注释与 docstring 用中文，风格与 `server/agent/` 现有文件保持一致。
6. 不要修改 `server/data/pois.json`、不要修改 `cli.py` 的既有参数语义、不要删除任何现有测试。
