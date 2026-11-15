# CHANGELOG

本项目的全部变更记录。格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循语义化版本。本项目由华为云码道（AI Coding）全程开发，
每轮任务对应 `codearts_proof/prompts/` 下的一份任务单原文。

## [1.4.3] — 2026-11-15 · 03M 拍摄模式与预检板 + 交付素材落位 + 云端部署

> 03M 是「交付收口」轮：不加业务功能、不改一像素视觉，只把**人做的那两个动作**
> （录屏、截图）的成本压到接近零，并把「现在能不能交」做成一条命令。
> 任务单原文：`codearts_proof/prompts/_已执行/03M_拍摄模式与预检板_把人的两个动作压到最短.md`。
>
> **云端部署**：<https://shudao-agent.onrender.com/> —— 云端完整 FastAPI 后端，
> SSE 事件流与对话式改行程全部可用（`/api/health` 返回 `mode: offline`，离线优先不依赖外部 LLM）。

### Added

- **交付素材落位**：`docs/images/` 六张规格图（home / overview / player / map / replay / chat，取自实际运行画面）与
  `video/蜀道智行-演示视频.mp4`（**177 秒**，赛题限 180 秒）。文件名须与 `docs/images/README.md` 规格表一致
  （`package.py` 的闸从那张表解析文件名）。README 两处改为真实嵌图。
- **拍摄模式**（任务 A）：六个 URL 参数直达目标状态（`?shot=overview|player|map|replay|chat`），
  全部复用既有函数（`run()` / `state.player.seek(n)` / `drawer-open` / `revise()`），
  **不加 UI、不加样式**——保证加参数后画面与现状完全一致，录屏与截图可复现。
  `map.png` 的 tooltip 需人工悬停，已在 `docs/images/README.md` 如实标注。
- **提交预检板**（任务 B）：`python scripts/ctl.py preflight`，七项检查
  （视频 / 六图 / PPT 常量 / 地址可达 / 占位残留 / 任务单份数 / 版本号一致），
  每行给一句「下一步该干嘛」的人话，而不是只给退出码。`--offline` 跳过地址可达项。
- **公网部署验证**（任务 C）：`python scripts/ctl.py verify <url>`，
  逐项打 `/api/health`、`/api/meta`、`/api/plan` 并给耗时与结论。

### Changed

- **版本号单一真相源**（任务 D）：`gen_ppt.VERSION` 改为运行时读 CHANGELOG 顶条，
  不再与 zip 名 / 提交清单各写一份。
- **package.py 补两闸**（任务 E）：`video/` 内 mp4 时长 ≤ 190 秒、
  归档任务单份数 ≥ 清单项数；mp4 时长复用 preflight 的纯标准库解析（不写第二份实现）。

### Fixed

- **提交三闸在 Windows 上全部跑不完（严重）**：`ctl.py` / `package.py` / `preflight.py` /
  `check_placeholders.py` / `verify_deploy.py` / `export_demo_assets.py` 均 print 了
  `✓`/`✗`/`✅`/`⚠️` 等 GBK 不可编码字符，却没有 `sys.stdout.reconfigure(encoding="utf-8")`。
  Windows 控制台按 GBK 编码 → 最后一行 `UnicodeEncodeError` 崩溃。
  后果：**`ci` / `preflight` / `package` 在这台机上从未真正跑完**，缺陷得以漏检到远端。
  修法：照抄 `cli.py` 既有守卫写法，六处统一补齐。
- **ruff W292**：`preflight.py` / `verify_deploy.py` 末行缺换行，导致 GitHub Actions
  CI 三连失败（3.12 矩阵）。补换行，零逻辑改动。
- **预检板版本号项永远红**：`preflight.ppt_constants()` 用正则读 `VERSION = "..."` 字面量，
  而 03M 任务D 已把 `VERSION` 改成 `_changelog_top_version()` 函数调用 → 永远读到 `None`。
  改为识别该形式并直接对 CHANGELOG 求值（它不是独立真相源，只是镜像）。

### Tested

- `python scripts/ctl.py ci` → lint + pytest（146 用例）+ 前端冒烟（24 步）**全绿，并完整跑完最后一行**（修复前会在末行崩溃）
- `python scripts/preflight.py` → 七项正常出表（此前崩溃）
- GitHub Actions：`main` 推送上后三连通过

---

## [1.4.2] — 2026-11-09 · 外部审查修复轮（P0 正确性与可信度收口）

