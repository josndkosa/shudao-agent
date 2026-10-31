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
step("CityMaps.render（含 removed 灰叉分支）", () => {
  const evs = globalThis.__events.filter(e => e.type === "fix");
  const removed = new Map();
  for (const e of evs) if (e.detail?.removed) removed.set(e.detail.day ?? 1, new Set(e.detail.removed));
  const revealed = new Map([[1, new Set(globalThis.__events.filter(e => e.type === "decision").flatMap(e => Array.isArray(e.detail) ? e.detail : []))]]);
  globalThis.__maps.render({
    itinerary: { days: [{ day: 1, city: "成都", items: [{ type: "poi", poi_id: "CD-01" }] }] },
    revealed, activeDay: 1, removed,
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
console.log(failed ? `\n冒烟失败：${failed} 步异常` : "\n冒烟通过：前端关键路径全部正常");
process.exit(failed ? 1 : 0);