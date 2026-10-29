# 码道 Prompt 03 · W2 前端：原生单页 + 双城 SVG 自绘路线图 + 可倒带时间轴（**mock 先行**）

> 用法：整段粘贴给码道（IDE 模式）。
> **前置：Prompt 01 已完成（缺陷已修，demo 数据可信）。后端（Prompt 02）尚未开始 —— 本条不依赖后端。**
>
> 执行完成后，把这段对话与码道的生成过程截图存进 `codearts_proof/`。

---

## 为什么这轮做前端

后端接口契约**已经写死**（见下"接口契约"一节），前端可以完全独立开工。
更关键的是：本次最贵的东西不在后端，而在**可倒带时间轴的交互**和**双城 SVG 的版面**——
这两样看得见、摸得着，越早看到实物越早迭代。早期做出来比早期做正确更值钱。

后端（Prompt 02）随后按前端已固化的契约实现，接上后**前端零改动切换**。

## 本条的两条硬规矩

1. **零构建、零依赖、零 CDN**：原生 HTML + CSS + ES Module。不引入 Vue/React/外部字体/外部地图服务。答辩现场可能断网，任何外部资源都会让页面裸奔。
2. **数据源可切换，且只有一套 UI**：后端起来走真实接口，后端没起走本地 mock 演示数据，**两种模式下界面与交互完全一致**。这既是开发方式，也是答辩保命手段。

---

## 项目根目录

`D:\项目代码\shudao-agent`

## 可用的真实数据（不要手编任何行程内容）

后端还没写，但 **W1 的 CLI 已经完全可用**，它就是 mock 数据的来源：

```bash
python cli.py --days 3 --budget 3000 --tags 美食,文化 --json   # 主数据
python cli.py --days 3 --budget 1200 --tags 美食 --json        # 预算更紧的"改行程后"数据
```

两者都输出 `{itinerary, timeline, mode, budget}`，其中 `timeline` 就是**完整的事件流**（每条带 `seq/stage/type/title/reason/detail`）——这正是"可倒带"的全部素材。

> ⚠️ **不要复用 `docs/baseline/baseline-demo.json` 作为前端数据。**
> 那份是 Prompt 00 在**缺陷修复前**跑出来的"before"快照（若 D1 属实，其中已被误删了磁器口与湖广会馆）。
> 前端必须用下面的 `export_demo_assets.py` **在修复后的代码上重新生成**。
> `docs/baseline/` 里的产物只用于 before/after 对照与文档引用。

---

## 交付物

### A. `scripts/export_demo_assets.py`（先做这个，是前端的燃料）

一次性脚本，把 CLI 真实产物 + 真实投影坐标导出成前端可直接 fetch 的静态 JSON：

| 产物 | 内容 | 生成方式 |
|---|---|---|
| `static/demo.json` | `{itinerary, timeline, mode, budget}` | `cli.py --days 3 --budget 3000 --tags 美食,文化 --json` 的真实输出 |
| `static/demo-revised.json` | 同结构，另一组参数 | `cli.py --days 3 --budget 1200 --tags 美食 --json` 的真实输出 |
| `static/demo-geo.json` | `{"成都":[{id,name,city,lat,lng,x,y}], "重庆":[...]}` | 读 `server/data/pois.json`，用 `server/tools/geo.py` 的 `Projector` **按城分别**投影 |

要求：
- 复用 `server/tools/geo.py` 的 `Projector`，**前端不自己算投影**（口径唯一）
- 投影时**成渝各建一个 Projector**（详见"双城分图"一节）
- 脚本必须打印每个产物的路径、字节数与 SHA-256
- 产物必须是**真实运行结果**，不许手写任何一个字段
- 提供 `--out` 参数指定输出目录，默认 `static/`

### B. `static/` 前端

```
static/
├── index.html
├── style.css
├── demo.json / demo-revised.json / demo-geo.json   （由 A 生成）
└── js/
    ├── api.js        数据源适配层（★ 核心，见下）
    ├── map.js        双城 SVG 路线图
    ├── timeline.js   逐日行程区
    ├── player.js     可倒带事件回放器
    └── main.js       装配与状态
```

