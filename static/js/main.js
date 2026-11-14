// main.js — 装配与状态：参数条 / 地图 / 行程区 / 回放器 / 对话改行程 / URL 与持久化
// 视图状态机在 view.js（纯函数）：回放第 k 条事件时的界面 = 依序 apply 前 k 条事件。

import { api } from "./api.js";
import { CityMaps } from "./map.js";
import { DayPanel } from "./timeline.js";
import { Player } from "./player.js";
import { applyParseResult, describeParse } from "./parsefill.js";
import { payload, viewAt } from "./view.js";
import { enableDragScroll } from "./dragscroll.js";

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = id => document.getElementById(id);

const state = {
  planId: null,
  itinerary: null,
  budget: null,
  events: [],
  maps: null,
  activeDay: 1,
};

// 03K 深链：?seq=N 在管线跑完后定位到第 N 条事件（隐式 auto=1）。只在首次 run 生效。
let pendingSeq = null;

// 03M 任务A 拍摄模式：?shot=<name> 管线跑完直接停在指定拍摄状态（隐式 auto=1）。
// 只复用现有函数（seek/renderAll/revise/drawer-open），不新增视图逻辑、不动 CSS——
// 「加了参数，画面和现在一模一样」，人只需要按截图键。只在首次 run 生效。
const SHOT_NAMES = ["overview", "map", "player", "replay", "chat", "budget"];
let pendingShot = null;


// ── 渲染 ─────────────────────────────────────────────────────
const dayPanel = new DayPanel(day => { state.activeDay = day; renderAll(); });

function renderAll(cursor = state.player ? state.player.cursor : state.events.length) {
  const view = viewAt(cursor, state.events);
  // 天状态单源：state.activeDay 为准（手动点tab/回放seek/流式decision 都先写它）。
  // 修复：此前 { activeDay: state.activeDay, ...view } 的后展开使 view.activeDay
  // （回放状态机里最后一条 decision 的天）覆盖手动选择 → Day tab 点击永远无效。
  view.activeDay = state.activeDay;
  // 完成时全部揭示（管线收尾语义）
  if (view.finished && state.itinerary) {
    for (const d of state.itinerary.days) {
      if (!view.revealed.has(d.day)) {
        view.revealed.set(d.day, new Set(d.items.filter(it => it.type === "poi").map(it => it.poi_id)));
      }
    }
  }
  state.maps?.render({ itinerary: state.itinerary, ...view });
  // F2：removed 的 id → 名称，供行程卡显示"✕ 被规则移除"
  const removedNames = new Map();
  for (const [day, ids] of (view.removed || new Map())) {
    removedNames.set(day, [...ids].map(id => state.maps?.index[id]?.point.name || id));
  }
  dayPanel.render(state.itinerary, { activeDay: state.activeDay, ...view, removedNames });
  renderBudgetCount(state.budget, view.finished);
  // 核心卖点可发现性：管线完成后给「Agent 决策回放」按钮一次性高亮引导（打开抽屉后解除）
  if (view.finished) $("drawer-btn")?.classList.add("attn");
}

let budgetAnim = null;
function renderBudgetCount(budget, finished) {
  if (!budget) return;
  const el = $("budget-bar");
  if (REDUCED || !finished) return;   // 未走完管线时不打扰（渲染交给 dayPanel）
  const from = 0, to = budget.total, t0 = performance.now();
  cancelAnimationFrame(budgetAnim);
  const step = now => {
    const p = Math.min(1, (now - t0) / 600);
    const val = Math.round(from + (to - from) * p);
    const total = el.querySelector(".total");
    if (total) total.textContent = `¥${val}`;
    if (p < 1) budgetAnim = requestAnimationFrame(step);
  };
  budgetAnim = requestAnimationFrame(step);
}

// ── 播放器 ──────────────────────────────────────────────────
state.player = new Player({
  onSeek: (cursor, events) => {
    state.activeDay = viewAt(cursor, events).activeDay || state.activeDay;
    renderAll(cursor);
    // 03K 深链：URL 带 seq 时，cursor 同步写回地址栏（replaceState 不产生历史条目，
    // 否则用户按返回键会连退 N 次）；不带 seq 的普通模式行为零变化
    syncSeqParam(cursor);
  },
  onEventClick: ev => {
    // 点联动：从 detail 解析 poi id（嵌套/扁平统一走 payload 解包）
    const vd = payload(ev);
    const ids = [];
    if (Array.isArray(vd)) ids.push(...vd);
    if (vd && typeof vd === "object" && vd.poi) ids.push(vd.poi);
    for (const id of ids) {
      state.maps?.highlight(id);
      dayPanel.highlightPoi(id);
    }
  },
});

