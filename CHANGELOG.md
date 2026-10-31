# CHANGELOG

本项目的全部变更记录。格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循语义化版本。本项目由华为云码道（AI Coding）全程开发，
每轮任务对应 `codearts_proof/prompts/` 下的一份任务单原文。

## [1.1.3] — 2026-10-31 · 字号阶梯提升 + 空态挂载修复

### Changed（用户反馈「字体有点小」）

- **字号阶梯提升**：全站 +1px 为主（微小字 11→12、辅助字 12/12.5→13、正文 13/13.5→14/14.5），
  标题与数字块 +1~2px；覆盖顶栏/参数条/图幅图例/逐日行程/回放抽屉/对话栏/首页全部组件，
  SVG 内天序标记同步 10→11。网格/间距/字重/颜色一律不动。
  实现方式：style.css 末尾集中覆盖段（原规则区不改，可审阅可整体回滚），约 45 条选择器按组件分组注释。

### Fixed

- **空态引导从未挂载**（用户截图「结果区一片空白」的根因）：第十一轮加的空态占位只在
  `DayPanel.render(null)` 被调用时才渲染，而 `boot()` 只有 `auto=1` 才 run——非 auto 路径
  从不调用 renderAll，空态代码写了但永远不触发。修复：boot 非 auto 分支补 `renderAll(0)`。
  教训同第六/十轮：冒烟验证了「调用 render(null) 会渲染空态」，没验证「boot 会调用它」——
  **渲染分支验证 ≠ 挂载路径验证**。

### Tested

- `python scripts/ctl.py ci` → 三连全绿（82 passed + 冒烟 15/15）
- 静态 8765 浏览器实开：plan.html（空态）与 plan.html?auto=1（运行态）

## [1.1.2] — 2026-10-31 · 双页面拆分：品牌首页 / 规划工作台

### Changed

- **前端拆为两个物理页面**（用户截图反馈「把这俩分成俩页面」）：
  - `index.html` = 品牌首页：hero 大标题 + 4 数据卡 + 三步管线说明（01 规划 / 02 校验 / 03 叙事）+ 黑色大 CTA + 页脚
  - `plan.html` = 规划工作台：参数条 + 多城地图 + 逐日行程 + 回放抽屉 + 对话栏（原单页的全部功能，去掉 hero）
  - 共享 style.css 与 JS 模块（api/map/timeline/player 不动）；新增 `js/home.js`（首页徽标 + 透传），工作台沿用 `js/main.js`
  - **旧链接零破坏**：`?days=&budget=&tags=&auto=1&cities=` 打到首页自动透传到 plan.html（README/演示脚本既有用法不变）
  - 工作台顶栏品牌名可点击返回首页；FastAPI StaticFiles 天然服务 /plan.html，后端零改动

### Fixed（截图评审暴露的问题）

- **徽标语义矛盾**：「离线」与「● 已连接后端」并存——badge-offline 恒显「离线」从不更新。修复：badge-api 表达后端连接状态、badge-offline 表达引擎模式（LLM 在线 / 引擎离线 / 演示数据），双页同源逻辑
- advisory 软提醒天的 Day tab 内联色 #D29922（白底对比度 2.5:1 不达 AA）→ `.day-tab.adv` class + 朱红 var(--accent)，与全站强调色统一
- 「车乘 0.86h」术语不通用 → 「交通 0.86h」
- chat 快捷词四连排无分隔 → 右间距 + 虚线下划线（hover 变朱红实线，可点性更可发现）
- 首页数据卡「22 决策事件」→ 23（与 demo 资产一致）

### Added

- 冒烟 +2 步（双页拆分互链/职责断言、home.js 透传逻辑）→ 15/15；stub 补 `location`
- package.py 自检 need_prompts 补齐 03D/03F/04（上轮归档后漏同步）
- docs/images/README.md 截图规格按双页更新，新增 `home.png`（品牌首页）共 6 张

### Tested

- `python scripts/ctl.py ci` → 三连全绿（82 passed + 冒烟 15/15）
- 真实端口（uvicorn）：`/` 首页 CTA、`/plan.html` 工作台容器、`/api/health` 全部 200
- 静态 8765 双页浏览器实开验证

## [1.1.1] — 2026-10-31 · 前端直觉性优化 + 两个一致性 bug 修复

### Fixed

- **天数 < 勾选城市数时天数超发**（缺陷2 的多城版）：`_allocate_days` 的比例分支在 days<城数时 `min(take, 负数)` 产生负天数、被 `range` 吞掉后其余城各 1 天——勾 4 城给 2 天实际输出 4 天。修复：该边界取候选池总分前 N 城各 1 天（保持城市顺序），+3 回归用例（含单元级「任意组合分配值全正且总和==days」）
- **负载条「强度偏高」与后端 V3 判定不同口径**：前端硬编码 `LOAD_CAP_INTENSITY=8.5`，批次1 地形分档后昆明（cap 7.0）等城市后端报软提醒但前端不标。修复：`over` 改由 advisories 驱动（校验段报出才标注，回放语义一致），删除硬编码常量

### Added（可发现性优化，不改瑞士网格视觉语言与交互骨架）

