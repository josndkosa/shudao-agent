# API 契约

> 契约以 `static/js/api.js` 的 LiveApi 实现为准（后端严格对齐，前端零改动切换）。
> 实现见 `server/app.py`；测试见 `tests/test_api.py`（TestClient，11 用例）。

## 六端点速览

| 方法 | 路径 | 作用 | 返回 |
|---|---|---|---|
| GET | `/api/health` | 启动自检（前端 2s 探测选 Live/Mock） | `{status, mode, llm}` |
| POST | `/api/parse` | **自然语言 → 结构化参数**（03G 抽取层，抽取与规划分离） | `{origin, cities, days, budget, tags, family, source, note}` |
| POST | `/api/plan` | 同步跑完管线 | `{plan_id, itinerary, timeline, mode, budget}` |
| POST | `/api/stream` | SSE 流式推事件 | `data: {...}\n\n` 逐条 + plan_result 帧 + done 哨兵 |
| POST | `/api/revise` | 对话式改行程 | `{itinerary, timeline, revised_day, message, budget}` |
| GET | `/api/geo` | 分城投影坐标 | `{points: {城市: [...]}, cities: [...]}` |
| GET | `/api/meta` | 快照元信息 | `{cities, tags, meta}` |

另有：`GET /`（静态前端）、`POST /api/plan/{plan_id}/save`（OBS 可选）、`GET /api/plan/{plan_id}/geo`（别名）。

## /api/parse 契约（03G：自然语言规划入口）

```bash
curl -X POST http://localhost:8000/api/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "我在北京，想去成都和重庆玩3天，预算3000，喜欢美食和夜景"}'
# → {"origin": "北京", "cities": ["成都", "重庆"], "days": 3, "budget": 3000,
#    "tags": ["美食", "夜景"], "family": false, "source": "rules", "note": "出发地 北京 仅作展示，…"}
```

- **`source`**：`"llm"`（在线 DeepSeek 纯 JSON 抽取） | `"rules"`（离线正则+词表，断网可用） |
  `"fallback"`（完全没解析出来）——两种实现返回**完全同构**，前端零分叉
- **校验与归一在抽取层完成**（模型自造语义在此拦死）：城市只认 `meta.city_info`
  （不认识的城市过滤并在 `note` 如实提示）；标签必须落 `expand_tags()` 受控词表；
  天数 clamp 1–30、预算 clamp ≥500
- **`origin`（出发地）只抽取不计算**：note 与前端均如实标注「暂未计入行程时间与交通费」
- LLM 返回非法 JSON / 调用失败 → 自动降级规则实现，**任何情况不抛错**
- 前端语义：无 plan_id 时对话栏发送 = 抽取 → 回填参数条（回填不替换，未识别字段保留
  原值）→ 自动触发规划；有 plan_id = 走 `/api/revise`（改行程语义零变化）

### /api/parse 契约扩展（03J：显式偏好记忆）

返回新增 `remember` / `forget` / `view`（bool，互斥）+ `prefs`（当前画像）+ `timeline`
（本次调用的事件流）。记忆操作**纯规则实现，不依赖 LLM**（离线在线都能用）：

| 用户说 | 返回 | 效果 |
|---|---|---|
| 「记住：我带娃，不去博物馆」 | `remember=true, prefs={family, avoid_tags:[博物馆]}` | 增量写入画像 + timeline 含「已记住偏好」事件 |
| 「记住：预算两千」 | `remember=true, prefs={budget:2000}` | 中文金额口语可识别（一万五=15000） |
| 「记住：我不吃辣」 | `remember=true, note=「数据维度还不支持…」` | **如实拒绝**，画像零污染 |
| 「忘掉我的偏好」/「忘掉博物馆」 | `forget=true` | 全清 / 只删指定项 |
| 「我记住了什么」 | `view=true, note=画像列表` | 用户可见我们替他记了什么 |
| 正常规划语句（有画像时） | `budget/family/tags` 含记忆合并值 + note「已按上次的偏好：…」 | 显式优先：这次说了预算五千就用五千 |

**生效路径**（服务端权威点）：`run_pipeline` 入口读画像 → `merge_prefs` 合并进
TripRequest → timeline 含「应用偏好记忆」事件（reason 写明记住了什么 + 上次记录时间）。
`avoid_tags` 为**候选筛选阶段的硬排除**（poi_search 之后、打分装箱之前），不触碰
V1–V5 判定；在线路径在 exec_tool 源头过滤 + 归一化层兜底。