// ── 顶部徽标 ────────────────────────────────────────────────
function setBadge(h) {
  const b = $("badge-api");
  if (api.kind() === "live") {
    b.textContent = "● 已连接后端";
    b.classList.add("badge-live");
    $("badge-offline").textContent = h?.mode === "online" ? "LLM 在线" : "引擎离线";
  } else {
    b.textContent = "本地演示数据（后端未启动）";
    $("badge-offline").textContent = "演示数据";
  }
}

// ── 主流程 ──────────────────────────────────────────────────
const DEFAULT_CITIES = ["成都", "重庆"];   // 默认演示仍是成渝（数据最扎实；城市多选是可选增强）

async function loadGeo() {
  const res = await api.geo(state.planId, null);
  state.cityMeta = res.city_meta || {};
  state.maps = new CityMaps(res.points, p => {
    // 点击点位：跳到含它的那一天 + 行程卡高亮
    if (state.itinerary) {
      const d = state.itinerary.days.find(x => x.items.some(it => it.poi_id === p.id));
      if (d) { state.activeDay = d.day; renderAll(); dayPanel.highlightPoi(p.id); }
    }
  });
  state.maps.setCities(DEFAULT_CITIES, state.cityMeta);
}

/** 行程涉及城市（按天数首次出现序）→ 动态重建图幅卡 */
function syncMapCities() {
  if (!state.itinerary?.days?.length || !state.maps) return;
  const cities = [...new Set(state.itinerary.days.map(d => d.city))];
  state.maps.setCities(cities, state.cityMeta || {});
  updateScrollHint(cities.length);
}

/** >2 城时图幅容器内横滚——给「右侧还有城市」的可见提示 */
function updateScrollHint(n) {
  const hint = $("map-scroll-hint");
  if (hint) hint.hidden = n <= 2;
}

async function run() {
  const req = readParams();
  saveParams(req);
  $("btn-run").disabled = true;
  try {
    state.planId = null;
    state.itinerary = null;
    state.budget = null;
    state.events = [];
    state.player.setEvents([]);
    renderAll(0);
    // F5：流式期间进入"实时跟随"态——播放器控件禁用置灰，避免 cursor 与新事件打架
    setStreaming(true);
    // 任务A方案B：只跑一次 stream，行程随 plan_result 控制帧回来（与事件流必然同源）；
    // 旧路径 plan + stream 各跑一次独立管线，在线模式下既烧双份 token，
    // 非确定性（temp 0.3）下行程卡与事件流还会描述两个不同的行程
    let gotResult = false;
    await api.stream(req, ev => {
      if (ev.type === "plan_result") {
        gotResult = true;
        state.planId = ev.plan_id || "mock-1";
        state.itinerary = ev.itinerary;
        state.budget = ev.budget;
        syncMapCities();
        renderAll(state.events.length);
        updateChatPlaceholder();   // 有了计划 → 对话栏切到「改行程」语义
        return;
      }
      // 哨兵=纯 type 无 stage（API.md 口径）；业务 narrate/system 的 done 事件带 stage，须正常入流——
      // 吞掉它们会让事件数 < 后端 timeline，?seq=N 深链与 seq 契约随之错位
      if (ev.type === "done" && ev.stage === undefined) { setStreaming(false); state.player.seek(state.events.length); return; }
      if (ev.type === "error") throw new Error("stream error");
      state.events.push(ev);
      // 流式直播跟随：新一天的选点决策到达时同步当前天（天状态单源 state.activeDay）
      if (ev.type === "decision") {
        const m = ev.title.match(/第(\d+)天选点/);
        if (m) state.activeDay = +m[1];
      }
      state.player.appendEvents([ev]);
      renderAll(state.events.length);
    });
    setStreaming(false);
    // 兜底：流正常结束却没收到 plan_result（异常路径）——退回一次性 plan 补齐，
    // 宁可此场景双跑也不要白屏（与 run() 顶层 catch 的红字兜底同原则）
    if (!gotResult && !state.itinerary) {
      const res = await api.plan(req);
      state.planId = res.plan_id || "mock-1";
      state.itinerary = res.itinerary;
      state.budget = res.budget;
      state.events = res.timeline;
      state.player.setEvents(res.timeline, res.timeline.length);
      syncMapCities();
    }
    renderAll(state.events.length);
    // 03K 深链：流结束（或兜底 plan）后按 ?seq=N 定位——在 done 帧的 seek(length)
    // 之后执行，覆盖其结果；之后 pendingSeq 置空，手动重跑不再定位
    if (pendingSeq != null) applyDeepLinkSeq();
    // 03M 任务A：?shot=<模式> 在管线跑完后进入指定拍摄状态（seq 优先于 shot——
    // 两者同带时按 seq 定位，shot 忽略，boot 里已 console 说明）
    else if (pendingShot) await applyShot(pendingShot);
  } catch (err) {
    // 可见的失败：宁可红字报错，也不要白屏（答辩现场白屏等于 0 分）
    console.error(err);
    const b = $("badge-api");
    b.textContent = "规划失败：" + (err?.message || err);
    b.classList.add("badge-error");
  } finally {
    $("btn-run").disabled = false;
  }
}