> 来源：外部审查报告《蜀道智行：赛事解析、项目锐评与实施方案》（2026-11-09，Codex）。
> 本轮**先独立复现再修**——报告指控的 5 个 P0 全部在本地复现确认后才动手，
> 不盲信任何单一审查方。每条修复都配了回归锁（`tests/test_p0_fixes.py` 8 条）。

### Fixed（P0：演示与可信度阻断）

- **P0-01 真实后端地图空数据**：`api.js` 的 `geo()` 对 `null` 执行
  `encodeURIComponent` → 字符串 `"null"` 被后端当城市名过滤 → 返回 0 城 0 点。
  前端改为 `URLSearchParams` 仅写入有值参数；后端 `_build_geo` 对历史客户端的
  `"null"/"undefined"/""` 做兼容（视为未指定）。真实端口实证：`city=null` 从
  0 城恢复为 15 城 237 点。
- **P0-02 Live 流式提前完成导致重复规划**：`LiveApi.stream` 启动 `pump()` 后立即
  返回（未等读流），`main.js` 兜底分支在流开始前触发 `api.plan()` 双跑。
  改为 `await pump()` 等流真正读完才 resolve——与 03K 修过的 MockApi 同构。
  顺带把「忽略坏帧」里的回调异常吞掉改为「JSON 解析失败跳过、回调异常不吞」。
  无头实证：慢流（120ms/帧）下 `await stream` 返回时已收到行程、耗时覆盖整流。
- **P0-03 时间表允许景点与用餐重叠**：`_build_timeline` 插餐写死 12:00/18:00，
  前一活动未结束就重叠（默认场景：武侯祠 10:10–12:10 与午餐 12:00、
  宽窄巷子 15:44–18:14 与晚餐 18:00）。改为 `max(窗口起点, t)` 起算
  （t=前一活动结束时间）。修复后默认场景**所有活动零重叠**（回归锁：
  `test_activities_never_overlap_default_scene`）。**baseline 因此重生成**
  （fixture 头部注明：餐点修正导致后续点位时刻后移，点位/负载/预算/事件序列不变）。
- **P0-04 超预算报告无条件宣布「V4 通过」**：`report.py` / `report.js` 第 5 节
  原写死「V4 预算校验通过」。改为读真实状态：总花费超上限 → 报超额与差额
  （如「超出预算 ¥1014，未通过 V4 预算校验」）；校验段有「仍残留违规」done 事件 →
  如实标注；费用统一用「预估」而非「实际总花费」。真实端口实证：7 天 500 请求
  （总花费 ¥1514）报告写超出预算而非通过。
- **P0-05 合法空候选崩溃 + SSE 异常无收尾**：排斥标签清空候选 → `budget(0)` 除零。
  修三层：`budget()` 对 days<=0 不除零；`offline_plan` 重试后仍空则提前返回
  空行程 + 明确「候选为空，无法规划」fallback 事件（**不静默放宽排斥标签**）；
  `stream()` 的后台任务加 `try/except/finally` 保证终态（成功或 error 后必发
  stream_end），线程事件经 `loop.call_soon_threadsafe` 入队（不直调跨线程 Queue）。

### Fixed（P1/P2：评委会问倒的硬伤与工程收口）

- **P1-02 修改指令遵守（三层指令违背路径全堵死）**：审查复现「第一天先去奎星楼街，
  实际首站仍是武侯祠」与「排斥博物馆后『加一个』又加回金沙遗址博物馆」。修复中
  发现用户指令被违背竟有**三层路径**，逐层堵死——
  ① **重排覆盖**：reorder 把目标提到最前后整体进 `_order_day`，最近邻重排把锁定
  顺序冲掉 → 锁定点固定最前，其余点从锁定点位置出发排序；
  ② **容量摘除**：重排后 leg 变长超容，`_trim_to_capacity` 按分数摘掉低分的锁定点
  → trim 加 `protect` 参数，用户点名的点不进摘除候选（真超容留给 validator 如实报）；
  ③ **开放窗口摘除**：锁定首站（奎星楼街 10 点开门）被排 8:36 到 → V2 违规 →
  fix 直接摘掉用户点名的点 → **等待开门策略**：首站开门晚于正常到达则推迟出发
  （`_build_timeline`/`_trim_to_capacity` 加 `start` 参数，容量从推迟时刻起算），
  事件 reason 如实说明「出发推迟到 X 点（等待开门，不摘你点名的点）」。
  另：extend（加一个）引入的新候选此前直接从全局 POI_INDEX 取、未过排斥过滤——
  改为与初次规划同款 `_apply_avoid`（**排斥标签的点位永不因加长复活**）。
  回归锁 2 条：`test_reorder_locks_user_first_choice`（点名末位点提前，断言修订后
  它就是首站）、`test_extend_never_resurrects_avoided_tags`（排斥博物馆后加长，
  断言博物馆类点位不出现）。