---

## 接口契约（`api.js` 必须导出这 6 个方法，后端将来严格照此实现）

```js
// static/js/api.js
export const api = {
  async health(),                                  // → {status, mode, llm}
  async plan({days, budget, tags, family}),        // → {plan_id, itinerary, timeline, mode, budget}
  async stream(req, onEvent),                      // → 逐条回调 {seq,stage,type,title,reason,detail}；最后回调 {type:"done"}；返回 {unsubscribe()}
  async revise(plan_id, message),                  // → {itinerary, timeline, revised_day, message}
  async geo(plan_id, city),                        // → {points:[{id,name,city,lat,lng,x,y}], cities:[...]}
  async meta(),                                    // → {cities:[...], tags:[...], meta:{...}}
};
```

### `api.js` 的三种实现（运行时自动选择，UI 无感）

| 实现 | 触发条件 | 行为 |
|---|---|---|
| `LiveApi` | `GET /api/health` 在 **2 秒内**返回 200 | 真 `fetch` + SSE（`fetch` + `ReadableStream` 手工解析 `data: ` 帧，因为流式端点是 POST，`EventSource` 不支持 POST） |
| `MockApi` | health 超时 / 报错 / 返回非 200 | 从 `demo.json` 读数据；`stream()` 用 `setTimeout` 按 `seq` 顺序把 `timeline` 逐条推给 `onEvent`（**间隔 350ms，可加速到 120ms**，让"实时流式"的手感成立）；`revise()` 切换到 `demo-revised.json` 并把该份数据的时间线接在原时间线之后（模拟"用户介入"的第二幕） |
| 切换提示 | 走了 MockApi | 顶部显示徽标「本地演示数据（后端未启动）」 |

**关键要求**：
- `MockApi.stream()` 推的事件必须与 `LiveApi` **同构**（同一套字段、同一顺序、同样以 `done` 收尾）
- 上层代码（map / timeline / player）**不允许出现任何 `if (mock)` 的分支**——只能通过 `api` 这一层区分
- 真实后端接上后，`LiveApi` 必须能直接工作，**前端代码零改动**

---

## 一、页面结构

单页，两栏。目标 1440×900，同时保证 1366×768 不塌。

```
┌─────────────────────────────────────────────────────────────┐
│  蜀道智行 · 成渝行程规划智能体     [离线] [本地演示数据/●已连接] │
├──────────────────────────────────────┬──────────────────────┤
│  参数条：天数/预算/偏好标签/亲子 + 开始 │  Agent 决策回放        │
│  ──────────────────────────────────  │  ┌────────────────┐  │
│  双城路线图（成都 SVG │ 重庆 SVG）      │  │ ◀ ▶ ▶‖  进度条  │  │
│  ──────────────────────────────────  │  ├────────────────┤  │
│  逐日行程（Tab: Day1 Day2 Day3）      │  │ #012 plan 决策 │  │
│  卡片流：时间/点位/入选理由/文案        │  │ 因为 …         │  │
│                                       │  └────────────────┘  │
├──────────────────────────────────────┴──────────────────────┤
│  对话改行程： [ 输入框… ] [ 发送 ]   提示：第二天太赶            │
└─────────────────────────────────────────────────────────────┘
```

## 二、设计方向（严格按此实现，不要自行发挥）

- 深色底：背景 `#0E1116`，面板 `#161B22`，描边 `#30363D`，正文 `#E6EDF3`，次要 `#8B949E`
- 双城双色：成都 `#E8A33D`（暖橙），重庆 `#4EA8DE`（江蓝）；跨城高铁用双色渐变
- 状态色：违规 `#F85149`，通过 `#3FB950`，工具调用 `#A371F7`
- 字体：中文 `system-ui,"PingFang SC","Microsoft YaHei"`；事件流与时间用等宽 `ui-monospace,"JetBrains Mono",Consolas`
- 1px 描边 + 极轻层次差，**不用厚重阴影与玻璃拟态**；圆角 8px；留白克制
- 图标用内联 SVG 或纯字符，**不用图标字体或图片外链**