/** 流式跟随态：禁用回放控件 + 置灰 + 顶栏提示，流结束恢复"可回放" */
function setStreaming(on) {
  document.querySelector(".player-ctrl").classList.toggle("streaming", on);
  for (const id of ["pc-play", "pc-prev", "pc-next", "pc-first", "pc-last", "pc-seek"]) {
    $(id).disabled = on;
  }
  $("badge-offline").textContent = on ? "实时接收中…" : "离线";
}

// ── 03K 深链 ?seq=N：管线跑完定位到第 N 条事件 ──────────────────
// 走与手动拖进度条完全相同的路径（player.seek）；越界落到最后一步并如实提示。
function applyDeepLinkSeq() {
  const n = pendingSeq;
  pendingSeq = null;   // 深链定位只消费一次（之后的重跑/改行程走默认行为）
  if (!state.events.length) return;
  state.player.seek(Math.min(n, state.events.length));
  if (n > state.events.length) {
    const hint = $("params-hint");
    if (hint) {
      hint.textContent = `seq=${n} 超出范围（本次规划共 ${state.events.length} 条事件），已定位到最后一步`;
      hint.hidden = false;
    }
  }
}

/** URL 带 seq 时，把 cursor 写回地址栏（replaceState：可分享精确位置，不污染浏览器历史） */
function syncSeqParam(cursor) {
  const u = new URLSearchParams(location.search);
  if (!u.has("seq")) return;
  u.set("seq", String(Math.max(1, cursor)));
  history.replaceState(null, "", `${location.pathname}?${u.toString()}`);
}

// ── 03M 任务A：拍摄模式 ?shot=<name> ────────────────────────────
// 六个状态全部复用现有函数；到位后只在 <html data-shot> 上做标记（控制台可见），
// 界面不显示任何提示文字（它会进截图）。CSS 零改动。
async function applyShot(name) {
  const shot = pendingShot;
  pendingShot = null;              // 只消费一次（重跑/改行程走默认行为）
  document.documentElement.dataset.shot = name;   // 控制台查 document.documentElement.dataset.shot
  const evs = state.events;
  const scrollInto = (sel, block) => document.querySelector(sel)?.scrollIntoView({ block, behavior: "instant" });

  if (shot === "overview") {
    // 全页稳定态：抽屉关闭 → Day 1 → 页顶
    document.body.classList.remove("drawer-open");
    state.activeDay = 1;
    renderAll(state.events.length);
    scrollInto(".layout", "start");
  } else if (shot === "map") {
    // 地图区视口内 + 全部点位点亮（跑完即全亮——tooltip 需人工悬停，README 已如实标注）
    document.body.classList.remove("drawer-open");
    state.activeDay = 1;
    renderAll(state.events.length);
    scrollInto(".map-row", "center");
  } else if (shot === "player") {
    // 抽屉展开 + 事件列表滚入视口（当前项焦点在末尾，与手动展开观感一致）
    document.body.classList.add("drawer-open");
    state.player.seek(evs.length);
    scrollInto(".evt-list", "center");
  } else if (shot === "replay") {
    // 中段（约 60% 处最近的一条 decision）：与 ?seq 完全同一条 seek 路径 + 抽屉展开
    const half = Math.ceil(evs.length * 0.5);
    let n = evs.find(e => e.type === "decision" && e.seq >= half)?.seq;
    if (n == null) {
      const decs = evs.filter(e => e.type === "decision");
      n = decs.length ? decs[decs.length - 1].seq : evs.length;
    }
    document.body.classList.add("drawer-open");
    state.player.seek(n);          // 与手动拖进度条/深链同一路径；地图随 cursor 点亮
    await new Promise(r => setTimeout(r, 60));   // 等 renderAll 一帧
    document.querySelector(".evt.cur")?.scrollIntoView({ block: "center", behavior: "instant" });
  } else if (shot === "chat") {
    // 真实发一次「第二天太赶」（走与人工完全相同的 revise()）→ 抽屉展开读第二幕
    // 不伪造第二幕事件——塞进 state 的是假画面，评委一点就穿帮
    await revise("第二天太赶");
    document.body.classList.add("drawer-open");
    await new Promise(r => setTimeout(r, 120));  // 等 revise 重建与 seek 完成
    scrollInto(".evt-list", "center");
  }
  // budget：无独立到位逻辑——它只是 URL 预置预算 900 跑完（镜 11 违规修复场景），
  // boot 里已把 budget 参数写进表单，run() 完成态即所需画面
}