**隐私**：画像存于**用户主目录** `~/.shudao/preferences.json`（`SD_PREFERENCES_PATH`
可覆盖）——不进仓库、不进提交包（`server/data/` 会被打进 zip 分发给评委，用户数据
绝不能放那）。文件损坏/目录不可写 → 静默降级为无记忆，绝不影响主流程。

## 请求示例

```bash
# plan：天数/预算/偏好标签/亲子/城市（PlanRequest 校验 days 1-7、budget ≥ 500）
# cities 可选：空数组=按候选池总分自动选 N 城（N=days）；显式指定时未收录城市剔除并如实发 fallback 事件
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{"days": 3, "budget": 3000, "tags": ["美食", "文化"], "family": false, "cities": ["成都", "重庆"]}'

# revise：plan_id 来自 plan 响应
curl -X POST http://localhost:8000/api/revise \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "97b1422c20ac", "message": "第二天太赶"}'

# geo：city 可空——空=全部有快照城市分组；指定=单城但外层结构不变
curl "http://localhost:8000/api/geo?city=重庆"
```

## 多城契约补充（03E 批次1）

- **`POST /api/plan` 请求**新增可选字段 `cities: string[]`：
  - `[]`（缺省）= 按候选池总分自动选城（N = min(days, 可用城市数)），事件流含「自动选城」decision（reason 带各城总分）
  - 显式列表 = 按给定顺序分天；未收录城市剔除并发 `fallback` 事件；`days < len(cities)` 时取总分前 N 城各 1 天
  - 行程 `items` 中的城际条目：`{"type": "intercity", "label": "成渝高铁"（覆盖表）或 "A→B 列车"（自动生成）, "arrival", "departure"}`
- **`GET /api/geo`**：返回**全部有快照的城市**（当前 15 城）；新增 `city_meta` 字段：
  `{城市: "CHENGDU · 30.67°N 104.07°E"}`（图幅注记行，前端动态图幅用）
- **`GET /api/meta`**：`cities` 为 15 城全量（批次1–3 全部落地，合计 237 点）；
  `meta.count` 为 POI 总数（首页统计卡的数据源）；`city_info.terrain` 契约：
  `{type: plain|basin|hill|karst|plateau|alpine|tropical, intensity_cap: 6.0–8.5, alt_m}`——
  V3 强度阈值按城市取 `intensity_cap`（无配置回落默认 8.5）

## 响应示例（真实运行产物）

```jsonc
// POST /api/plan → 200
{
  "plan_id": "97b1422c20ac",
  "mode": "offline",                // offline | online（LLM 开关）
  "itinerary": {
    "days": [
      {
        "day": 1, "city": "成都",
        "weather": {"day": "多云", "temp": [10, 17], "source": "local-snapshot"},
        "items": [
          {"type": "poi", "poi_id": "CD-09", "name": "文殊院",
           "arrival": "08:32", "departure": "10:02",
           "visit_hours": 1.5, "leg_hours": 0.04, "ticket": 0,
           "tags": [...], "reasons": ["标签命中[...]"], "summary": "..."},
          {"type": "meal", "label": "午餐", "arrival": "12:00", "departure": "13:00"}
        ],
        "load": {"hours": 13.35, "intensity": 5.8, "tickets": 120},
        "narrative": "第1天·成都：……"
      }
    ],
    "budget": {"tickets": 190, "meals": 360, "transit": 259, "total": 809, "per_day": 269.7}
  },
  "timeline": [                     // ← 可倒带时间轴的全部素材（见下节帧格式）
    {"seq": 1, "stage": "system", "type": "start", "title": "蜀道智行·三段式管线启动",
     "reason": "LLM 模式 offline…", "detail": {"mode": "offline"}},
    ...
  ]
}
```

```jsonc
// POST /api/revise "第二天太赶" → 200
{
  "revised_day": 2,
  "message": "已调整第2天：5 → 4 个点，负载 9.44h",
  "itinerary": { ... },             // 更新后的完整行程
  "timeline": [ ...原事件,           // 第二幕：revise 分组事件接在原时间线之后
    {"seq": 24, "stage": "revise", "type": "start",  "title": "用户介入：第二天太赶", ...},
    {"seq": 25, "stage": "revise", "type": "decision", "title": "第2天重排：5 → 4 个点", ...},
    {"seq": 26, "stage": "revise", "type": "tool_call", ...},
    {"seq": 27, "stage": "revise", "type": "tool_result", ...},
    {"seq": 32, "stage": "revise", "type": "done", ...}
  ],
  "budget": { ... }
}
```