## 三、双城 SVG 自绘路线图

### 为什么必须分两幅图

成渝直线距离约 250km。40 个 POI 里两城各半，若投影到**同一张 1000×700 画布**，成都的点会挤成一小团。
因此：**成渝各一张 SVG，各用各的 Projector**（`demo-geo.json` 已按城分开存好坐标）。
两图之间画一条 **"成渝高铁"连接线**：成都图右缘 → 重庆图左缘，标注 `1.8h` 与 `¥154`，虚线 + 流动光点动效。

### 图内要素

1. **点位 marker**：按类型定大小（`must_see` 稍大），填充城市主色；hover 显示名称/门票/开放时间/爬坡强度
2. **当日路线连线**：按 `items` 顺序连线（**只取 `type=="poi"` 的条目**，`meal`/`intercity` 不画点）
3. **天序标记**：起点 `D1`、终点 `D3`；当天线路加粗高亮，非当天淡出
4. **跨城段**：单独画高铁线
5. 坐标直接用 `demo-geo.json` 的 `x`/`y`，**前端不重算投影**

### 交互

- 切换天 → 该天路线高亮、其余淡出；对应 marker 放大
- 点击 marker → 显示点位详情卡
- 回放进行中 → marker 随事件推进逐步点亮，未到达为灰

## 四、逐日行程区

- Tab 切天。条目三类分别渲染：
  - `poi`：时间区间、名称、门票（免费则不显示）、`visit_hours`、**入选理由**（`reasons` 数组渲染成小标签，这是"可解释"的落点）、`summary` 一句话
  - `meal`：餐次，弱化样式
  - `intercity`：高铁，跨城渐变条
- 每底部显示当天负载 `hours` / `intensity` / `tickets`；`intensity > 8.5` 用状态色标红（与后端 V3 规则一致）
- 显示当天 `narrative`（叙事段文案），排版成导览词而非普通正文
- 底部固定预算条：`tickets + meals + transit = total`，超用户预算标红

## 五、可倒带时间轴（核心差异化，务必做扎实）

数据源：`timeline` 数组，每条 `{seq, stage, type, title, reason, detail}`。

- **播放器**：进度条（可拖）、播放/暂停、单步前进/后退、跳到首尾、倍速（1x/2x/4x）
- **回放语义**：进度 = 当前已发生到第几条事件。回放到第 k 条时：
  - 事件列表第 k 条高亮，之前淡显，之后灰掉
  - **地图与行程卡同步回到第 k 条事件发生时的状态**（例如事件是"第2天选点3个"，此刻地图上就该只有这 3 个点；事件是"校验通过"，此刻才显示完整行程）
  - 实现：用事件类型 → 视图更新的映射表推进。**做不到精确 diff 的部分用"高亮 + 说明"表达，不要假装能做到**
- **事件列表**：按 `stage`（plan / validate / revise / narrate / system）分组着色；每条显示 `seq`、图标、`title`、**`reason`（全场最重要的一列，用次要色缩进显示）**
- **点联动**：点击事件 → 从 `detail` 里解析 poi id 就高亮对应点位，解析不出就跳过
- **事件类型图标**：`start ▶ / thought ◌ / tool_call ⚙ / tool_result ✓ / decision ◆ / violation ✗ / fix ↻ / pass ✔ / done ■ / fallback ▽ / advisory ⚠ / unfixable ⊘`（与 `cli.py` 的 `TYPE_MARK` 保持一致；`advisory` 与 `unfixable` 是 Prompt 01B 新增的类型）
- **软硬分级的视觉区分**（Prompt 01B 引入）：
  - `violation`（硬违规）→ 红色 `#F85149`，**会触发修复回流**，前端应把它和随后的 `fix` 事件在视觉上关联起来
  - `advisory`（软提醒，如强度超标）→ 琥珀色 `#D29922`，**不触发修复**，是一个独立的信息节点，不要画成错误
  - `unfixable`（有硬违规但无自动修复策略）→ 橙红 `#DB6D28`，表示"系统如实标注并停止重试"
  - 校验通过事件 `pass` → 绿色 `#3FB950`
