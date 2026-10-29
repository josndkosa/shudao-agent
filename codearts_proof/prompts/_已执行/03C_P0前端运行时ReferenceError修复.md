# 码道 Prompt 03C · P0：前端运行时 ReferenceError（**点「开始规划」即白屏**）

> 用法：整段粘贴给码道（IDE 模式）。
> 这是一条 **P0 阻断级修复**，做完后前端才能真正跑起来。

---

## 症状

打开页面**不报错**，但**一点「开始规划」，行程区和事件流全空**，控制台抛未捕获异常。

---

## 根因：`static/js/player.js` 第 37–43 行

```js
setEvents(events) {                              // ← 签名只有一个参数
    this.events = events;
    this.seekEl.max = events.length;
    this._renderList();
    // 传 cursor 则直接定位目标（避免按旧 cursor 先闪一次旧画面）
    this.seek(cursor != null ? cursor : this.cursor);   // ← cursor 没有声明！
}
```

`cursor` **不是 `setEvents` 的参数**，在模块作用域里也**从未声明**（只有 `this.cursor` 这个实例属性）。
读取一个未声明的标识符，在任何 JS 模式下都会抛 **`ReferenceError: cursor is not defined`**。

所以 `setEvents()` **每次调用都炸**：

| 调用点 | 后果 |
|---|---|
| `main.js` `run()` → `state.player.setEvents([])` | 抛错 → `run()` 的 try 没有 catch → 未处理的 Promise rejection → **行程区空、事件流空** |
| `main.js` `revise()` → `state.player.setEvents(res.timeline, target)` | 同上，且第二个参数 `target` 也被静默丢弃 → F1 的修复**等于没生效** |
| `main.js` `run()` catch 分支 → `state.player.setEvents(res.timeline, res.timeline.length)` | 同上 |

**为什么初次打开不报错**：`boot()` 不调用 `setEvents()`，所以页面看起来正常；
一旦点「开始规划」才暴露。**这是最容易漏掉的一类 bug。**

**为什么 `node --check` 没抓到**：`--check` 只做**语法**检查，不做**未声明标识符**检查。
需要**运行时**验证。

---

## 修复

### 1. 补上参数（`static/js/player.js`）

```js
setEvents(events, cursor = null) {
  this.events = events;
  this.seekEl.max = events.length;
  this._renderList();
  // 传 cursor 则直接定位目标（避免按旧 cursor 先闪一次旧画面）
  this.seek(cursor != null ? cursor : this.cursor);
}
```

### 2. 顺手扫一遍 `static/js/` 里还有没有同类问题

**全量 grep 每一个裸标识符的使用点**，确认都有对应的声明（参数 / `const` / `let` / 类方法 / 全局）。
重点检查这轮改动过的文件：`player.js`、`main.js`、`map.js`、`timeline.js`、`api.js`。

**特别检查**：`map.js`、`timeline.js`、`main.js` 里新加的 `fmtHour`、`removedNames`、`setStreaming`、
`revisedDay`、`_diffDay`、`_lastItinerary` —— 确认每一个**引用处**和**声明处**拼写完全一致
（大小写 / 少个下划线 / 少个字母这种错，`node --check` 同样查不出来）。

### 3. 让错误**看得见**（`static/js/main.js`）

现在 `run()` 里的异常会变成未处理的 Promise rejection，用户只看到一片空白。
请给 `run()` 加 `catch`，把错误显示到顶部徽标上：

```js
} catch (err) {
  console.error(err);
  const b = $("badge-api");
  b.textContent = "规划失败：" + (err?.message || err);
  b.classList.add("badge-error");
} finally { ... }
```

**理由**：宁可红字报错，也不要白屏。答辩现场白屏等于 0 分，红字报错至少还能立刻定位。

---

## 验证要求（**这次必须做运行时验证，不能只 `node --check`**）

### A. 后端在跑的情况

```bash
python scripts/start_server.sh          # 或 start_server.bat
```
浏览器打开 `http://localhost:8000`，**点「开始规划」**，然后：

- [ ] **控制台零报错**（把空控制台截图贴出来）
- [ ] 行程区出现 3 天行程、逐日卡片、预算条
- [ ] 右侧事件流出现 22 条左右事件，**逐条出现**（流式）
- [ ] 拖动进度条 → 行程卡内容与地图点位同步回退
- [ ] 点某条事件 → 对应点位高亮
- [ ] 用 `--days 2 --budget 2000 --tags 夜景` 场景验证 **violation → fix → pass**：
      事件流里能看到移除事件，**地图上被移除的点变灰打叉**，行程卡上显示「✕ 被规则移除」
- [ ] 点「发送」输入"第二天太赶" → **第二幕的「用户介入」事件被选中**（F1 真正生效）

### B. 后端没跑的情况（答辩保命路径）

杀掉后端进程，刷新页面：

- [ ] 顶部徽标显示「本地演示数据（后端未启动）」
- [ ] 点「开始规划」→ **依然能出完整行程和事件流**（MockApi 路径）
- [ ] 改行程 → 第二幕正常
- [ ] 控制台零报错

### C. 一条最省事的冒烟脚本（可选，但建议做）

写一个 `scripts/smoke_frontend.mjs`（Node，无需任何依赖）：
用最小 DOM stub 加载 `static/js/*.js`，依次调用 `api.health()` → `api.plan(...)` →
`player.setEvents(events, 1)` → `player.setEvents(events)`，
**捕获并打印任何异常**。有异常 → 非零退出。

这能在一秒内挡住本次这类 bug，以后每次改前端都能跑。

---

## 交付要求

1. **贴出运行时验证证据**：A、B 两组自检的**控制台截图**（空控制台 + 页面正常渲染）
2. 如果加了 `scripts/smoke_frontend.mjs`，贴出它的**真实运行输出**
3. `python -m pytest -q` 仍全绿（用例数 ≥ 60，不得减少）
4. 把本次修复追加到 `codearts_proof/debug-log-2026-10-28.md`（**新开一节，不要覆盖已有内容**），
   重点写清「**为什么 `node --check` 查不出这类问题**」——这是很好的工程反思素材
5. 不要改动 `server/` 下任何文件（本条只动 `static/js/`）
6. 顺手确认 `static/` 里的 `demo*.json` 已是 01C 之后的版本（南山一棵树在、advisory 事件在）