- **P1-04 自然语言理解**：「不带娃」「不要亲子」不再误判为亲子模式（新增
  NEG_FAMILY 否定短语表；「一个人带娃」不误判——「一个人」不进否定词表）；
  城市顺序按**文本出现顺序**（「先去重庆再去成都」→ [重庆, 成都]）而非 meta 表顺序；
  `_cn_amount` 支持阿拉伯+中文混合金额（「2千」=2000，此前阿拉伯数字字符不在
  中文数字表 → 直接返回 None）。
- **P2 工程**：`.github/workflows/ci.yml` Node 18 → 20（`import.meta.dirname`
  需要 ≥20.11，readme 同步）；`boot()` 里 `buildCityPicker()` 改 `await`——
  此前未 await 导致 URL 里的 cities 参数在选框创建前被回填丢弃（真实网络下
  用户指定城市被默认成渝覆盖）。

### 同批入库（人工侧并行改动）

交付物分桶与 CI 入口收敛（用户手工）：`scripts/ci.sh` / `ci.bat` 移除，
CI 唯一入口收敛为 `python scripts/ctl.py ci`；`答辩材料/` 源文件单一化、
`不上交/` 分桶、`提交清单.md` 权威口径、`已废弃脚本/` 归档。
双方改动共存于 `package.py`（人工的投放逻辑 + 本轮占位闸）已验证兼容。

### Tested

- `python scripts/ctl.py ci` 三连全绿（**156 passed**（146+新回归锁 10 条）+ 冒烟 24 步）
- 五个 P0 全部先独立复现、修复后真实端口/无头逐条验证通过；P1-02 的三层指令
  违背路径（重排覆盖/容量摘除/开放窗口摘除）由回归锁逐层钉死
- 默认场景 baseline 重生成后回归锁仍绿（`test_dual_city_regression_locked`）
- **注意**：`scripts/export_demo_assets.py` 未强制 `SD_LLM_MODE`——在 .env 有 key
  且 auto 模式下重生成会产出**在线 LLM 版** demo（结构不同、无「第N天选点」事件），
  曾因此冲掉冒烟 P0 回归锁。重生成演示资产必须 `SD_LLM_MODE=offline python ...`
  （03G 轮已记录过的同类坑，本轮再次踩中并纠正）。

## [1.4.1] — 2026-11-03 · 03L 身份与材料收口（决策报告导出与占位自证）

### Added

- **决策报告导出（任务L6，补 03K 砍掉的任务 C）**：答辩时「评委可以自己下载一份
  证据」的交付物——下载下来的 md 里每个决策的 reason 原样在。
  - `server/agent/report.py`：`render_report(itinerary, timeline, meta)` 六节固定结构
    （请求摘要 / 逐日行程 / **决策链事件流全量 reason 不截断** / 校验与修复 /
    预算明细 / 数据与版本）；`unwrap_detail` 与前端 `payload(ev)` 逐字同语义
    （嵌套取内层 / 扁平原样——直读 ev.detail = 第 4 节静默空白，03H 任务 H5
    那次 P0 的报告版不许重演）；事件契约版本运行时读 `event.schema.json`
    （不手抄）；生成时间真实时间。
  - `GET /api/plan/report?plan_id=`：`text/markdown` + `attachment` 下载；query 参数
    （对齐 geo 的约定）；404 与 revise 一致；只读端点不动 `_PLANS` 缓存。
  - 前端：`static/js/report.js`（纯函数 renderReport，无 DOM/网络依赖）+
    `api.js` 第 8 方法 `report(planId)`（Live=服务端 md / Mock=本地同构生成，
    UI 零 `if (mock)`、不直接 fetch）+ 抽屉底部「⤓ 导出决策报告」按钮
    （Blob 下载，失败上徽标红字与 run/revise 同款兜底）。**断网（Mock）也能导出**，
    六节标题与服务端逐字一致（`tests/test_report.py` 锁章节序列 + JS 子进程渲染比对）。
  - 测试 7 条：Python/JS 章节一致性（node 加载 report.js 喂真实 demo.json 比对）、
    reason 全量不截断、报告点数 == 行程点数、双形状解包锁、夜景场景第 4 节
    四类齐全（violation/fix removed/advisory 嵌套载荷）、端点契约（content-type /
    disposition / 404 / 只读幂等）。冒烟 +1 步（**24 步**：真实 demo 产物断言
    六节 + reason 原文 + 预算 + 断网如实标注）。
