// api.js — 数据源适配层（本作品唯一的数据入口，上层不出现任何 mock 分支）
// 契约（后端 Prompt 02 严格照此实现）：
//   health()                                   → {status, mode, llm}
//   plan({days, budget, tags, family})         → {plan_id, itinerary, timeline, mode, budget}
//   stream(req, onEvent)                       → 逐条回调事件；最后回调 {type:"done"}；返回 {unsubscribe()}
//   revise(plan_id, message)                   → {itinerary, timeline, revised_day, message}
//   geo(plan_id, city)                         → {points:[...], cities:[...]}
//   meta()                                     → {cities:[...], tags:[...], meta:{...}}

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
    const tick = () => {
      if (!alive) return;
      if (i < events.length) {
        onEvent(events[i++]);
        setTimeout(tick, this._baseInterval);
      } else {
        onEvent({ type: "done" });
      }
    };
    setTimeout(tick, this._baseInterval);
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
    for (const city of Object.values(pts)) {
      for (const p of city) (p.tags || []).forEach(t => tags.add(t));
    }
    return { cities: Object.keys(pts), tags: [...tags], meta: { source: "local-snapshot" } };
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
  plan: (req) => pick().then(i => i.plan(req)),
  stream: (req, onEvent) => pick().then(i => i.stream(req, onEvent)),
  revise: (planId, message) => pick().then(i => i.revise(planId, message)),
  geo: (planId, city) => pick().then(i => i.geo(planId, city)),
  meta: () => pick().then(i => i.meta()),
};