// map.js — 双城 SVG 自绘路线图（成都 #E8A33D / 重庆 #4EA8DE）
// 坐标全部来自 demo-geo.json（后端 Projector 投影，前端不重算）。
// 渲染受 main.js 的视图状态驱动：revealed（已揭示点位）/ activeDay（当前天）/ advisories（软提醒天）

const CITY_COLOR = { "成都": "#E8A33D", "重庆": "#4EA8DE" };
const SVG_W = 1000, SVG_H = 700;
const NS = "http://www.w3.org/2000/svg";

/** F4：小数小时 → HH:MM（18.5→"18:30"、9→"09:00"、24→"24:00"） */
function fmtHour(h) {
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function el(tag, attrs = {}) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

export class CityMaps {
  constructor(geoData, onPoiClick) {
    this.geo = geoData;                       // {"成都":[...], "重庆":[...]}
    this.onPoiClick = onPoiClick;
    this.index = {};                          // poi_id → {point, city, circle}
    this.lines = {};                          // day → polyline
    this.tip = this._makeTip();
    for (const [city, pts] of Object.entries(geoData)) {
      const domId = city === "成都" ? "map-chengdu" : "map-chongqing";
      const host = document.getElementById(domId);
      const svg = el("svg", { viewBox: `0 0 ${SVG_W} ${SVG_H}` });
      // 底图层：路线线在下，marker 在上
      this._layer = { [city]: { line: el("g"), mark: el("g") } };
      svg.append(this._layer[city].line, this._layer[city].mark);
      host.appendChild(svg);
      this._drawMarkers(city, pts);
    }
  }

  _makeTip() {
    const tip = document.createElement("div");
    tip.className = "poi-tip";
    document.body.appendChild(tip);
    return tip;
  }

  _drawMarkers(city, pts) {
    const g = this._layer[city].mark;
    pts.forEach((p, idx) => {   // idx 仅写入 CSS 变量 --i 供 stagger 动画用，不改任何逻辑
      const c = el("circle", {
        cx: p.x, cy: p.y,
        r: p.must_see ? 8 : 5.5,
        fill: CITY_COLOR[city],
        class: "poi-marker dim",
        "data-poi": p.id,
      });
      c.addEventListener("mouseenter", ev => this._showTip(ev, p));
      c.addEventListener("mouseleave", () => this.tip.classList.remove("on"));
      c.addEventListener("click", () => this.onPoiClick?.(p));
      c.style.setProperty("--i", idx);   // stagger 索引：CSS 动画 delay 消费
      g.appendChild(c);
      this.index[p.id] = { point: p, city, circle: c };
      if (p.must_see) {
        // 必游地标加描边环，识别度更高
        g.appendChild(el("circle", {
          cx: p.x, cy: p.y, r: 12, fill: "none",
          stroke: CITY_COLOR[city], "stroke-width": 1.2, opacity: 0.45,
          class: "poi-marker dim", "data-poi": p.id,
        }));
      }
    });
  }

  _showTip(ev, p) {
    const t = this.tip;
    t.innerHTML = `<div class="t-name">${p.name}</div>` +
      `<div class="t-row">门票 ${p.ticket ? "¥" + p.ticket : "免费"} · ${fmtHour(p.open_hour[0])}-${fmtHour(p.open_hour[1])}</div>` +
      `<div class="t-row">爬坡 ${"▲".repeat(p.slope) || "平"} · 拥挤 ${"●".repeat(p.crowd_level)}${"○".repeat(5 - p.crowd_level)}</div>`;
    t.style.left = Math.min(ev.clientX + 12, innerWidth - 240) + "px";
    t.style.top = ev.clientY - 10 + "px";
    t.classList.add("on");
  }

  /** 依视图状态重绘路线与点位。
   *  view = { itinerary, revealed: Map(day→Set(id)), activeDay, fixed: Set(id), removed: Map(day→Set(id)) }
   */
  render(view) {
    const { itinerary, revealed, activeDay, removed } = view;
    // 清空旧线
    for (const city of Object.keys(this._layer)) this._layer[city].line.replaceChildren();
    if (!itinerary) return;

    for (const d of itinerary.days) {
      const ids = revealed.get(d.day);
      const drop = removed?.get(d.day) || new Set();
      const pts = (ids ? [...ids] : [])
        .filter(id => !drop.has(id) && this.index[id])
        .sort((a, b) => {
          // 按当天 items 顺序排（order by 出现次序）
          const order = d.items.filter(it => it.type === "poi").map(it => it.poi_id);
          return order.indexOf(a) - order.indexOf(b);
        });
      // 连线（同城点才有线；跨城点由高铁线表达）
      const sameCity = pts.filter(id => this.index[id].city === d.city);
      if (sameCity.length >= 2) {
        const hubLine = el("polyline", {
          points: sameCity.map(id => `${this.index[id].point.x},${this.index[id].point.y}`).join(" "),
          class: "route-line" + (d.day === activeDay ? "" : " dim"),
          stroke: CITY_COLOR[d.city],
          "stroke-width": d.day === activeDay ? 3 : 2,
          "stroke-dasharray": d.day === activeDay ? "none" : "6 6",
          opacity: d.day === activeDay ? 0.95 : 0.5,
        });
        this._layer[d.city].line.appendChild(hubLine);
      }
      // 起点/终点天序标记
      if (sameCity.length) {
        const first = this.index[sameCity[0]].point;
        const last = this.index[sameCity[sameCity.length - 1]].point;
        const mk = (pt, txt, y) => {
          const t = el("text", { x: pt.x + 10, y: pt.y + y, class: "daytag" });
          t.textContent = txt;
          this._layer[d.city].line.appendChild(t);
        };
        mk(first, `D${d.day} 起`, -10);
        if (sameCity.length > 1) mk(last, `D${d.day} 止`, 18);
      }
    }
    // marker 状态：removed 命中的点变灰打叉（表达"被规则否决"，不消失）
    const removedAll = new Set();
    for (const set of (removed || new Map()).values()) for (const id of set) removedAll.add(id);
    for (const [id, rec] of Object.entries(this.index)) {
      let revealedSomewhere = false;
      for (const [day, set] of revealed) {
        if (set.has(id) && !removed?.get(day)?.has(id)) { revealedSomewhere = true; break; }
      }
      const isRemoved = removedAll.has(id);
      rec.circle.classList.toggle("dim", !revealedSomewhere || isRemoved);
      rec.circle.classList.toggle("done", revealedSomewhere && !isRemoved);
      rec.circle.setAttribute("fill", isRemoved ? "#6e7681" : CITY_COLOR[rec.city]);
      if (isRemoved) {
        // 打叉（画在线路层，随 render 重建）
        const s = 9;
        const g = this._layer[rec.city].line;
        for (const [dx1, dy1, dx2, dy2] of [[-s, -s, s, s], [-s, s, s, -s]]) {
          g.appendChild(el("line", {
            x1: rec.point.x + dx1, y1: rec.point.y + dy1,
            x2: rec.point.x + dx2, y2: rec.point.y + dy2,
            stroke: "#F85149", "stroke-width": 3, "stroke-linecap": "round",
          }));
        }
      }
    }
  }

  highlight(poiId) {
    const rec = this.index[poiId];
    if (!rec) return;
    rec.circle.classList.remove("dim");
    rec.circle.classList.add("done");
    // 短暂呼吸效果（Web Animations，reduced-motion 下 main.js 已全局降级）
    rec.circle.animate(
      [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(1.9)", opacity: .6 }, { transform: "scale(1)", opacity: 1 }],
      { duration: 700, iterations: 2 },
    );
  }
}