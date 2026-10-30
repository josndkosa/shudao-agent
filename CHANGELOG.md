# CHANGELOG

本项目的全部变更记录。格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循语义化版本。本项目由华为云码道（AI Coding）全程开发，
每轮任务对应 `codearts_proof/prompts/` 下的一份任务单原文。

## [1.0.0] — 2026-10-29

### 码道开发轨迹（git log 即证据）

以下提交按时间顺序构成完整开发弧线，message 末尾的 `[prompt NN]`
与 `codearts_proof/prompts/_已执行/` 中的任务单一一对应：

| 轮次 | 内容 | 提交 |
|---|---|---|
| 00 | 基线测量：pytest/CLI/JSON 基线、依赖清单、架构图、缺陷复现记录 | ad7dbbb（并入首提） |
| 01 | 修 W1 四缺陷：V1 跨城日误报 / days=1 出 2 天 / 在线 KeyError / 死代码与 seq 累加 | ad7dbbb（并入首提） |
| 01B | 规则软硬分级（V3=soft）+ 修复循环收敛检测 + 规划器与校验器 leg 口径统一 | ad7dbbb（并入首提） |
| 01C | 恢复夜景收尾（南山一棵树）+ 修正摘点排序键 | ad7dbbb（并入首提） |
| 02 | FastAPI + SSE + 对话式改行程 + 华为云可选接入（OBS / FunctionGraph） | ad7dbbb（并入首提） |
| 03 | 双城 SVG 自绘路线图 + 可倒带决策时间轴（零构建前端） | ad7dbbb（并入首提） |
| 03B | 修复动作可视化（removed 字段）+ revise off-by-one + 流式跟随态 | ad7dbbb（并入首提） |
| 03C | setEvents 未声明标识符导致的白屏修复 + 运行时冒烟脚本 | ad7dbbb（并入首提） |
| 03D | Survey Atlas 视觉重设计（测绘图鉴风格，后被 03F 替换） | 2c94ff9 |
| 03F | 瑞士网格视觉重构 + 动效编排（当前视觉基线） | 115abc7 |
| 04 | 工程正规化：目录/文档体系/数据分层/打包脚本 | 本轮提交 |

> 说明：git 仓库在 03D 完成后才初始化（时序受开发节奏影响），
> 00–03C 的改动合并在基线提交 ad7dbbb 中，其逐轮调试过程完整保存于
> `codearts_proof/debug-log-2026-10-28.md`（六轮先红后绿记录）。

### Added

- 三段式行程规划管线（规划 → 校验 → 叙事）与 EventBus 事件流（`reason` 字段贯穿）
- 五条校验规则：V1 时长 / V2 开放窗口 / V3 强度（soft）/ V4 预算 / V5 亲子（hard）
- 违规回流修复循环（收敛检测，最多 3 轮；软提醒 advisory / 无解 unfixable 事件类型）
- CLI（`cli.py`，断网保命形态）与 FastAPI 六端点（含 SSE 流式）
- 对话式改行程（纯规则意图解析：减载/加长/移除/重排，离线可用）
- 零构建前端：双城 SVG 路线图、可倒带事件时间轴、Mock/Live 自适应、瑞士网格视觉
- 华为云可选接入层（`server/cloud/`：OBS SigV4 上传 + FunctionGraph 天气）
- 数据层分城快照（`server/data/chengdu.json` / `chongqing.json` + `meta.json` + `schema.md`）
- 工程体系：`pyproject.toml` / `scripts/ctl.py`（跨平台任务入口）/ `scripts/package.py`（提交打包）
- 文档体系（`docs/`）：架构设计 / 规则引擎规格 / API / 华为云接入 / 演示脚本 / 开发指南 / 赛题情报归档

### Tested

- `python -m pytest -q` → 60 passed（工具层 / 校验规则 / 管线 / API 契约 / 缺陷回归）
- `node scripts/smoke_frontend.mjs` → 10/10（前端运行时冒烟）
- `python scripts/ctl.py ci` → lint + test + smoke 一条命令