- **占位残留闸（任务L5）**：`scripts/check_placeholders.py`——扫会进 zip 的
  README / readme / docs / ppt 文本 + `scripts/gen_ppt.py`（身份信息源）+
  **pptx 穿透**（当 zip 解开查 `ppt/slides/*.xml` 与 `notesSlides/*.xml`——二进制
  grep 找不到）；判定 `_{6,}`（`___` 分隔线 / `__init__` 不误伤）；排除
  codearts_proof（历史任务单原文里的 ______ 是证据）、docs/baseline、赛题情报。
  接进 `package.py` 自检（staging 双根扫描：顶层 + project/ 子根，命中走 problems
  ——正式提交必拦，`--allow-missing-media` 开发期放行）。
- `.github/workflows/ci.yml`（任务L8）：与 `ctl.py ci` 等价的流水线配置
  （push/PR 触发、Python 3.11+3.12 矩阵、装主+dev 依赖、跑三连）。
  **文件头如实说明当前不自动运行（仓库无远端）——它是「可接入的配置」而不是
  「已在跑的 CI」**，开发指南同口径说明。
- **交付物分桶（03L 任务L0，人工侧）**：仓库新增**三个桶**，把"哪些上交"从隐性变成显性。
  - `提交清单.md`（仓库根，**上交**）：**唯一权威口径**——zip 五件套逐项状态、
    逐目录归属表（进 zip / 不进 zip / 谁挡的）、三道提交前机器闸、四项待补清单。
  - `答辩材料/`（**不上交**）：`讲稿.md` 与 `视频分镜.md` 从 `ppt/` 移出；
    `package.py` 按 `zip-layout.md` 原规划在打包时把讲稿投放 `ppt/`、分镜投放 `ppt/` 与 `video/`
    ——**源只有一份**，不维护两份真相（想撤掉讲稿：删投放块里那一项即可）。
  - `不上交/`（**不上交**）：赛题官网抓取的原始 JSON（`comp_tabs.json` 106KB 等）；
    有用的**原文**仍留在 `docs/赛题情报/`（4 个 txt）上交，让评委能核对我们对赛题的理解。
  - `package.py` 的 `EXCLUDE_DIRS` 加 `答辩材料` / `不上交` 两项——**这两个目录绝不进 zip**。

### Changed

- **身份信息固化单一来源（任务L1）**：`gen_ppt.py` 顶部常量块（TEAM_NAME
  「网恋被骗五毛钱」/ GROUP 高校组 / MAJOR 人工智能技术应用 / CONTACT 刘明超 /
  MEMBERS 四人分工与 `readme/团队分工.md` 同源）。封面与尾页 5 处占位全部改从
  常量取；尾页分工改四人两行（字号 18→16 装得下，不删成员不合并）；「仓库 /
  演示地址二维码位：预留」整句删除换真实演示地址位。**SUBMIT_DATE / DEMO_URL
  留占位由参赛者手填**（03L 任务单第六节）——这两项被 L5 的闸盯着，填完才转绿。
- **措辞修正（任务L3）**：PPT 第 16 页「CodeArts Repo 托管工程」→「本地 git 仓库
  （含完整 [prompt NN] 提交轨迹）」——本项目从无远端仓库，原表述会被评委一句
  「仓库地址发我一下」问穿帮；讲稿/开发指南同步（开发指南补三行如实说明）。
- **口径残留清理（任务L4）**：`server/data/meta.json` note（只改这一个字段，
  diff 1 行）：「批次1 落地 6 城 / 广度层随批次2/3 补齐」→「批次 1–3 已全部落地，
  合计 237 点」（与 schema.md 不再互相矛盾；`/api/meta` 不含 note，运行时口径
  本就干净）。`docs/演示脚本.md` 第 9 镜旁白词：14 份任务单/96 测试/冒烟 18 步 →
  **19 份任务单 + 24 轮先红后绿 + 139 测试 + 冒烟 23 步**（「十七轮」指 debug-log
  轮数，保留）。