- **重复事件的处理**：正常情况下事件流不应出现内容完全相同的连续违规。若出现（历史数据或异常），前端仍应正常渲染，但不要把它渲染成"卡住"的样子
- 搜索框：按 `title`/`reason` 过滤事件（推荐，演示时很有用）

## 六、对话式改行程（mock 与真实各一套实现）

- 输入框 + 发送按钮，示例提示语点击即填入：`第二天太赶` / `第一天太松了` / `换掉九眼桥` / `把宽窄巷子放最前面`
- 调用 `api.revise(plan_id, message)`：
  - **真实后端**（Prompt 02 实现）：后端只重排那一天，返回新的 `itinerary` + `timeline`
  - **Mock 模式**：切换到 `demo-revised.json`（预算更紧的真实行程），并把它的 `timeline` **接在原时间线之后**，模拟"用户介入"的第二幕
- 两种模式下的 UI 行为必须一致：刷新行程区与地图；播放器上以 `stage=="revise"` 分组头做明显分隔
- Mock 模式下界面上注明「本地演示：切换到另一份真实行程」，**不要假装是真实重排**

## 七、兜底与演示稳定性（答辩保命，**不可省略**）

1. **后端未启动 → 自动进 Mock 模式**，顶部显示徽标，**所有交互仍然可用**（这不是"降级占位"，是完整可演示的第二条路径）
2. **SSE 中途失败** → 用 `plan()` 返回的 `timeline` 一次性填充播放器，回放功能不受影响
3. **URL 参数预置**：`/?days=3&budget=3000&tags=美食,文化&auto=1` → 加载即自动跑一次，方便录视频
4. **刷新不丢状态**：参数与当前行程存 `localStorage`，刷新后恢复

## 八、动效清单

- 路径描绘：`stroke-dasharray` + `stroke-dashoffset`
- marker 出现：scale + opacity，按 `items` 顺序 stagger ≈ 60ms
- 高铁流动：虚线 `stroke-dashoffset` 循环
- 事件入场：右侧列表逐条淡入（回放时按倍速控制）
- 数字滚动：预算总额从 0 count 到目标值
- **必须尊重 `prefers-reduced-motion: reduce`**，命中时全部动效降级为即时呈现
- 动效用 **CSS transition/animation 或 Web Animations API**，不要引 GSAP/anime.js

---

## 九、交付要求

1. 交付 `scripts/export_demo_assets.py` 与 `static/` 全部文件
2. **贴出 `export_demo_assets.py` 的真实运行输出**（含三个产物的路径、字节数、SHA-256）
3. **自检清单**（逐条在浏览器点一遍，把结果写进回复）：
   - [ ] 改天数/预算/标签后能重新生成
   - [ ] 双城两张图，点位不重叠成一团，成都↔重庆有高铁连线
   - [ ] 切天时路线高亮联动
   - [ ] 播放器能播放/暂停/单步/拖动进度条
   - [ ] **拖动进度条时，行程卡内容随事件推进而变化**
   - [ ] 点击事件能高亮对应点位
   - [ ] `第二天太赶` 能改行程（Mock 与真实两套都能跑）
   - [ ] **后端完全没启动时，刷新页面仍能看到完整可演的 demo（带徽标）**
   - [ ] Mock 模式下事件是**逐条流式出现**的（有流式手感），不是一次性全出
   - [ ] 1366×768 下无横向滚动条、无元素重叠
   - [ ] `prefers-reduced-motion` 降级生效
4. 代码里不得出现任何硬编码的行程内容（全部来自 `demo*.json` 或接口）
5. 中文注释，风格与项目一致
6. **不要修改 `server/` 下任何文件**（后端是 Prompt 02 的范围）
