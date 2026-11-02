# CHANGELOG

本项目的全部变更记录。格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循语义化版本。本项目由华为云码道（AI Coding）全程开发，
每轮任务对应 `codearts_proof/prompts/` 下的一份任务单原文。

## [1.3.0] — 2026-11-02 · 03J 显式偏好画像（「有长期记忆吗」的诚实答案）

### Added

- **偏好记忆（显式指令式，非黑盒画像）**：对话栏说「记住：我带娃，不去博物馆」→
  增量写入画像 → 下一次规划自动带上（亲子模式+避开博物馆）。触发词：记住/别忘了/
  记一下/帮我记住/以后都；忘掉/别记了/清空；我记住了什么/看看我的偏好。零 UI 改动
  （不加开关面板——全部走对话栏，与 03G 自然语言入口同一套交互）。
- **`server/agent/preferences.py`**：画像读写合并。存**用户主目录**
  `~/.shudao/preferences.json`（`SD_PREFERENCES_PATH` 可覆盖）——不进仓库、不进
  提交包（`server/data/` 会被打进 zip 分发给评委，用户数据绝不能放那）；原子写
  （.tmp + os.replace 防半文件）；文件损坏/目录不可写 → 静默降级为无记忆。
- **记忆生效（服务端权威点）**：`run_pipeline` 入口读画像 → `merge_prefs` 合并进
  TripRequest → timeline 发「应用偏好记忆」事件（reason 写明记住了什么+上次记录时间，
  评委在回放器里看得到记忆起作用）；自然语言路径 parse 层同样合并（未说字段由记忆
  填空缺并回填参数条可见）。**显式优先铁律**：这次说了预算五千就用五千。
- **`avoid_tags`（排斥标签）硬排除**：候选筛选阶段生效（poi_search 之后、打分装箱
  之前，`_apply_avoid` 空列表原样返回=零行为变化）；在线路径 exec_tool 源头过滤
  （LLM 看不到被排除的点）+ 归一化层兜底（防幻觉入选，发 fallback 事件）。
  V1–V5 判定逻辑零触碰。
- **中文金额口语解析**：「预算两千」=2000、「一万五」=15000（万位后裸数字按低一级
  单位计）；标签上下文分流：「不去博物馆」→ avoid_tags 而非 tags。
- **`/api/parse` 契约扩展**：返回新增 remember/forget/view/prefs/timeline（记忆
  操作的事件流进回放器可见）；前端 planByChat 记忆三分支；Mock.parse 字段同构。

### 诚实边界（记不了什么，如实提示绝不假装）

口味偏好（「记住：我不吃辣」→「数据维度还不支持，先记不下来」+ 画像零污染）、
具体景点名、酒店/航班偏好——只记数据层有的维度：亲子/预算/喜欢标签/排斥标签。

### Tested

- `python scripts/ctl.py ci` 三连全绿（**132 passed** + 冒烟 23 步）
- 新增 `tests/test_preferences.py` 18 条：读写容错（损坏/不可写/原子写）/意图识别
  （记住/忘指定项/全清/查看）/生效（V5 亲子/博物馆排除/显式优先）/事件可观察
  （已记住/已忘掉/应用偏好记忆含时间）/回归锁（无画像 = `_apply_avoid` 原样返回 +
  merge 零应用）；conftest 全局偏好路径隔离（本机演示画像绝不泄进测试基线）

## [1.2.1] — 2026-11-02 · 03I 前端交互修复（Day 拖动 / 对话栏归位 / Day 跳号）

### Fixed（用户真实使用 30 天 + 6 城后反馈的三个问题）

- **Day 标签横向拖不动**：`.day-tabs` 是 `display: flex` 但没 `overflow-x: auto`——
  24 个标签一行铺开撑破容器、整页横向溢出（`.map-row` 早已同款修过，两个横向区域
  当时只改了一个）。修复四件套：overflow-x + 细滚动条（6px webkit，与 map-row 统一）；
  `.day-tab` 加 `flex: 0 0 auto`（防压缩挤断「Day 12 · 昆明」）；`dragscroll.js`
  拖拽滚动（Pointer Events 原生零依赖，day-tabs 与 map-row 共用，触摸走原生、
  不抢控件按下，拖时抓手光标 + 禁文字选中）；「← 横向拖动查看全部天数 →」提示
  （scrollWidth 实测判断，不写死个数，resize 跟随）。
- **对话栏太靠下**：`position: fixed` 全宽压视口底边（2px 黑线切断页面 + 内容有被压
  隐患）。归位到**参数条下方、地图上方**（main 内、form 外——form 内回车会触发规划
  而不是发消息）；对话与参数都是「用户输入」，语义上本就该相邻；03G 的自然语言入口
  摆正了位置。页面底部不再被切开。
- **在线路径 Day 编号跳号（1,2,3,4,6,7…）**：`_normalize_llm_plan` 用模型返回的
  `day` 字段，某天 poi 全非法被丢后剩余天保留原号留洞。改为**自计数连续分配**
  （被丢的天不占号）；模型原号写进事件 reason（「模型原安排第 2 天」）留参考；
  跨天去重事件里的「第N天」同步用最终显示号。离线路径 day_no 本就连续（回归锁
  确认未破坏）。

