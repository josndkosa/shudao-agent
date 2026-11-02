# 蜀道智行 · 提交 README

> 2026 华为开发者大赛·智能体创新赛（西南赛区）参赛作品提交说明。
> 本文件覆盖赛题 readme/ 要求的四条：环境依赖与一键安装 / 部署运行 / 开源组件 / 码道应用总结。

## 1. 环境依赖说明 + 一键安装

**运行环境**：Python ≥ 3.10（Windows / macOS / Linux 均可）；Node ≥ 18（仅前端冒烟脚本用，非运行必需）。

**核心依赖**（完整清单见 `project/docs/baseline/deps.md`，许可证逐包核对）：

| 包 | 版本 | 用途 |
|---|---|---|
| fastapi | 0.136.x | API 服务（SSE 流式） |
| uvicorn | 0.49.x | ASGI 服务器 |
| pydantic | 2.13.x | 请求模型校验 |
| openai | 2.38.x | **可选**：在线 LLM 规划（DeepSeek，OpenAI 兼容） |
| pytest | 9.x | 测试（dev） |

> CLI（`python cli.py`）与离线管线**仅用 Python 标准库**——零第三方依赖即可跑通完整规划。

**一键安装**：

```bash
# Linux / macOS
bash project/scripts/install.sh
# Windows
project\scripts\install.bat
# 或手动：python -m venv .venv && pip install -r requirements.txt
```

## 2. 部署运行步骤

### 本地一条命令

```bash
python scripts/ctl.py serve        # = uvicorn server.app:app --host 0.0.0.0 --port 8000
# 品牌首页 http://localhost:8000/ → 「进入工作台」
# 规划工作台 http://localhost:8000/plan.html?days=3&budget=3000&tags=美食,文化&auto=1
```

### 华为云 ECS 部署（答辩「上线」演示）

1. 购买/使用 ECS（可用华为开发者空间云主机），安全组**放行 8000 端口**入方向
2. 拉代码上云（CodeArts Repo 克隆或 scp zip 解包）
3. `bash scripts/install.sh`（建 venv + 装依赖）
4. `nohup python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 1 &`
   **必须单 worker**：`/api/revise` 依赖进程内计划缓存（`_PLANS` dict），多 worker 下
   plan 与 revise 落到不同进程会 404（「对话改行程」演示项当场失效）。这是刻意的
   架构取舍——单机演示场景下，跨进程存储带来的复杂度不值得
5. 冒烟验证：`curl http://localhost:8000/api/health` → `{"status":"ok","mode":"offline","llm":false}`
6. 公网访问 `http://<ECS公网IP>:8000/plan.html?auto=1`

### 公网防护（上线前必读）

公网开放后已内置三层防护（03H 任务F）：

- **在线模式默认关闭**：`SD_LLM_MODE` 为 auto 时，须显式设 `SD_ALLOW_ONLINE=1`
  才走 DeepSeek 在线规划——公网上别人用你的服务只会跑离线分支，**不烧你的 API 额度**。
  答辩现场要开在线：在 `.env` 里设 `SD_LLM_MODE=online`（明确意图，最高优先级）或
  `SD_ALLOW_ONLINE=1`
- **输入长度上限**：`message ≤ 500 字`、`tags ≤ 8 项`、`cities ≤ 16 项`，超限返回 422
- **IP 限流**：在线模式下每 IP 每秒 5 次规划类调用，超限 429（离线模式不限流，
  本地演示不受影响）

### 断网兜底（答辩保命）

后端未启动时前端自动切本地演示数据（顶部徽标如实标注「本地演示数据（后端未启动）」），
全部交互（含对话改行程）仍可演示——这是设计内行为，不是故障。

## 3. 额外使用的开源组件说明