- **行程区空态引导**：首开不再空白——三步说明主路径（输入参数 → 三段式生成 → 抽屉回放）
- **城市多选可读性**：加「城市」标签与「全不勾 = 自动选城」说明；勾选城市数 > 天数时即时提示「将按候选池总分取前 N 城（建议天数 ≥ 城市数）」
- **多城横滚提示**：>2 城时图幅下方显示「← 横向滑动查看全部城市 →」
- **地图图例**：排入行程 / 候选未排入 / 被规则移除 / 当日路线 一行小字（首次解释 dim 点与灰叉的含义）
- **回放入口引导**：管线完成后「Agent 决策回放」按钮一次性朱红高亮脉冲（打开抽屉即解除）——核心卖点不再依赖用户自行发现
- 天数输入上限 5→7（与 API `le=7` 对齐）
- 冒烟 +2 步（空态占位断言 / index.html 静态容器完整性断言）→ 13/13

### Tested

- `python -m pytest -q` → **82 passed**（79+3 边界回归）
- `node scripts/smoke_frontend.mjs` → 13/13
- `python scripts/ctl.py ci` → 三连全绿

## [1.1.0] — 2026-10-31 · 03E 批次1（西南赛区多城 · 深度层 6 城）

### Added

- **西南 15 城总表**（`meta.json` city_info）：省份覆盖 ⊇ 赛题定义的西南七省市（四川/重庆/云南/贵州/广西/海南/西藏），每城含 terrain 分档 / 11 月天气快照 / 枢纽坐标 / 图幅注记行
- **批次1 落地深度层 6 城 POI 共 101 点**：昆明 15 / 大理 15 / 贵阳 15 / 桂林 16 逐点手写厚字段（真实坐标/开放时段/票价/爬坡强度，open_hour 各城 ≥9 种取值，summary 全量互异）
- **V3 强度阈值按城市地形分档**（`validator._TERRAIN_CAP`）：盆地 8.5 / 丘陵 8.0 / 喀斯特 7.5 / 高原 7.0 / 极高海拔 6.0 / 热带 8.0——同样的强度值在不同地形下的体感差异成为规则参数；V1/V2/V4/V5 不随地形变化（设计取舍见 schema.md）
- **城际交通自动生成**（`route._gen_intercity`）：105 对城对按枢纽球面距离生成时长/票价；进藏城对按 2.0 绕行系数（直线 ~1250km、铁路实际 ~2500km）；跨省进桂/琼/藏 ×1.25；**人工覆盖表优先**
- **规划器多城**（任务 D）：`TripRequest.cities` 显式指定（未收录城市剔除并如实发事件）；空则按候选池总分自动选 N 城（N=days，发「自动选城」decision 事件）；跨城日容量扣减/时间线开场车次/预算城际票价全部按实际城对动态化（`_ic_leg` / `intercity_cost`）
- **前端动态多城图幅**（任务 E 最小可用）：map.js `setCities()` 按行程涉及城市重建图幅卡（双城 DOM 结构与旧静态双卡一致，视觉零回归）；>2 城容器内横向滚动；参数条新增城市多选（默认勾成渝=默认演示不变，全不勾=自动选城）；geo 契约新增 `city_meta` 注记行
- 测试：+19 用例（`tests/test_southwest.py` + fixtures 双城回归骨架），**79 passed**

### 城际偏差说明（成都-重庆）

自动生成口径下成都-重庆（枢纽直线 272km）应为 **2.29h / ¥130**；
实际生效走人工覆盖表 **1.8h / ¥154**（与历史基线**零偏差**）——覆盖表的存在正是为了让演示基线与真实高铁班次对齐。

### 修复（批次1 期间发现的既有隐藏 bug）

- **前端 advisory/violation 的 day 联动从未生效**：`EventBus.emit(**detail)` 的 kwargs 收集使 `emit(..., detail=v)` 产生嵌套 `{"detail": v}`，前端 `applyEvent` 的 `ev.detail.day` 恒为 undefined——01B 引入软提醒以来，行程卡的琥珀提醒条与违规点击高亮从未渲染过。修复：main.js 兼容嵌套结构取内层（不改后端事件结构，demo 资产零变化）
- 城市分天事件在「单城自动选」场景下补回总分依据说明（旧硬编码文案在 days=1 时丢失解释）

### 双城回归（批次1 最硬的验收）

`--cities 成都,重庆` 四场景（默认/夜景/低预算/单日）与改造前对比：
**点位序列、到离时刻、日负载、预算、事件条数与类型序列全部一致**。
唯一差异：重庆天 V3 detail 的阈值数字 8.5→8.0（hill 分档生效的预期体现，advisory 数量不变）；
day1 场景 weather 事件文案修正了旧硬编码的悬空斜杠瑕疵（「成都多云 / 」→「成都多云」）。
回归骨架已固化为 `tests/fixtures/regression-chengdu-chongqing.json`。

### Tested

- `python -m pytest -q` → **79 passed**（60 存量零删除 + 19 新增）
- `node scripts/smoke_frontend.mjs` → 11/11（新增动态挂载步骤）
- `python scripts/ctl.py ci` → lint + test + smoke 三连全绿
- 真实端口（uvicorn:8901）：geo 6 城分组 + 4 城 plan（城际条目「成渝高铁 1.8h / 重庆→贵阳 列车 / 贵阳→昆明 列车」）+ 多城 revise 全链路通过

### 已知限制（批次2 待办）

- 自动选城顺序按候选池总分而非地理邻近（如 成都→昆明→重庆 存在绕路）；批次2 可加贪心最近邻城市排序
- 广度层 9 城（乐山/阆中/丽江/西双版纳/安顺/西江千户苗寨/北海/三亚/拉萨）POI 未落地（总表与城际已就绪）
- 任务 F（Provider 抽象 OtaProviderStub）按批次计划推迟到批次3

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