// ── 对话栏双模式（03G）：无计划=自然语言规划入口，有计划=改行程（revise 语义零变化）──

const PLACEHOLDER_PLAN = "说说你想怎么玩，例如：我在北京，想去成都和重庆玩3天，喜欢美食和夜景";
const PLACEHOLDER_REVISE = "和规划师说点什么，例如：第二天太赶";

function updateChatPlaceholder() {
  const el = $("chat-input");
  if (el) el.placeholder = state.planId ? PLACEHOLDER_REVISE : PLACEHOLDER_PLAN;
}

/** 对话栏回一条系统提示（「我理解为…」/兜底说明），不报错不清参数 */
function setChatNote(text) {
  const el = $("chat-note");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}

/** 无计划时发送一句话：抽取 → 回填参数条（回填不替换：未识别字段保留原值）
 *  → 对话栏展示「我理解为…」→ 自动触发规划。参数条上的值仍可见可改。
 *  03J 记忆分支：「记住/忘掉/查看偏好」不触发规划——对话栏回 note，
 *  操作的事件流（已记住/已忘掉，带 reason）进回放器，评委看得到记忆起作用了。 */
async function planByChat(message) {
  $("btn-send").disabled = true;
  try {
    const r = await api.parse(message);
    if (r.remember || r.forget || r.view) {
      setChatNote(r.note);
      if (Array.isArray(r.timeline) && r.timeline.length) {
        state.events = r.timeline;
        state.player.setEvents(r.timeline, r.timeline.length);
        renderAll(state.events.length);
      }
      return;
    }
    const got = r.days || r.budget || r.cities?.length || r.tags?.length;
    if (r.source === "fallback" || !got) {
      setChatNote("没太看懂，也可以直接用上方参数条填写" + (r.note ? `；${r.note}` : ""));
      return;
    }
    applyParseResult(r, {
      cityBoxes: () => [...document.querySelectorAll("#p-cities input")],
      onHint: updateCityDayHint,
    });
    setChatNote(describeParse(r));
    await run();     // 回填后直接规划（流畅优先）；参数条值仍可见、可改后重新点「开始规划」
  } catch (err) {
    console.error(err);
    setChatNote("没太看懂（" + (err?.message || err) + "），也可以直接用上方参数条填写");
  } finally {
    $("btn-send").disabled = false;
  }
}

async function revise(message) {
  if (!state.itinerary) return;
  $("btn-send").disabled = true;
  try {
    const res = await api.revise(state.planId, message);
    state.itinerary = res.itinerary;
    state.budget = res.budget;
    state.events = res.timeline;
    syncMapCities();
    // F1：先算目标 cursor 再一次性 setEvents+seek，避免按旧 cursor 先闪一帧；
    // cursor 语义=前 k 条已生效，divider（stage=revise）本身要生效须 cut+1
    const cut = state.events.findIndex(e => e.stage === "revise");
    const target = cut >= 0 ? cut + 1 : state.events.length;
    state.player.setEvents(res.timeline, target);
  } catch (err) {
    // 与 run() 同款可见兜底：改行程失败上徽标，不静默
    console.error(err);
    const b = $("badge-api");
    b.textContent = "改行程失败：" + (err?.message || err);
    b.classList.add("badge-error");
  } finally {
    $("btn-send").disabled = false;
  }
}

