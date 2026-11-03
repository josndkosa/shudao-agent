// api.js — 数据源适配层（本作品唯一的数据入口，上层不出现任何 mock 分支）
// 契约（后端 Prompt 02 严格照此实现）：
//   health()                                   → {status, mode, llm}
//   parse(text)                                → {origin, cities, days, budget, tags, family, source, note}
//   plan({days, budget, tags, family})         → {plan_id, itinerary, timeline, mode, budget}
//   stream(req, onEvent)                       → 逐条回调事件；倒数第二次回调
//                                                 {type:"plan_result", plan_id, itinerary, budget, mode}
//                                                 （行程随流返回，一次规划只跑一次管线）；
//                                                 最后回调 {type:"done"}；返回 {unsubscribe()}
//   revise(plan_id, message)                   → {itinerary, timeline, revised_day, message}
//   geo(plan_id, city)                         → {points:[...], cities:[...]}
//   meta()                                     → {cities:[...], tags:[...], meta:{...}}
//   report(plan_id)                            → string（六节 Markdown 决策报告，03L 任务L6）
//                                                 Live=服务端渲染；Mock=本地 renderReport 同构生成

const HEALTH_URL = "/api/health";
const HEALTH_TIMEOUT = 2000;      // 2 秒内不响应即视为后端未启动
const MOCK_INTERVAL = 350;        // Mock 流式基础间隔（ms），流式手感的来源
const MOCK_INTERVAL_FAST = 120;   // 加速档

// ───────────────────── 真实后端实现（LiveApi）─────────────────────
class LiveApi {
  constructor() { this.kind = "live"; }

  async health() {
    const r = await fetch(HEALTH_URL);
    if (!r.ok) throw new Error(`health ${r.status}`);
    return r.json();
  }

  async parse(text) {
    const r = await fetch("/api/parse", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error(`parse ${r.status}`);
    return r.json();
  }

  async plan(req) {
    const r = await fetch("/api/plan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!r.ok) throw new Error(`plan ${r.status}`);
    return r.json();
  }

  async stream(req, onEvent) {
    // SSE 是 POST 流：EventSource 不支持 POST，用 fetch + ReadableStream 手工解析 data: 帧
    const ctrl = new AbortController();
    const r = await fetch("/api/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req), signal: ctrl.signal,
    });
    if (!r.ok || !r.body) throw new Error(`stream ${r.status}`);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    const pump = async () => {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop();
        for (const f of frames) {
          const line = f.split("\n").find(l => l.startsWith("data:"));
          if (line) {
            try { onEvent(JSON.parse(line.slice(5))); } catch { /* 忽略坏帧 */ }
          }
        }
      }
    };
    pump().catch(() => onEvent({ type: "error" }));
    return { unsubscribe: () => ctrl.abort() };
  }

  async revise(planId, message) {
    const r = await fetch("/api/revise", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: planId, message }),
    });
    if (!r.ok) throw new Error(`revise ${r.status}`);
    return r.json();
  }

  async geo(planId, city) {
    const r = await fetch(`/api/geo?plan_id=${encodeURIComponent(planId)}&city=${encodeURIComponent(city)}`);
    if (!r.ok) throw new Error(`geo ${r.status}`);
    return r.json();
  }

  async meta() {
    const r = await fetch("/api/meta");
    if (!r.ok) throw new Error(`meta ${r.status}`);
    return r.json();
  }

  async report(planId) {
    const r = await fetch(`/api/plan/report?plan_id=${encodeURIComponent(planId)}`);
    if (!r.ok) throw new Error(`report ${r.status}`);
    return r.text();
  }
}

// ───────────────────── 本地演示实现（MockApi，答辩保命）─────────────────────
class MockApi {
  constructor() {
    this.kind = "mock";
    this._cache = {};
    this._baseInterval = MOCK_INTERVAL;
  }

  async _load(name) {
    if (!this._cache[name]) {
      const r = await fetch(`./${name}`);
      if (!r.ok) throw new Error(`加载 ${name} 失败：${r.status}`);
      this._cache[name] = await r.json();
    }
    return this._cache[name];
  }

  async health() { return { status: "ok", mode: "mock", llm: "offline" }; }

  async parse() {
    // 如实标注：抽取器与偏好记忆（两种实现都在服务端）后端未启动时均不可用，
    // 返回 fallback + 记忆字段缺省（remember/forget/view 恒 false）走与「抽取失败」
    // 同一条前端路径（零分叉）——不假装能理解、不假装记住了
    return { origin: null, cities: [], days: null, budget: null, tags: [],
             family: false, source: "fallback", note: "后端未启动，自然语言抽取与偏好记忆暂不可用；请直接用上方参数条填写",
             remember: false, forget: false, view: false, prefs: {}, timeline: [] };
  }

  async plan(req) {
    const data = await this._load("demo.json");
    this._planId = "mock-1";
    this._history = [...data.timeline];     // 累计事件流（revise 时续接）
    this._lastItinerary = data.itinerary;   // F3：revise 时对比找实际变化的天
    return { plan_id: this._planId, ...data };
  }

