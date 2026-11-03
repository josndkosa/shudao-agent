// smoke_frontend.mjs — 前端运行时冒烟（零依赖，node scripts/smoke_frontend.mjs）
// 背景：node --check 只做语法检查，抓不到「未声明标识符」（如 setEvents 里的 cursor）。
// 本脚本用最小 DOM stub 真正加载 static/js 模块并执行关键路径，任何异常 → 非零退出。
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const STATIC = path.join(ROOT, "static");

// ── 最小 DOM stub（只实现被引用到的能力）──────────────────────
function makeEl() {
  const el = {
    textContent: "", value: "0", max: "0", disabled: false,
    style: { setProperty() {}, removeProperty() {} }, dataset: {}, innerHTML: "",
    classList: { _s: new Set(), add(...c) { c.forEach(x => this._s.add(x)); },
                 remove(...c) { c.forEach(x => this._s.delete(x)); },
                 toggle(c, on) { on === false ? this._s.delete(c) : this._s.add(c); } },
    addEventListener() {}, appendChild() {}, append() {}, replaceChildren() {},
    scrollIntoView() {}, animate() {}, querySelector() { return makeEl(); },
    querySelectorAll() { return []; }, setAttribute() {},
  };
  return el;
}
const elCache = new Map();
globalThis.document = {
  getElementById(id) { if (!elCache.has(id)) elCache.set(id, makeEl()); return elCache.get(id); },
  createElement() { return makeEl(); },
  createElementNS() { return makeEl(); },
  body: makeEl(),
  querySelector() { return makeEl(); },
};
globalThis.matchMedia = () => ({ matches: false });
globalThis.addEventListener = () => {};
globalThis.requestAnimationFrame = fn => setTimeout(fn, 0);
globalThis.cancelAnimationFrame = () => {};
globalThis.innerWidth = 1440;
globalThis.performance = { now: () => Date.now() };
globalThis.location = { search: "" };   // home.js passThrough 读取；空查询=不跳转