// ── 参数读写 ────────────────────────────────────────────────
function readParams() {
  const cityBoxes = [...document.querySelectorAll("#p-cities input:checked")].map(i => i.value);
  return {
    days: +$("p-days").value || 3,
    budget: +$("p-budget").value || 3000,
    tags: $("p-tags").value.split(",").map(s => s.trim()).filter(Boolean),
    family: $("p-family").checked,
    cities: cityBoxes,   // 空数组 = 按候选池总分自动选城
  };
}

function applyParams(q) {
  if (q.days) $("p-days").value = q.days;
  if (q.budget) $("p-budget").value = q.budget;
  if (q.tags) $("p-tags").value = Array.isArray(q.tags) ? q.tags.join(",") : q.tags;
  if (q.family != null) $("p-family").checked = !!q.family;
  if (Array.isArray(q.cities)) {
    for (const box of document.querySelectorAll("#p-cities input")) {
      box.checked = q.cities.includes(box.value);
    }
  } else if (typeof q.cities === "string" && q.cities) {
    // URL 透传形如 ?cities=成都,重庆（首页 passThrough 转来的字符串）
    const sel = q.cities.split(",").map(s => s.trim()).filter(Boolean);
    for (const box of document.querySelectorAll("#p-cities input")) {
      box.checked = sel.includes(box.value);
    }
  }
  updateCityDayHint();
}

/** 城市多选：默认勾选成渝（赛题版本默认演示），全不勾 = 自动选城 */
async function buildCityPicker() {
  const m = await api.meta();
  const box = $("p-cities");
  for (const c of m.cities) {
    const lab = document.createElement("label");
    lab.className = "chk";
    const inp = document.createElement("input");
    inp.type = "checkbox";
    inp.value = c;
    if (DEFAULT_CITIES.includes(c)) inp.checked = true;
    lab.append(inp, document.createTextNode(c));
    box.appendChild(lab);
  }
  box.addEventListener("change", updateCityDayHint);
  $("p-days").addEventListener("input", updateCityDayHint);
}

/** 勾选城市数 > 天数时的即时说明（行为 = 取候选池总分前 N 城，避免「为什么只出现两城」的困惑） */
function updateCityDayHint() {
  const hint = $("params-hint");
  if (!hint) return;
  const n = document.querySelectorAll("#p-cities input:checked").length;
  const days = +$("p-days").value || 3;
  if (n > days) {
    hint.textContent = `已选 ${n} 城但只有 ${days} 天：将按候选池总分取前 ${days} 城（建议天数 ≥ 城市数）`;
    hint.hidden = false;
  } else {
    hint.hidden = true;
  }
}

function saveParams(p) {
  try { localStorage.setItem("shudao-params", JSON.stringify(p)); } catch { /* 私密模式忽略 */ }
}

function restoreParams() {
  const u = new URLSearchParams(location.search);
  const q = Object.fromEntries(u.entries());
  if (Object.keys(q).length) return q;
  try { return JSON.parse(localStorage.getItem("shudao-params") || "{}"); } catch { return {}; }
}