| 组件 | 版本 | 许可证 | 用途 |
|---|---|---|---|
| FastAPI / Starlette / uvicorn | 见 deps.md | BSD-3 / BSD-3 / BSD-3 | API 服务 |
| pydantic (+pydantic-core) | 2.13.x | MIT | 模型校验 |
| openai-python | 2.38.x | Apache-2.0 | 在线 LLM 接入（可选） |
| pytest 及其依赖 | 9.x | MIT 等 | 测试 |

**郑重声明**：
- 前端**零框架、零构建工具、零 CDN 外链**（原生 HTML/CSS/ES Module，字体全系统本地栈）——
  断网答辩时页面 100% 自包含
- POI 数据为**本地快照**（西南 15 城 237 点，每城独立 JSON 文件，
  字段与来源说明见 `project/server/data/schema.md`；新增城市零代码改动——
  丢一个含 `city` 字段的 json 进 `server/data/` 即被自动收录），
  数据层可对接 OTA 开放接口（`server/cloud/` 已预留接入边界）
- 不使用任何外部地图服务（自研经纬度→SVG 投影，`server/tools/geo.py`）

## 4. 码道（AI Coding）在项目开发中的应用总结

### 4.1 覆盖度

本项目**全程由华为云码道开发**（约 17 轮任务单驱动），覆盖四类活动：

| 活动 | 证据（project/codearts_proof/） |
|---|---|
| 环境搭建 | 首轮任务单即含项目脚手架（CLI/管线/测试骨架） |
| 代码生成 | 全部 Python/JS/HTML/CSS 均为码道产出；`prompts/_已执行/` 14 份任务单原文（00–04 全轮次 + 03E/03F/03H），03G（自然语言入口）与 05（PPT/视频分镜，走码道 Space 模式）待执行 |
| 调试排错 | `debug-log-2026-10-28.md`：十七轮「先红后绿」记录（每轮含根因/修复/验证） |
| 文档生成 | `docs/` 七份文档（架构/规则规格/API/华为云/开发指南/演示脚本/开发历程）为码道撰写 |

### 4.2 Prompt 设计质量

任务单按固定结构组织（可在 `prompts/` 原文中直接验证）：
**背景与现状 → 硬约束（不许做的事）→ 逐条任务（含验收标准）→ 交付要求**。
典型设计：
- 「先写测试再改实现」被写进硬约束，产出 60 个测试 + 前端运行时冒烟脚本
- 契约先行：后端任务单以前端已固化的 `static/js/api.js` 为唯一契约来源
- 反过度工程约束显式写入（「不要加没用的抽象层」），抑制 AI 过度生成

### 4.3 真实性（如实说明）

- **由码道生成**：全部源代码、测试、文档、工程脚本
- **由人工完成**：任务单的撰写与评审（含三轮方向性返工：视觉方向两次被人工评审否决后重做）、
  最终决策（选题/架构权衡/软硬分级策略）、真实运行验证与即将进行的截图/录屏
- **过程记录的留存缺口（如实申报）**：W1 阶段（管线与 CLI 主体）开发时未开启对话截图导出，
  该阶段以任务单原文 + 调试记录 + git 基线提交作为替代证据；现存截图类证明材料
  覆盖 W2 各阶段（见 `codearts_proof/`，正文中无伪称）

### 4.4 一句话总结

> 码道承担了「实现者」，人承担了「提出问题、否决坏答案、验收」——
> 三次方向性返工（V3 删点策略、视觉两次重构）都是人工评审推动的正确决策，
> 这本身就是人机协作开发模式的现场样本。

## 附：故障排查

| 症状 | 处置 |
|---|---|
| 端口占用（8000） | `netstat -ano | findstr :8000` 找 PID → `taskkill /F /PID <pid>`（Windows）；或换端口 `--port 8001` |
| 依赖缺失 | 重跑 `scripts/install.sh`；或仅跑 CLI（零依赖）验证数据层：`python cli.py --days 3` |
| 后端没起 | 前端自动降级本地演示数据（徽标标注），演示不中断 |
| 测试失败 | `python scripts/ctl.py ci` 定位 lint/test/smoke 哪一环 |