- `package.py` need_prompts 清单加 `03L_`。
- `docs/API.md`：端点表加 report（顺手把「六端点速览」的「六」去掉——数字会过期）；
  新增「决策报告」一节；Mock 同构说明更新为八方法。

### Removed

- **`scripts/ci.sh` / `scripts/ci.bat`**（移入 `不上交/已废弃脚本/`，可回滚）：
  职责被 `python scripts/ctl.py ci` 完全覆盖，且**旧实现更弱**——
  两者的 lint 步写成 `ruff check . || echo "（ruff 未安装则跳过）"`，
  **`||` 会把 ruff 真报出的 lint 错误一并吞掉，脚本仍打印「✓ CI 全部通过」**；
  而 `ctl.py ci` 先用 `probe.returncode` 判断 ruff 是否安装，装了但有错就非零退出。
  留着一个会给出错误结论的入口＝给"虚假安全感"开口子。
  引用已同步：`docs/华为云接入说明.md` 与 `server/cloud/README.md` 的 CI 说明改为
  **唯一入口 `python scripts/ctl.py ci`**；`.github/workflows/ci.yml` 本就调它。
  > 历史记录里提到这两个文件的地方**保持原样**——debug-log 与 04 任务单记的是
  > "当时创建了它们"，那是**事实**，不是待办清单。

### Tested

- `python scripts/ctl.py ci` 三连全绿（**146 passed**（139+报告 7 条）+ 冒烟 24 步）
- 真实端口实测：plan → report 全链路 200，content-type / disposition / 404 全对；
  报告六节齐全、第 4 节双形状载荷正确、点数 14 == 行程点数
- 断网 Mock 导出：六节标题与服务端逐字一致，第 6 节如实标注「后端未启动，
  运行时版本不可读」
- 占位闸：当前 4 处命中（gen_ppt.py:60/61 + pptx#slide1/slide18）——全部来自
  SUBMIT_DATE / DEMO_URL 两个**有意占位**（等参赛者手填，填完转绿）；
  staging 假探针文件被精确报出（`readme/_probe_placeholder.md:2`，文件+行号）
- PPT 重出 + PDF COM 导出：封面（队名/专业/联系人）、尾页（四人分工）、
  第 16 页（本地 git 措辞）逐页验证通过；实测口径行 pytest 146 / 冒烟 24 /
  任务单 19（归档 03L 后终版重出为 20）

## [1.4.0] — 2026-11-03 · 03K 收口加固（决策协议化与可复现补强）

### Added

- **事件契约 v1.0.0（任务A）**：`server/agent/event.schema.json` 把 Event 的核心字段
  （`seq / type / stage / title / reason` + `detail` 载荷；`t` 可选——序列化帧可省略）
  固化成**带版本号**的契约。校验纯标准库实现（`server/agent/event_contract.py`，
  零新依赖：字段存在性 + 枚举成员 + 类型 + 下界/非空）。
  `tests/test_event_contract_schema.py` 三锁：真跑管线**所有事件**过校验 /
  造非法 `type` 必报错（防恒真校验器）/ 缺必填字段必报错。
  **任何行程规划 Agent 按这五字段发事件流即可接入本项目的可倒带回放器**（docs/API.md
  已注明）。`events.py` 零改动——契约只读不写。
- **深链 `?seq=N`（任务B）**：`plan.html?days=3&budget=3000&tags=…&seq=17` 隐式
  `auto=1`，管线跑完定位到第 N 条事件（走与手动拖进度条**完全相同**的 seek 路径）；
  N 越界落最后一步并在状态行如实提示；cursor 经 `history.replaceState` 写回 URL
  （可分享精确位置、不产生历史条目）；首页参数透传带 `seq`。
- **数据溯源旁挂（任务D）**：`server/data/provenance.json`——只登记**逐条核对过出处**
  的点（当前 0 点，等人工核对表填入；**不出现 = 未核对**，比批量标注「人工整理」更
  干净）。`tests/test_data_provenance.py` 两锁（id 真实存在于 POI 表 / source 非空 +
  verified_at 合法日期）。`schema.md` 增「数据核对状态」节。**15 个数据文件 diff 为 0**。