  async stream(req, onEvent) {
    const data = await this._load("demo.json");
    const events = data.timeline;
    let i = 0, alive = true;
    // 03K：Promise 等流真正推完再 resolve——与 LiveApi「读完 body 才返回」同构。
    // 此前立即 resolve：main.js 的兜底分支（!gotResult && !itinerary）会在流开始前
    // 触发 api.plan() 双跑，事件列表出现两份；done 帧的 seek 也会晚于深链定位执行，
    // 把 ?seq=N 的定位覆盖回末尾（断网演示下深链失效）。同构修复，不改帧格式与顺序。
    await new Promise(resolve => {
      const tick = () => {
        if (!alive) { resolve(); return; }
        if (i < events.length) {
          onEvent(events[i++]);
          setTimeout(tick, this._baseInterval);
        } else {
          // 与 LiveApi 契约对齐：业务事件之后先给 plan_result（行程随流返回），再发 done
          onEvent({ type: "plan_result", plan_id: "mock-1",
                    itinerary: data.itinerary, budget: data.budget, mode: "mock" });
          onEvent({ type: "done" });
          resolve();
        }
      };
      setTimeout(tick, this._baseInterval);
    });
    return { unsubscribe: () => { alive = false; } };
  }

  async revise(planId, message) {
    // 本地演示：切换到另一份真实行程，并把其时间线接在原时间线之后（第二幕）
    const revised = await this._load("demo-revised.json");
    const base = this._history?.length ? this._history : (await this._load("demo.json")).timeline;
    let seq = base.length ? base[base.length - 1].seq : 0;
    const divider = {
      seq: ++seq, stage: "revise", type: "start",
      title: `用户介入：${message}`,
      reason: "本地演示：切换到另一份真实行程（预算更紧），时间线续接展示修订过程",
      detail: {},
    };
    const tail = revised.timeline.map(e => ({ ...e, seq: ++seq }));
    const timeline = [...base, divider, ...tail];
    this._history = timeline;
    // F3：revised_day 不硬编码——对比两份行程每天 poi 集合，找差异最大的一天
    const revisedDay = this._diffDay(this._lastItinerary, revised.itinerary);
    this._lastItinerary = revised.itinerary;
    return {
      itinerary: revised.itinerary,
      timeline,
      revised_day: revisedDay,
      message: "本地演示：已切换到预算更紧的真实行程",
      budget: revised.budget,
    };
  }

  /** 对比两份行程，返回 poi 集合差异最大的天数；完全相同返回 null */
  _diffDay(a, b) {
    if (!a || !b) return null;
    const daySet = d => new Set(d.items.filter(i => i.type === "poi").map(i => i.poi_id));
    let bestDay = null, bestDiff = 0;
    for (const d of b.days) {
      const other = a.days.find(x => x.day === d.day);
      const s = daySet(d);
      const diff = other
        ? [...new Set([...s, ...daySet(other)])].filter(x => !s.has(x) || !daySet(other).has(x)).length
        : s.size;
      if (diff > bestDiff) { bestDiff = diff; bestDay = d.day; }
    }
    return bestDiff > 0 ? bestDay : null;
  }

  async geo() {
    const data = await this._load("demo-geo.json");
    const { _city_meta, ...pts } = data;
    return { points: pts, cities: Object.keys(pts), city_meta: _city_meta || {} };
  }

  async meta() {
    const data = await this._load("demo-geo.json");
    const { _city_meta, ...pts } = data;
    const tags = new Set();
    let count = 0;
    for (const city of Object.values(pts)) {
      count += city.length;
      for (const p of city) (p.tags || []).forEach(t => tags.add(t));
    }
    // count 与 LiveApi 的 meta.count 同义（断网时数字来自本地演示快照，徽标如实标注）
    return { cities: Object.keys(pts), tags: [...tags],
             meta: { source: "local-snapshot", count } };
  }

  async report(planId) {
    // 与 LiveApi.report 同构：本地用 renderReport 生成六节 Markdown（断网也能导出，
    // 「断网保命」的一环）；数据版本/契约版本后端未启动不可读——第 6 节如实标注。
    const { renderReport } = await import("./report.js");
    const data = await this._load("demo.json");
    const timeline = this._history?.length ? this._history : data.timeline;
    const itinerary = this._lastItinerary || data.itinerary;
    const m = await this.meta();
    return renderReport({
      itinerary, timeline,
      meta: { source: "local-snapshot", poi_count: m.meta.count,
              data_version: null, contract_version: null },
    });
  }
}

// ───────────────────── 懒选择：后端 2 秒内应答走真实，否则 Mock ─────────────────────
let _impl = null;

async function pick() {
  if (_impl) return _impl;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT);
    const r = await fetch(HEALTH_URL, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) throw new Error(String(r.status));
    _impl = new LiveApi();
  } catch {
    _impl = new MockApi();
  }
  return _impl;
}

export const api = {
  kind: () => (_impl ? _impl.kind : "detecting"),
  health: () => pick().then(i => i.health()),
  parse: (text) => pick().then(i => i.parse(text)),
  plan: (req) => pick().then(i => i.plan(req)),
  stream: (req, onEvent) => pick().then(i => i.stream(req, onEvent)),
  revise: (planId, message) => pick().then(i => i.revise(planId, message)),
  geo: (planId, city) => pick().then(i => i.geo(planId, city)),
  meta: () => pick().then(i => i.meta()),
  report: (planId) => pick().then(i => i.report(planId)),
};