// ── 启动 ────────────────────────────────────────────────────
async function boot() {
  const h = await api.health();   // 懒选择在此触发
  setBadge(h);
  await loadGeo();
  // 03M P2：必须 await 建完城市选框再回填参数——此前 buildCityPicker() 未 await，
  // applyParams 时 #p-cities 的 checkbox 可能尚未创建，URL 里的 cities 被静默丢弃
  // （真实网络下尤为明显：api.meta() 是异步的，勾选框晚于参数回填出现）
  await buildCityPicker();
  const q = restoreParams();
  applyParams(q);

  // 03I：两个横向滚动区域启用拖拽滚动（day-tabs 新增；map-row 锦上添花，不改宽度逻辑）
  enableDragScroll($("day-tabs"));
  enableDragScroll($("map-row"));
  window.addEventListener("resize", () => dayPanel.updateScrollHint());

  $("params-form").addEventListener("submit", e => { e.preventDefault(); run(); });
  $("btn-send").addEventListener("click", () => {
    const v = $("chat-input").value.trim();
    if (!v) return;
    $("chat-input").value = "";
    // 03G 双模式：还没有 plan_id = 一句话规划（抽取→回填→自动跑管线）；
    // 已有 plan_id = 对话改行程（走既有 /api/revise，行为零变化）
    if (state.planId) revise(v); else planByChat(v);
  });
  $("chat-input").addEventListener("keydown", e => { if (e.key === "Enter") $("btn-send").click(); });
  updateChatPlaceholder();

  // 03L 任务L6：决策报告导出——api.report 是唯一数据入口（Live=服务端 md /
  // Mock=本地 renderReport 同构生成），UI 不直接 fetch、无 if (mock) 分支
  $("btn-report")?.addEventListener("click", async () => {
    if (!state.planId) return;
    const btn = $("btn-report");
    btn.disabled = true;
    try {
      const md = await api.report(state.planId);
      const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `shudao-report-${state.planId}.md`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      // 与 run()/revise() 同款可见兜底：失败上徽标红字，不静默
      console.error(err);
      const b = $("badge-api");
      b.textContent = "导出报告失败：" + (err?.message || err);
      b.classList.add("badge-error");
    } finally {
      btn.disabled = false;
    }
  });

  // 示例提示语（点击即填）：无计划时的示例是「一句话规划」，与对话栏当前语义一致
  const hints = state.planId
    ? ["第二天太赶", "第一天太松了", "换掉九眼桥", "把宽窄巷子放最前面"]
    : ["我在北京，想去成都和重庆玩3天，喜欢美食和夜景", "带娃去昆明玩5天，预算5000", "从上海出发去大理和丽江玩4天"];
  const hintEl = $("chat-hints");
  hintEl.textContent = "试试：";
  for (const h of hints) {
    const s = document.createElement("span");
    s.textContent = h.length > 18 ? h.slice(0, 18) + "…" : h;
    s.title = h;
    s.addEventListener("click", () => { $("chat-input").value = h; });
    hintEl.appendChild(s);
  }

  // 底部抽屉开关（第八轮新增：按钮 / 关闭钮 / Esc / 遮罩，四种路径）
  const drawerBtn = document.getElementById("drawer-btn");
  drawerBtn?.addEventListener("click", () => {
    const open = document.body.classList.toggle("drawer-open");
    drawerBtn.setAttribute("aria-expanded", open ? "true" : "false");
    drawerBtn.classList.remove("attn");   // 用户已发现回放入口，解除引导高亮
  });
  document.getElementById("drawer-close")?.addEventListener("click", () => {
    document.body.classList.remove("drawer-open");
    drawerBtn?.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      document.body.classList.remove("drawer-open");
      drawerBtn?.setAttribute("aria-expanded", "false");
    }
  });
  // 遮罩点击关闭：抽屉外的遮罩区（body.drawer-open::after 不可绑事件，用一次性全局点击兜底）
  document.addEventListener("click", e => {
    if (!document.body.classList.contains("drawer-open")) return;
    const inDrawer = e.target.closest(".right, #drawer-btn");
    if (!inDrawer) {
      document.body.classList.remove("drawer-open");
      drawerBtn?.setAttribute("aria-expanded", "false");
    }
  });

  // 03K 深链：?seq=N 隐式 auto=1（带 seq 就是要看某一步，不该还要人再点一次开始）
  const seqN = Number.parseInt(q.seq, 10);
  if (Number.isFinite(seqN) && seqN >= 1) pendingSeq = seqN;

  // 03M 任务A：?shot=<拍摄模式>（隐式 auto=1；seq 优先于 shot——同带时按 seq 定位）
  if (q.shot && SHOT_NAMES.includes(q.shot)) {
    pendingShot = q.shot;
    if (pendingSeq != null) {
      // seq 优先：shot 忽略，console 说明（不进界面——提示会进截图）
      console.info(`[shot] URL 同时带 seq=${pendingSeq} 与 shot=${q.shot}：按 seq 定位，shot 忽略`);
      pendingShot = null;
    } else if (q.shot === "budget" && !q.budget) {
      // 镜 11 场景：预算 900 的违规修复叙事（只在未显式给 budget 时预置）
      $("p-budget").value = 900;
    }
  }

  if (q.auto === "1" || q.auto === 1 || pendingSeq != null || pendingShot != null) run();
  else renderAll(0);   // 非自动播放时先渲染空态引导（此前只有 auto 才 run，
                       // dayPanel.render(null) 从不触发 → 空态占位从未挂载、结果区一片空白）
}


boot().catch(err => {
  console.error(err);
  const b = $("badge-api");
  b.textContent = "初始化失败（请检查 static/ 资产是否已生成）";
});