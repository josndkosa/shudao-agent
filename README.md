# 蜀道智行 · 三段式行程规划智能体

2026 华为开发者大赛·智能体创新赛（西南赛区）参赛作品。

输入天数/预算/偏好，三段式管线生成成渝行程，前端以 SVG 自绘路线图 + 可倒带时间轴呈现 Agent 决策过程。

## 架构

```
规划段 Planner   LLM Function Calling（在线）/ 贪心装箱（离线兜底）
  ↕ 违规回流修复（最多 3 轮）
校验段 Validator 纯规则引擎：V1时长 / V2开放窗口 / V3强度 / V4预算 / V5亲子
  ↓
叙事段 Narrator  LLM 导览词（在线）/ 模板兜底
```

- 全程事件流 `EventBus`：每个决策带 `reason`，前端渲染**可倒带时间轴**，回放"为什么第二天排这三个点"
- 数据为**本地快照**（40 个 POI 厚字段：开放时间/预约难度/人流时段/爬坡强度/亲子友好度），保证断网演示稳定，数据层可对接 OTA 开放接口
- LLM 模式开关 `SD_LLM_MODE=auto|offline|online`，断网自动降级规则引擎

## 快速开始

```bash
pip install -r requirements.txt   # CLI 仅用标准库，可不装依赖直接跑
python cli.py --days 3 --budget 3000 --tags 美食,文化
python cli.py --days 2 --budget 2500 --tags 亲子,遛娃 --family
python cli.py --days 3 --json > plan.json    # 供前端联调
SD_LLM_MODE=online python cli.py ...         # 接入 DeepSeek FC（需 .env 配 key）
```

## Web 服务（前端 + API + SSE + 对话改行程）

```bash
scripts/start_server.bat                      # Windows（或 .sh）：venv + 依赖 + uvicorn 8000
# 浏览器打开 http://127.0.0.1:8000/?auto=1   # 后端在场走真实接口；不在场自动切本地演示数据
```

API 契约（与 `static/js/api.js` 的 LiveApi 严格对齐）：
`GET /api/health` · `POST /api/plan` · `POST /api/stream`（SSE）· `POST /api/revise` · `GET /api/geo` · `GET /api/meta`

可选华为云接入（配置才启用，未配置自动跳过）：
- OBS：`OBS_ENDPOINT/OBS_BUCKET/OBS_AK/OBS_SK`（可选 `OBS_REGION`）→ `POST /api/plan/{id}/save`
- FunctionGraph 天气：`FG_WEATHER_URL`（2s 超时静默回落本地快照）

## 测试

```bash
pytest -q
```

## 目录

```
cli.py                 命令行入口（答辩保命形态）
server/
  app.py               FastAPI：六端点 + SSE 流式 + 对话改行程 + 静态托管
  agent/
    pipeline.py        三段式编排（on_event 回调供 SSE 推流）
    planner.py         规划段（LLM FC + 离线贪心 + 修复）
    validator.py       校验段（纯规则引擎，软硬分级）
    narrator.py        叙事段
    revise.py          对话式改行程（规则意图解析 + 定向重排）
    llm.py             DeepSeek 客户端 + 模式开关
    events.py          事件流（可倒带时间轴数据源）
  tools/               poi_search / route / weather / budget / geo / obs
  data/pois.json       40 点本地快照（厚字段）
static/                零构建前端（原生单页 + demo 资产 + api/map/timeline/player/main）
scripts/               export_demo_assets.py / start_server.{sh,bat}
tests/                 pytest 覆盖工具、校验规则、全管线、API 契约
```

## 环境变量

见 `.env.example`。`DEEPSEEK_API_KEY` 配置后 `auto` 模式自动走在线 FC。