- **打包三闸（任务F4）**：`package.py` ①密钥扫描——staging 内容级搜 `sk-` 前缀与
  带值的 `DEEPSEEK_API_KEY=`（`.env.example` 的注释空值模板不误伤），命中即败且
  `--allow-missing-media` 也不放行（泄漏是唯一不可挽回的失败）；②`--max-mb`（默认
  100，超限删包退出并打印实际体积）；③收尾打印每个顶层目录的解压体积（畸大目录
  一眼可见）。实测：codearts_proof/ 9.9 MB 是 zip 里的大头。
- `requirements-dev.txt`（ruff / python-pptx 开发与出 PPT 工具，与主依赖分离）。

### Fixed

- **`.gitignore` 断链（任务F3）**：`.uvicorn-8000.log` 的忽略规则此前被上一行注释
  意外吞掉（「…必须提交.uvicorn-8000.log」），实为从未生效——拆为独立规则行，
  `git check-ignore` 实证命中。
- **Mock 流式 resolve 语义与 Live 不同构（顺手修的既有 bug）**：MockApi.stream 此前
  立即 resolve，main.js 的兜底分支在流开始前就触发 `api.plan()` 双跑（事件列表出现
  两份、`setStreaming` 提前解除），且 done 帧的 seek 会晚于深链定位执行、把 `?seq=N`
  的定位覆盖回末尾（断网演示下深链失效）。改为**等流真正推完再 resolve**（与
  LiveApi「读完 body 才返回」同构）。真实端口日志对照实证：修复前的会话
  stream+plan 双请求，修复后仅 stream 单请求。
- **业务 done 事件被哨兵判定误吞（顺手修的既有 bug）**：SSE 哨兵 = 纯 `type` 无
  `stage`（API.md 口径），main.js 原判定只看 `type`——narrate/system 段的 `done`
  **业务**事件被吞，前端事件数 < 后端 timeline，`seq` 深链随之错位。补 `stage`
  区分后，事件流与后端 timeline 真正同源（demo 场景 19→23 条对齐）。
- **`load_pois` 排除清单**：加 `provenance.json`（溯源旁挂是 dict 不是 POI 列表，
  不排除会把它的键当 POI 迭代，直接 TypeError）。

### Changed（任务F1/E：口径与复现治理）

- **版本锁定**：`requirements.txt` 五包全部 pin 为 `==`（干净 venv 安装即复现；
  pytest 留在主依赖——install 脚本以测试全绿收尾）；readme 版本表改实测值
  （fastapi 0.136.3 / uvicorn 0.49.0 / pydantic 2.13.5 / openai 2.38.0 / pytest 9.1.1）。
- **摘除易变数字（E2）**：README 徽标 / readme / 华为云接入说明 / 开发指南 / 讲稿 /
  视频分镜中的测试数、冒烟步数、任务单份数改为「以 `scripts/ctl.py ci` 输出为准」；
  POI 口径全站统一 **15 城 237 点**；**gen_ppt.py 改为重出时现读实测**（pytest
  collect + 冒烟输出 + 任务单目录计数；实测失败回落「—」，绝不印编造数）——
  PPT 是快照型材料，数字与重出时点**必然**一致（本次重出：139 tests / 23 步 / 18 份）。
- 讲稿 P16「CodeArts Repo **加**流水线」→「CI 已脚本化（ctl.py ci），**可直接接入**
  CodeArts 流水线」——仓库无流水线定义文件（CodeArts Repo 不执行 .github/），
  原表述答辩时会被一句「流水线在哪看」问倒。
- `package.py` 的 need_prompts 清单加 `03K_`。

### Tested

- `python scripts/ctl.py ci` 三连全绿（**139 passed** + 冒烟 23 步）
- 默认场景与 `tests/fixtures/regression-chengdu-chongqing.json` 逐字一致（回归锁在跑）
- 深链无头双场景断言：`?seq=17` → cursor=17 + URL 写回 seq=17；`?seq=999` →
  落最后一步（23）+ 如实提示「超出范围，已定位到最后一步」
- 干净 venv：`pip install -r requirements.txt` 装出版本与 readme 表逐项一致，测试全绿
- `package.py`：`sk-` 探针文件被拦（打印命中路径 `project\zz_secret_probe.txt`）；
  `--max-mb 1` 拦截（打印实际 10.6 MB）；完整打包 10.6 MB 通过
- PPT 程序化重出 + PowerPoint COM 导出 PDF（实测口径自证打印）

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