无法解析意图时**不报错**：`revised_day: null` + 友好提示 message，行程原样返回。

## SSE 帧格式（POST /api/stream）

- 响应头：`Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`
- 每帧 `data: {json}\n\n`，json 即 `Event.to_dict()`（`seq/stage/type/title/reason/detail`）
- **plan_result 控制帧（03H 任务A）**：业务事件全部送达后、哨兵之前，推送
  `{"type": "plan_result", "plan_id", "itinerary", "budget", "mode"}`（纯 type 无 stage）——
  行程随流返回，前端一次「开始规划」只跑一次管线（在线模式省一半 token，
  行程与事件流必然同源）；`plan_id` 随流缓存，可直接喂 `/api/revise`
- **流结束哨兵**：最后一帧 `data: {"type": "done"}`（纯 type 无 stage——与业务
  narrate/system 的 done 事件区分；该哨兵是 prompt 02 修掉的真实 bug，测试已固化）
- 实现要点：管线跑在线程池（`run_in_executor`），`EventBus(on_emit)` 回调入
  `asyncio.Queue`；客户端断连（`request.is_disconnected()`）干净终止推送

## 事件 detail 字段的确切形状（03H 任务H5 补——消费端曾在此栽过 P0）

`EventBus.emit(stage, type, title, reason, **detail)` 的 kwargs 收集规则决定了形状：

| 调用方写法 | detail 形状 | 典型事件 |
|---|---|---|
| `emit(..., detail=X)` | **嵌套** `{"detail": X}` | 选点 decision（X=poi_id 数组）、violation/advisory（X=违规对象）、tool_result 的 detail 参数 |
| `emit(..., 具名键=值)` | **扁平** `{键: 值}` | fix（`{violation, removed}`）、tool_call（`{tool, args}`）、tool_result（`{count}`）、start（`{mode}`） |

**前端唯一解包入口是 `static/js/view.js` 的 `payload(ev)`**——它对嵌套形状自动解一层
内层 `detail`、扁平形状原样返回。任何新消费端一律 `import { payload }`，
不许自己读 `ev.detail`（P0 复核轮的教训：map.js 各读各的层级，路线从未渲染过）。

## 事件枚举（前端 TYPE_MARK 与后端 events.py 同源）

**stage 取值**：`plan` / `validate` / `narrate` / `revise` / `system`

**type 取值**：

| type | 图标 | 含义 |
|---|---|---|
| `start` | ▶ | 阶段开始 |
| `thought` | ◌ | 需求解析等思考事件 |
| `tool_call` | ⚙ | 工具调用（poi_search/route/weather/budget/obs） |
| `tool_result` | ✓ | 工具返回 |
| `decision` | ◆ | 关键决策（城市分天/逐日选点/revise 重排） |
| `violation` | ✗ | **硬**违规（进修复循环） |
| `advisory` | ⚠ | **软**提醒（V3 强度，不阻断不修复） |
| `fix` | ↻ | 修复动作（detail.removed 携带被移除 poi_id） |
| `pass` | ✔ | 一轮校验通过（只看 hard） |
| `unfixable` | ⊘ | 硬违规无自动修复策略，收敛检测停止重试 |
| `done` | ■ | 阶段/管线完成 |
| `fallback` | ▽ | 降级（LLM→离线、文案→模板、校验异常跳过） |

## geo 契约的三个关键点

1. **`points` 必须是「城市 → 点位数组」对象**（不是扁平数组）——前端 `CityMaps`
   对 `Object.entries` 逐城建图，扁平数组直接渲染不出
2. **成渝分城投影**：两城直线约 250km，合投影会把成都的点挤成一团——
   每城各建一个 `Projector`（`server/tools/geo.py`），坐标与 `static/demo-geo.json` 同口径
3. 字段齐全：前端要用 `must_see/slope/crowd_level/open_hour/ticket/name/tags/x/y`

## Mock 与真实后端同构的保证

- Mock 的 `stream()` 用 `setTimeout` 按 `seq` 顺序推同一份 timeline（350ms 间隔），
  **最后同样发 `{type:"done"}`** —— 帧格式/顺序/收尾三者同构
- Mock 的 `revise()` 切换 `demo-revised.json` 并把时间线接在原时间线后
  （`revise/start` 分组分隔），与真实 revise 的事件结构一致
- 前端唯一数据入口是 `api.js` 六方法；上层（map/timeline/player/main）
  **没有任何 `if (mock)` 分支**——两种模式界面与交互完全一致