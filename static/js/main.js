// main.js — 装配与状态：参数条 / 地图 / 行程区 / 回放器 / 对话改行程 / URL 与持久化
// 视图状态机：回放第 k 条事件时的界面 = 依序 apply 前 k 条事件（见 applyEvent 映射表）。

import { api } from "./api.js";
import { CityMaps } from "./map.js";
import { DayPanel } from "./timeline.js";
import { Player } from "./player.js";

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

// ── 视图状态机（回放语义的落点）────────────────────────────────
function freshView() {
  return {
    revealed: new Map(),     // day → Set(poi_id)  已揭示点位
    activeDay: 1,
    advisories: new Map(),   // day → 软提醒事件
    violations: new Map(),   // day → 硬违规事件
    removed: new Map(),      // day → Set(poi_id)  被规则移除的点位（F2：地图灰叉/行程卡删除线联动）
    narrated: new Set(),     // 已生成导览词的天
    finished: false,         // 管线完成
    fixes: [],               // 修复动作记录
  };
}

function applyEvent(view, ev) {
  if (ev.type === "decision") {
    let m = ev.title.match(/第(\d+)天选点/);
    if (m) {
      const day = +m[1];
      view.revealed.set(day, new Set(Array.isArray(ev.detail) ? ev.detail : []));
      view.activeDay = day;
    }
  } else if (ev.type === "violation") {
    if (ev.detail && ev.detail.day) view.violations.set(ev.detail.day, ev);
  } else if (ev.type === "advisory") {
    if (ev.detail && ev.detail.day) view.advisories.set(ev.detail.day, ev);
  } else if (ev.type === "fix") {
    view.fixes.push(ev);
    // F2：fix 事件 detail.removed 携带被移除 poi_id → 写入 view.removed
    const m = ev.title.match(/第(\d+)天/);
    if (m && ev.detail && Array.isArray(ev.detail.removed)) {
      const day = +m[1];
      if (!view.removed.has(day)) view.removed.set(day, new Set());
      ev.detail.removed.forEach(id => view.removed.get(day).add(id));
    }
  } else if (ev.type === "done" && ev.stage === "narrate") {
    const m = ev.title.match(/第(\d+)天文案/);
    if (m) view.narrated.add(+m[1]);
  } else if (ev.type === "done" && ev.stage === "system") {
    view.finished = true;
  }
  return view;
}

function viewAt(cursor, events) {
  let view = freshView();
  for (let i = 0; i < cursor && i < events.length; i++) applyEvent(view, events[i]);
  return view;
}

// ── 渲染 ─────────────────────────────────────────────────────
const dayPanel = new DayPanel(day => { state.activeDay = day; renderAll(); });

function renderAll(cursor = state.player ? state.player.cursor : state.events.length) {
  const view = viewAt(cursor, state.events);
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
  },
  onEventClick: ev => {
    // 点联动：从 detail 解析 poi id
    const detail = ev.detail;
    const ids = [];
    if (Array.isArray(detail)) ids.push(...detail);
    if (detail && typeof detail === "object" && detail.poi) ids.push(detail.poi);
    for (const id of ids) {
      state.maps?.highlight(id);
      dayPanel.highlightPoi(id);
    }
  },
});

// ── 顶部徽标 ────────────────────────────────────────────────
function setBadge() {
  const b = $("badge-api");
  if (api.kind() === "live") {
    b.textContent = "● 已连接后端";
    b.classList.add("badge-live");
  } else {
    b.textContent = "本地演示数据（后端未启动）";
  }
}

// ── 主流程 ──────────────────────────────────────────────────
async function loadGeo() {
  const res = await api.geo(state.planId, null);
  state.maps = new CityMaps(res.points, p => {
    // 点击点位：跳到含它的那一天 + 行程卡高亮
    if (state.itinerary) {
      const d = state.itinerary.days.find(x => x.items.some(it => it.poi_id === p.id));
      if (d) { state.activeDay = d.day; renderAll(); dayPanel.highlightPoi(p.id); }
    }
  });
}

async function run() {
  const req = readParams();
  saveParams(req);
  $("btn-run").disabled = true;
  try {
    const res = await api.plan(req);
    state.planId = res.plan_id || "mock-1";
    state.itinerary = res.itinerary;
    state.budget = res.budget;
    state.events = [];
    state.player.setEvents([]);
    renderAll(0);
    // F5：流式期间进入"实时跟随"态——播放器控件禁用置灰，避免 cursor 与新事件打架
    setStreaming(true);
    // 流式推进事件；失败则一次性用 plan 返回的 timeline 填充（兜底2）
    try {
      await api.stream(req, ev => {
        if (ev.type === "done") { setStreaming(false); state.player.seek(state.events.length); return; }
        if (ev.type === "error") throw new Error("stream error");
        state.events.push(ev);
        state.player.appendEvents([ev]);
        renderAll(state.events.length);
      });
    } catch {
      setStreaming(false);
      state.events = res.timeline;
      state.player.setEvents(res.timeline, res.timeline.length);
    }
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

async function revise(message) {
  if (!state.itinerary) return;
  $("btn-send").disabled = true;
  try {
    const res = await api.revise(state.planId, message);
    state.itinerary = res.itinerary;
    state.budget = res.budget;
    state.events = res.timeline;
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
  return {
    days: +$("p-days").value || 3,
    budget: +$("p-budget").value || 3000,
    tags: $("p-tags").value.split(",").map(s => s.trim()).filter(Boolean),
    family: $("p-family").checked,
  };
}

function applyParams(q) {
  if (q.days) $("p-days").value = q.days;
  if (q.budget) $("p-budget").value = q.budget;
  if (q.tags) $("p-tags").value = Array.isArray(q.tags) ? q.tags.join(",") : q.tags;
  if (q.family != null) $("p-family").checked = !!q.family;
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
  await api.health();           // 懒选择在此触发
  setBadge();
  await loadGeo();
  const q = restoreParams();
  applyParams(q);

  $("params-form").addEventListener("submit", e => { e.preventDefault(); run(); });
  $("btn-send").addEventListener("click", () => { const v = $("chat-input").value.trim(); if (v) { revise(v); $("chat-input").value = ""; } });
  $("chat-input").addEventListener("keydown", e => { if (e.key === "Enter") $("btn-send").click(); });

  // 示例提示语（点击即填）
  const hints = ["第二天太赶", "第一天太松了", "换掉九眼桥", "把宽窄巷子放最前面"];
  const hintEl = $("chat-hints");
  hintEl.textContent = "试试：";
  for (const h of hints) {
    const s = document.createElement("span");
    s.textContent = h;
    s.addEventListener("click", () => { $("chat-input").value = h; });
    hintEl.appendChild(s);
  }

  // 底部抽屉开关（第八轮新增：按钮 / 关闭钮 / Esc / 遮罩，四种路径）
  const drawerBtn = document.getElementById("drawer-btn");
  drawerBtn?.addEventListener("click", () => {
    const open = document.body.classList.toggle("drawer-open");
    drawerBtn.setAttribute("aria-expanded", open ? "true" : "false");
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

  if (q.auto === "1" || q.auto === 1) run();
}


boot().catch(err => {
  console.error(err);
  const b = $("badge-api");
  b.textContent = "初始化失败（请检查 static/ 资产是否已生成）";
});