// fetch stub：/api/health 拒绝（强制走 MockApi 路径）；./demo*.json 读本地真实产物
globalThis.fetch = async url => {
  if (String(url).includes("/api/health")) throw new Error("no backend (smoke)");
  const name = String(url).replace(/^\.\//, "");
  const raw = readFileSync(path.join(STATIC, name), "utf8");
  return { ok: true, status: 200, json: async () => JSON.parse(raw) };
};

// ── 依次执行冒烟步骤，任何异常即失败 ─────────────────────────
const steps = [];
function step(name, fn) { steps.push([name, fn]); }

step("import api.js", async () => {
  const mod = await import(pathToFileURL(path.join(STATIC, "js", "api.js")));
  globalThis.__api = mod.api;
});
step("api.health()（Mock 选择）", async () => {
  const h = await globalThis.__api.health();
  if (h.status !== "ok") throw new Error("health 异常: " + JSON.stringify(h));
});
step("api.plan(...)", async () => {
  const r = await globalThis.__api.plan({ days: 3, budget: 3000, tags: ["美食", "文化"] });
  if (!r.itinerary?.days?.length) throw new Error("plan 无行程");
  if (!Array.isArray(r.timeline)) throw new Error("plan 无 timeline");
  globalThis.__events = r.timeline;
  globalThis.__itinerary = r.itinerary;   // 供 CityMaps.render 步用真实行程
});
step("import player.js + new Player", async () => {
  const { Player } = await import(pathToFileURL(path.join(STATIC, "js", "player.js")));
  globalThis.__player = new Player({ onSeek() {}, onEventClick() {} });
});
// 本轮 bug 的直接复现点：两种签名都必须不抛
step("player.setEvents(events, 1)", () => {
  globalThis.__player.setEvents(globalThis.__events, 1);
  if (globalThis.__player.cursor !== 1) throw new Error("cursor 未定位到 1");
});
step("player.setEvents(events)", () => {
  globalThis.__player.setEvents(globalThis.__events);
});
step("player.seek(3) / step(+1) / play 后 pause", () => {
  globalThis.__player.pause();
  globalThis.__player.seek(3);
  globalThis.__player.play();
  globalThis.__player.pause();
});
step("import map.js（fmtHour 路径）", async () => {
  const { CityMaps } = await import(pathToFileURL(path.join(STATIC, "js", "map.js")));
  const geo = JSON.parse(readFileSync(path.join(STATIC, "demo-geo.json"), "utf8"));
  globalThis.__maps = new CityMaps(geo, () => {});
});
step("CityMaps.setCities 动态挂载双城", () => {
  globalThis.__maps.setCities(["成都", "重庆"], { "成都": "CHENGDU · 30.67°N 104.07°E" });
  if (Object.keys(globalThis.__maps._layer).length !== 2) throw new Error("双城图幅未挂载");
});
step("view.js：decision 嵌套 detail → revealed 非空（P0 回归锁）", async () => {
  const { applyEvent, freshView } = await import(pathToFileURL(path.join(STATIC, "js", "view.js")));
  const evs = globalThis.__events.filter(e => e.type === "decision" && /第\d+天选点/.test(e.title));
  if (!evs.length) throw new Error("事件流无「第N天选点」事件（断言前提失败）");
  const ev = evs[0];
  if (!ev.detail || !Array.isArray(ev.detail.detail)) {
    throw new Error("测试前提失败：decision detail 非嵌套结构 " + JSON.stringify(ev.detail).slice(0, 80));
  }
  const day = +ev.title.match(/第(\d+)天选点/)[1];
  const inner = ev.detail.detail;
  const view = freshView();
  applyEvent(view, ev);
  const got = view.revealed.get(day);
  if (!got || got.size === 0) throw new Error("P0 回归：revealed 仍为空集（detail 层级读错）");
  for (const id of inner) if (!got.has(id)) throw new Error(`revealed 缺 poi ${id}`);
  if (view.activeDay !== day) throw new Error("activeDay 未跟随选点事件");
});
step("view.js：violation / advisory 嵌套 detail 按 day 落位", async () => {
  const { applyEvent, freshView, payload } = await import(pathToFileURL(path.join(STATIC, "js", "view.js")));
  const tl = JSON.parse(readFileSync(path.join(STATIC, "demo-revised.json"), "utf8")).timeline;
  let nV = 0, nA = 0;
  const view = freshView();
  for (const ev of tl) {
    if (ev.type !== "violation" && ev.type !== "advisory") continue;
    applyEvent(view, ev);
    const vd = payload(ev);
    if (!vd || !vd.day) throw new Error(`${ev.type} 载荷缺 day：` + JSON.stringify(vd).slice(0, 60));
    const sink = ev.type === "violation" ? view.violations : view.advisories;
    if (sink.get(vd.day) !== ev) throw new Error(`${ev.type} 第${vd.day}天未落位`);
    ev.type === "violation" ? nV++ : nA++;
  }
  if (!nV) throw new Error("demo-revised 无 violation（断言无效）");
  if (!nA) throw new Error("demo-revised 无 advisory（断言无效）");
});
step("view.js：fix 事件扁平 detail.removed → view.removed 含被移除 id", async () => {
  const { applyEvent, freshView } = await import(pathToFileURL(path.join(STATIC, "js", "view.js")));
  const tl = JSON.parse(readFileSync(path.join(STATIC, "demo-revised.json"), "utf8")).timeline;
  const evs = tl.filter(e => e.type === "fix" && e.detail && Array.isArray(e.detail.removed));
  if (!evs.length) throw new Error("demo-revised 无带 removed 的 fix 事件（断言无效）");
  const view = freshView();
  for (const ev of evs) applyEvent(view, ev);
  for (const ev of evs) {
    const m = ev.title.match(/第(\d+)天/);
    if (!m) throw new Error("fix title 缺天序：" + ev.title);
    const set = view.removed.get(+m[1]);
    if (!set) throw new Error(`第${m[1]}天 view.removed 缺失`);
    for (const id of ev.detail.removed) if (!set.has(id)) throw new Error(`removed 缺 poi ${id}`);
  }
});
step("CityMaps.render（真实 view 状态驱动：revealed 非空 + removed 灰叉分支）", async () => {
  const { viewAt } = await import(pathToFileURL(path.join(STATIC, "js", "view.js")));
  const view = viewAt(globalThis.__events.length, globalThis.__events);
  const revealedTotal = [...view.revealed.values()].reduce((n, s) => n + s.size, 0);
  if (!revealedTotal) throw new Error("viewAt 全量事件后 revealed 为空集——P0 回归（路线将不渲染）");
  globalThis.__maps.render({
    itinerary: globalThis.__itinerary,
    revealed: view.revealed, activeDay: 1, removed: view.removed,
  });
});
step("import timeline.js + DayPanel.render（removedNames 分支）", async () => {
  const { DayPanel } = await import(pathToFileURL(path.join(STATIC, "js", "timeline.js")));
  const dp = new DayPanel(() => {});
  const itin = { days: [{ day: 1, city: "成都", weather: {}, items: [{ type: "poi", poi_id: "CD-01", name: "宽窄巷子", arrival: "09:00", departure: "11:30", visit_hours: 2.5, ticket: 0, leg_hours: 0.2, tags: [], reasons: [], summary: "" }], load: { hours: 5, intensity: 2, tickets: 0 }, narrative: "" }], budget: { tickets: 0, meals: 120, transit: 35, total: 155, per_day: 51.7 } };
  dp.render(itin, { removedNames: new Map([[1, ["测试点"]]]), advisories: new Map([[1, { reason: "软提醒" }]]) });
});
step("DayPanel 空态占位（首开不空白）", async () => {
  const { DayPanel } = await import(pathToFileURL(path.join(STATIC, "js", "timeline.js")));
  const dp = new DayPanel(() => {});
  dp.render(null, {});
  const html = document.getElementById("day-panel").innerHTML;
  if (!html.includes("还没有行程")) throw new Error("空态占位缺失");
});
step("plan.html 工作台静态容器完整（图例/横滚提示/城市多选/参数提示）", () => {
  const html = readFileSync(path.join(STATIC, "plan.html"), "utf8");
  for (const id of ["map-legend", "map-scroll-hint", "p-cities", "params-hint", "city-pick-hint"]) {
    if (!html.includes(id)) throw new Error("静态容器缺失: " + id);
  }
  // 03G：天数上限 30 + origin 只读提示行 + 对话栏 note 容器 + 双模式 placeholder
  if (!html.includes('max="30"')) throw new Error("p-days 上限应放开到 30");
  for (const id of ["parse-origin", "chat-note", "days-hint"]) {
    if (!html.includes(`id="${id}"`)) throw new Error("03G 静态容器缺失: " + id);
  }
  if (!html.includes("我在北京，想去成都和重庆玩3天")) throw new Error("规划模式 placeholder 缺失");
});
step("parsefill.js：抽取结果回填参数条（回填不替换，未识别保留原值）", async () => {
  const { applyParseResult, describeParse } = await import(pathToFileURL(path.join(STATIC, "js", "parsefill.js")));
  // DOM stub 环境：document.getElementById 返回通用 makeEl（value 可断言）
  const days = document.getElementById("p-days");
  const budget = document.getElementById("p-budget");
  const tags = document.getElementById("p-tags");
  const family = document.getElementById("p-family");
  days.value = "3"; budget.value = "3000"; tags.value = "美食,文化"; family.checked = false;
  const boxes = [
    { value: "成都", checked: true },
    { value: "重庆", checked: false },
    { value: "昆明", checked: false },
  ];
  const r = { origin: "北京", cities: ["重庆"], days: 12, budget: 1500,
              tags: ["夜景"], family: true, source: "rules", note: "" };
  const { applied, kept } = applyParseResult(r, { cityBoxes: () => boxes });
  if (days.value !== "12") throw new Error("p-days 未回填: " + days.value);
  if (budget.value !== "1500") throw new Error("p-budget 未回填: " + budget.value);
  if (tags.value !== "夜景") throw new Error("p-tags 未回填: " + tags.value);
  if (family.checked !== true) throw new Error("p-family 未回填");
  if (!boxes.find(b => b.value === "重庆").checked) throw new Error("城市勾选未回填");
  if (boxes.find(b => b.value === "成都").checked) throw new Error("未提及的城市勾选应取消");
  const oEl = document.getElementById("parse-origin");
  if (!oEl.textContent.includes("北京") || !oEl.textContent.includes("暂未计入行程时间与交通费")) {
    throw new Error("origin 提示缺如实标注: " + oEl.textContent);
  }
  if (!applied.includes("days") || !applied.includes("cities")) throw new Error("applied 字段缺失: " + applied);
  // 回填不替换：只给 tags 时其余字段保留原值
  const before = { d: days.value, b: budget.value, f: family.checked };
  applyParseResult({ tags: ["美食"], cities: [], days: null, budget: null, family: false, origin: null }, { cityBoxes: () => [] });
  if (days.value !== before.d || budget.value !== before.b) throw new Error("未识别字段被清空（回填≠替换）");
  if (family.checked !== before.f) throw new Error("family=false 不应清除原勾选");
  if (!document.getElementById("parse-origin").hidden) throw new Error("origin 应随空值收起");
  // 提示语拼接
  const s = describeParse(r);
  if (!s.includes("我理解为") || !s.includes("12 天") || !s.includes("重庆") || !s.includes("暂未计入")) {
    throw new Error("describeParse 提示语不完整: " + s);
  }
});
step("main.js：对话栏双模式分发存在（无计划=抽取规划，有计划=revise）", () => {
  const src = readFileSync(path.join(STATIC, "js", "main.js"), "utf8");
  if (!src.includes("planByChat") || !src.includes("api.parse")) throw new Error("缺 planByChat/api.parse 分发");
  if (!src.includes("planByChat(v)")) throw new Error("双模式分发逻辑缺失");
  if (!src.includes("applyParseResult")) throw new Error("缺回填调用");
});
step("双页面拆分：index=品牌首页 / plan=工作台（互链与职责断言）", () => {
  const home = readFileSync(path.join(STATIC, "index.html"), "utf8");
  const plan = readFileSync(path.join(STATIC, "plan.html"), "utf8");
  if (!home.includes('href="plan.html"') || !home.includes("js/home.js")) throw new Error("首页缺少工作台入口或 home.js");
  if (home.includes('id="params-form"') || home.includes('id="chat-input"')) throw new Error("首页不应含工作台表单/对话栏");
  if (!plan.includes('id="params-form"') || !plan.includes('id="map-row"') || !plan.includes('id="chat-input"')) throw new Error("工作台缺关键容器");
  if (!plan.includes("js/main.js") || plan.includes('class="hero"')) throw new Error("工作台应引 main.js 且不含 hero");
  if (!plan.includes('href="index.html"')) throw new Error("工作台缺返回首页链接");
});
step("home.js 语法与透传逻辑存在", async () => {
  const src = readFileSync(path.join(STATIC, "js", "home.js"), "utf8");
  if (!src.includes("passThrough") || !src.includes("plan.html?")) throw new Error("home.js 缺参数透传");
  await import(pathToFileURL(path.join(STATIC, "js", "home.js")));
});
step("03I：对话栏归位参数条下方（form 外、map 前）+ Day 标签横向滚动容器", () => {
  const plan = readFileSync(path.join(STATIC, "plan.html"), "utf8");
  const formEnd = plan.indexOf("</form>");
  const chatAt = plan.indexOf('class="chat-bar"');
  const mapAt = plan.indexOf('id="map-row"');
  if (!(formEnd >= 0 && chatAt > formEnd && mapAt > chatAt)) {
    throw new Error(`chat-bar 应在 </form> 之后、map-row 之前（formEnd=${formEnd}, chat=${chatAt}, map=${mapAt}）`);
  }
  if (plan.lastIndexOf('class="chat-bar"') !== chatAt) throw new Error("chat-bar 应只出现一次（旧 fixed 底部条应已删除）");
  const css = readFileSync(path.join(STATIC, "style.css"), "utf8");
  if (!/\.day-tabs\s*\{[^}]*overflow-x:\s*auto/.test(css)) throw new Error(".day-tabs 缺 overflow-x: auto");
  if (!/\.day-tab\s*\{[^}]*flex:\s*0 0 auto/.test(css)) throw new Error(".day-tab 缺 flex: 0 0 auto（防压缩挤断）");
  if (!css.includes(".day-tabs.dragging") || !css.includes("cursor: grabbing")) throw new Error("拖拽光标样式缺失");
  if (!plan.includes('id="day-scroll-hint"')) throw new Error("Day 溢出提示容器缺失");
});
step("03I：dragscroll.js 导入可用（拖拽滚动 + 溢出提示纯函数）", async () => {
  const { enableDragScroll, updateOverflowHint } = await import(pathToFileURL(path.join(STATIC, "js", "dragscroll.js")));
  const el = { addEventListener() {}, classList: { add() {}, remove() {} }, scrollLeft: 0, scrollWidth: 0, clientWidth: 0 };
  if (enableDragScroll(el) !== el) throw new Error("enableDragScroll 应返回元素本身");
  if (enableDragScroll(null) !== null) throw new Error("空元素应安全返回");
  const hint = { hidden: false };

  updateOverflowHint({ scrollWidth: 500, clientWidth: 200 }, hint);
  if (hint.hidden !== false) throw new Error("溢出时应显示提示");
  updateOverflowHint({ scrollWidth: 200, clientWidth: 500 }, hint);
  if (hint.hidden !== true) throw new Error("未溢出时应隐藏提示");
  // timeline.js 引 dragscroll 后模块加载不炸（DOM stub 环境）
  await import(pathToFileURL(path.join(STATIC, "js", "timeline.js")));
});
step("03J：偏好记忆分支存在（对话栏入口，零 UI 改动）", () => {
  const main = readFileSync(path.join(STATIC, "js", "main.js"), "utf8");
  if (!main.includes("r.remember || r.forget || r.view")) throw new Error("planByChat 缺记忆意图分支");
  if (!main.includes("setChatNote(r.note)")) throw new Error("记忆操作未回对话栏提示");
  const apiSrc = readFileSync(path.join(STATIC, "js", "api.js"), "utf8");
  if (!apiSrc.includes("remember: false")) throw new Error("Mock.parse 缺记忆字段（结构不同构）");
});
step("03L：决策报告 renderReport（Mock 导出同构，六节 + reason 原文 + 预算）", async () => {
  const { renderReport, SECTION_TITLES } = await import(pathToFileURL(path.join(STATIC, "js", "report.js")));
  const demo = JSON.parse(readFileSync(path.join(STATIC, "demo.json"), "utf8"));
  // 喂真实 demo 产物（不手工构造事件——冒烟只消费真实产物，第 15 轮的纪律）
  const md = renderReport({ itinerary: demo.itinerary, timeline: demo.timeline,
                            meta: { poi_count: 237, data_version: null, contract_version: null } });
  const secs = [...md.matchAll(/^## (.+)$/gm)].map(m => m[1]);
  if (JSON.stringify(secs) !== JSON.stringify(SECTION_TITLES)) {
    throw new Error("六节缺失或乱序：" + JSON.stringify(secs));
  }
  // 已知事件 reason 原文（demo.json 的 start 事件）
  const startEv = demo.timeline[0];
  if (!md.includes(startEv.reason)) throw new Error("已知事件 reason 原文未出现在报告：" + startEv.reason);
  // 预算明细（demo 的真实 budget）
  const b = demo.itinerary.budget;
  if (!md.includes(`¥${b.tickets}`) || !md.includes(`¥${b.total}`)) {
    throw new Error("预算明细缺真实数字：" + JSON.stringify(b));
  }
  // 断网如实标注（后端未启动时版本信息不可读——不许假装）
  if (!md.includes("后端未启动，运行时版本不可读")) throw new Error("Mock 版第 6 节缺如实标注");
  // api.js 第 8 方法存在且 UI 不直接 fetch 报告端点
  const apiSrc = readFileSync(path.join(STATIC, "js", "api.js"), "utf8");
  if (!apiSrc.includes("report: (planId)") || !apiSrc.includes("/api/plan/report")) {
    throw new Error("api.js 缺第 8 方法 report");
  }
  const mainSrc = readFileSync(path.join(STATIC, "js", "main.js"), "utf8");
  if (!mainSrc.includes("api.report(state.planId)")) throw new Error("按钮未走 api.report（唯一数据入口）");
  if (/fetch\([^)]*report/.test(mainSrc)) throw new Error("UI 层不许直接 fetch 报告端点");
  const planHtml = readFileSync(path.join(STATIC, "plan.html"), "utf8");
  if (!planHtml.includes('id="btn-report"')) throw new Error("plan.html 缺导出按钮容器");
});

let failed = 0;
for (const [name, fn] of steps) {
  try {
    await fn();
    console.log("  ✓ " + name);
  } catch (err) {
    failed++;
    console.error(`  ✗ ${name} → ${err.constructor.name}: ${err.message}`);
  }
}
console.log(failed
  ? `\n冒烟失败：${failed}/${steps.length} 步异常`
  : `\n冒烟通过（${steps.length} 步）：前端关键路径全部正常`);
process.exit(failed ? 1 : 0);