### Tested

- `python scripts/ctl.py ci` 三连全绿（**114 passed** + 冒烟 22 步：+2——chat-bar
  归位静态断言 / dragscroll 单元验证）
- 30天6城：26 天（6 城 94 点物理上限）编号 1–26 连续、4 条用尽事件如实说明；
  3天2城常规参数 Day 1,2,3 正常；在线模式 8 天 4 城：8 天全出、编号连续、零幻觉

## [1.2.0] — 2026-11-02 · 03G 自然语言规划入口 + 天数上限放开（抽取与规划分离）

### Added

- **自然语言规划入口（抽取与规划分离）**：`server/agent/parse_request.py` 新增抽取层——
  一句话 → `{origin, cities, days, budget, tags, family, source, note}`。在线实现为一次
  纯 JSON 调用（无 tools，json_mode——03F 预留调用点兑现）；离线实现为正则 + meta 词表
  （城市别名表 `meta.city_aliases`：渝/蓉/春城/山城/筑/版纳/西江……）；两种实现返回完全
  同构，LLM 失败自动降级规则实现。校验归一在抽取层拦死模型自造语义：城市只认
  city_info（不认识的过滤并在 note 如实提示）、标签必须落 expand_tags 受控词表、
  数值 clamp（days 1–30 / budget ≥500）。
- **`POST /api/parse` 端点**（线程池执行与 /api/plan 同款）；前端 `api.parse` 方法。
- **前端对话栏双模式**：无 plan_id = 一句话规划（抽取 → `parsefill.js` 回填参数条 →
  自动触发规划，「我理解为…」提示 + note 如实标注）；有 plan_id = 走既有 /api/revise
  （改行程语义零变化）。回填不替换：未识别字段保留参数条原值。`origin` 只读提示行
  如实标注「暂未计入行程时间与交通费」。
- **天数上限 7 → 30**（前后端同步：PlanRequest le=30 / p-days max=30）。

### Fixed（放开天数暴露的连带缺陷）

- **候选用尽静默丢天**：某城 POI 排完后该天被静默 `continue`——用户要 12 天可能只拿到
  9 天且界面无说明。改为发 `plan/fallback` 事件（reason 写明「建议多选城市」），该天
  不占用 day 序号。
- **预算分母用错**：`budget(request.days, ...)` 在截断发生时系统性低估日均（餐饮/市内
  交通按请求天数乘、城际按实际天数计）。改为按**实际行程天数**核算——planner 三处 +
  **validator.py:84**（该处还把预算回写进 plan，是第三个隐藏调用点，调用栈探针定位）。
- **baseline-cli-3d.txt 误用在线模式生成**（03H 疏忽）：非确定产物不可作回归锚——
  已用 `SD_LLM_MODE=offline` 确定性口径重生成，复跑逐字一致。

### Tested

- `python scripts/ctl.py ci` 三连全绿（**113 passed** + 冒烟 20 步：新增 parsefill 回填
  DOM 断言 + 双模式分发断言）
- 在线真实 DeepSeek 抽取 ×3（source=llm，别名/中文数字正确理解）；离线规则抽取全用例
- `--days 12` 十城：12 天全排满、零用尽事件；单城 days=10：8 天 + 用尽事件 + 日均
  分母锁（per_day == total ÷ 实际天数）

## [1.1.6] — 2026-10-31 · DeepSeek 在线模式接入验证 + health 如实标注修复

### Fixed（接入验证期间发现）

- **/api/health 谎报「引擎离线」**：`_load_dotenv()` 只在 `run_pipeline()` 内调用，服务启动后首次规划前
  health 的 `resolve_mode()` 读不到 `.env` 里的 key——徽标显示「引擎离线」而实际规划走在线，
  违反如实标注原则。修复：`server/app.py` 模块级调用 `_load_dotenv()`（run_pipeline 内的二次调用
  经 setdefault 幂等无害）。
- **接入侧安全迁移**：key 初填在 `.env.example`（入库文件，未及提交即发现）——已安全移入 `.env`
  （gitignore 覆盖），example 还原为空模板；顺带修正用户填写时带的引号（`_load_dotenv` 不去引号，
  直接使用会认证失败）。

### 在线模式首次真实执行记录（此前在线分支从未跑过）

- CLI 全链路真实跑通：LLM 真实 Function Calling（自主调用 poi_search/weather 多轮）→ 归一化 →
  校验 → 5 轮 fix 回流收敛 → 合法 3 天行程，事件流 67 条，`mode:online`
- FC enum 动态化验证有效：LLM 调用了昆明（说明 6 城枚举被模型正确感知）
- 已知特性（如实记录）：LLM 计划存在非确定性（temperature 0.3）——同一请求两次运行一次排三城一次
  全排成都，行程始终合法；答辩演示若需确定性输出可切 `SD_LLM_MODE=offline`
- 真实端口 `curl /api/health` → `{"mode":"online","llm":true}` ✓

### Tested

- `python scripts/ctl.py ci` → 三连全绿（82 passed + 冒烟 18/18）
- 在线 CLI ×2（FC 链路 + 完整行程校验）+ 真实端口 health + 浏览器徽标实开

## [1.1.5] — 2026-10-31 · P0 修复：地图路线从未渲染（revealed 嵌套 detail 读错层级）

### Fixed（用户复核发现的 P0）

- **地图路线/点位点亮从未渲染过**：事件流「第N天选点」的 detail 是嵌套结构
  `{"detail": ["CD-09", ...]}`（EventBus.emit kwargs 收集），而消费端
  `Array.isArray(ev.detail)` 恒 false → `revealed` 永远空集。受影响的四项核心视觉全部复活：
  朱红当日路线折线（全仓唯一折线生成点）、「D1 起/D2 止」标签、点位点亮态与 popIn 入场动效、
  routeDraw 描线动效；回放拖进度条时地图从「毫无变化」恢复为逐日点亮。
  完成兜底 `if (!view.revealed.has(day))` 此前是死代码（空 set 已 put，has 恒 true），
  修复后该分支语义恢复为「该天选点事件是否已发生」。
- `onEventClick` 的内联解包与 `applyEvent` 统一收敛到 `payload()` 单一解包点。

### Changed（结构性）

- **视图状态机抽为 `static/js/view.js`**（纯函数：`freshView` / `payload` / `applyEvent` / `viewAt`，
  不碰 DOM），main.js import——「事件流→视图状态」链路自此可被冒烟直接覆盖。
- **冒烟 15→18 步且每步带断言**：新增 decision 嵌套 detail→revealed 非空（P0 回归锁）、
  violation/advisory 按 day 落位、fix removed 落位三步；CityMaps.render 步改用真实
  `viewAt(events)` 驱动并断言 revealed 非空；**删除**旧手工构造 revealed 的写法
  （它用与 bug 一模一样的错误表达式 `Array.isArray(e.detail)` 且无断言——虚假安全感的教科书案例）。
  脚本尾部打印总步数。

### V3 地形分档回归差异（用户裁决：接受）

分档收紧后重庆强度 14.4 仍 > 8.0，软提醒照常出现——说明分档既未掩盖真问题、也未制造假阳性。
（此前 1.1.0 已记录：唯一回归差异是 V3 detail 阈值数字 8.5→8.0，advisory 数量不变。）

### 文档口径统一（工程现状 v1.1.4 / 十四轮 / 82 passed / 6 城 101 点 / 双页面）

- readme/README.md：40 点→101 点 6 城分城文件；11 份任务单→已执行 12 份 + 05 待执行；八轮→十四轮；URL 统一 /plan.html
- docs/华为云接入说明.md：任务单 13 份（12 已执行 + 05 待执行）；八轮→十四轮；pytest 60→82、冒烟 18 步
- docs/开发指南.md：40 点断言→101；load_city_pois 映射口径更新（6 城 + glob 自动发现）
- docs/开发历程.md：轮次总览表补 03E 批次1 与第 12–16 轮（直觉性→双页→字号→Day tab→P0 复核演进线）
- docs/API.md：补 /api/plan cities 参数语义与 /api/geo city_meta、/api/meta city_info.terrain 契约
- docs/演示脚本.md：按「品牌首页 + 工作台」双页重排为 9 镜
- codearts_proof/ACCEPTANCE.md：里程碑表勾选 03F/04/03E 批次1/前端四连；归档口径 8→12 份
- 03E 任务单原文归档入 `prompts/_已执行/`（12 份）

### Tested

- `node scripts/smoke_frontend.mjs` → 18/18 步（含事件流→视图状态三步回归锁）
- `python scripts/ctl.py ci` → 三连全绿（82 passed）
- 浏览器实开 `plan.html?auto=1` 供画面级验收（路线折线/点亮态/advisory 条/事件点击高亮）

## [1.1.4] — 2026-10-31 · 修复 Day tab 点击无法切天

### Fixed

- **Day 1/Day 2 tab 点击回不去**（用户实测反馈）：`renderAll` 里 `dayPanel.render(itinerary, { activeDay: state.activeDay, ...view })`
  的对象展开顺序使 `view.activeDay`（回放状态机中最后一条 decision 事件的天）**覆盖**手动选择的
  `state.activeDay`——点击设置了 state 却被 view 盖回，永远停在最后一条 decision 的天。
  自回放状态机引入以来即存在（此前未在已跑完行程上点过 tab 而未暴露）。
- 修复为**天状态单源化**：`viewAt` 后统一 `view.activeDay = state.activeDay`（地图路线高亮与行程卡
  两个消费者同源）；回放 seek 路径（onSeek 写 state）不变；流式回调补 decision 时同步 state.activeDay，
  保住「新一天开始排程自动跟随」的直播语义不退化。

### Tested

- `python scripts/ctl.py ci` → 三连全绿（82 passed + 冒烟 15/15）
- 静态 8765 浏览器实开运行态供点击回归

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