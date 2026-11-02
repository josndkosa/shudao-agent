// timeline.js — 逐日行程区（Tab 切天 + 三类条目 + 负载/叙事/预算条）
// 注意命名：本模块是"行程区"；可倒带事件时间轴在 player.js。

import { updateOverflowHint } from "./dragscroll.js";

export class DayPanel {
  constructor(onSwitchDay) {
    this.tabsEl = document.getElementById("day-tabs");
    this.panelEl = document.getElementById("day-panel");
    this.budgetEl = document.getElementById("budget-bar");
    this.hintEl = document.getElementById("day-scroll-hint");
    this.onSwitchDay = onSwitchDay;
    this.day = 1;
  }

  /** 渲染整个行程单；advisories: Map(day→事件)，narrated: Set(day)，finished: bool，removedNames: Map(day→[名称]) */
  render(itinerary, { activeDay = 1, advisories = new Map(), narrated = new Set(), finished = false, removedNames = new Map() } = {}) {
    if (!itinerary) {
      // 初始空态：引导用户理解「输入→生成→回放」的主路径，而不是面对一片空白
      this.tabsEl.replaceChildren();
      this.panelEl.innerHTML =
        `<div class="empty-state">
           <div class="empty-title">还没有行程</div>
           <div class="empty-line">① 在上方输入天数、预算与偏好（城市默认成渝，可勾选更多西南城市）</div>
           <div class="empty-line">② 点「开始规划」——规划 → 校验 → 叙事三段式管线逐日生成行程</div>
           <div class="empty-line">③ 打开下方「Agent 决策回放」抽屉，<b>可倒带</b>每一次选点、违规与修复的理由</div>
         </div>`;
      this.budgetEl.replaceChildren();
      this.updateScrollHint();
      return;
    }
    this.itinerary = itinerary;
    this.advisories = advisories;
    this.narrated = narrated;
    this.finished = finished;
    this.removedNames = removedNames;

    // Tabs
    this.tabsEl.replaceChildren();
    for (const d of itinerary.days) {
      const t = document.createElement("div");
      t.className = "day-tab" + (d.day === activeDay ? " on" : "");
      t.textContent = `Day ${d.day} · ${d.city}`;
      if (advisories.has(d.day)) t.classList.add("adv");   // 软提醒天：朱红标记（CSS 统一管理，避免内联色值）
      t.addEventListener("click", () => { this.day = d.day; this.onSwitchDay?.(d.day); });
      this.tabsEl.appendChild(t);
    }
    this._renderDay(activeDay);
    this._renderBudget(itinerary.budget, itinerary.days);
    this.updateScrollHint();
  }

  /** 03I：标签总宽超出容器才显示「还有更多」提示（scrollWidth 实测，不写死个数） */
  updateScrollHint() {
    updateOverflowHint(this.tabsEl, this.hintEl);
  }

  _renderDay(dayNo) {
    const d = this.itinerary.days.find(x => x.day === dayNo);
    this.panelEl.replaceChildren();
    if (!d) return;
    const wrap = document.createElement("div");

    for (const it of d.items) {
      const row = document.createElement("div");
      if (it.type === "meal") {
        row.className = "it-item it-meal";
        row.innerHTML = `<div class="it-time">${it.arrival}</div><div class="it-body">${it.label}</div>`;
      } else if (it.type === "intercity") {
        row.className = "it-item";
        row.innerHTML = `<div class="it-time">${it.arrival}</div><div class="it-body"><div class="it-rail">${it.label} → ${it.departure}</div></div>`;
      } else {
        const price = it.ticket ? `<span class="price">¥${it.ticket}</span>` : "";
        const reasons = (it.reasons || []).map(r => `<span class="it-tag">${r}</span>`).join("");
        row.className = "it-item";
        row.dataset.poi = it.poi_id;
        row.innerHTML =
          `<div class="it-time">${it.arrival}–${it.departure}</div>` +
          `<div class="it-body"><div class="it-name">${it.name}${price}</div>` +
          (reasons ? `<div class="it-tags">${reasons}</div>` : "") +
          `<div class="it-sum">${it.summary || ""}</div>` +
          `<div class="it-reasons">游玩 ${it.visit_hours}h · 交通 ${it.leg_hours}h</div></div>`;
      }
      wrap.appendChild(row);
    }

    // 软提醒（V3 强度等）：琥珀提示条，不渲染成错误
    if (this.advisories.has(dayNo)) {
      const a = this.advisories.get(dayNo);
      const note = document.createElement("div");
      note.className = "it-item advisory";
      note.innerHTML = `<div class="it-time">⚠ 提醒</div><div class="it-body it-sum">${a.reason || a.detail || ""}</div>`;
      wrap.appendChild(note);
    }
    // F2：被规则移除的点位：删除线灰字标记（不消失——消失会让人以为数据丢了）
    if (this.removedNames?.has(dayNo)) {
      for (const name of this.removedNames.get(dayNo)) {
        const row = document.createElement("div");
        row.className = "it-item it-removed";
        row.innerHTML = `<div class="it-time">✕ 移除</div><div class="it-body it-sum"><s>${name}</s> <span class="rm-tag">被规则移除</span></div>`;
        wrap.appendChild(row);
      }
    }
    this.panelEl.appendChild(wrap);

    // 负载条
    const load = document.createElement("div");
    load.className = "day-load";
    // 「偏高」与后端 V3 同口径：校验段报出 advisory 才标注（地形分档 cap 各城不同，
    // 前端不再硬编码 8.5；回放推进到校验段前不预告，与决策叙事一致）
    const over = this.advisories.has(dayNo);
    load.innerHTML =
      `<span>负载 ${d.load.hours}h</span>` +
      `<span class="${over ? "over" : ""}">强度 ${d.load.intensity}${over ? "（偏高）" : ""}</span>` +
      `<span>门票 ¥${d.load.tickets}</span>`;
    this.panelEl.appendChild(load);

    // 叙事段文案（导览词排版，未生成则显示占位）
    const nar = document.createElement("div");
    nar.className = "day-narrative";
    nar.textContent = (this.finished || this.narrated.has(dayNo))
      ? (d.narrative || "")
      : "（回放推进到叙事段后显示当日导览词）";
    this.panelEl.appendChild(nar);
  }

  _renderBudget(budget, days) {
    if (!budget) { this.budgetEl.replaceChildren(); return; }
    this.budgetEl.innerHTML =
      `预算核算：门票 <b>¥${budget.tickets}</b> + 餐饮 <b>¥${budget.meals}</b> + 交通 <b>¥${budget.transit}</b>` +
      ` = <span class="total">¥${budget.total}</span><span>（日均 ¥${budget.per_day}）</span>`;
  }

  highlightPoi(poiId) {
    const row = this.panelEl.querySelector(`[data-poi="${poiId}"]`);
    if (row) {
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
      row.animate([{ background: "rgba(232,163,61,.18)" }, { background: "transparent" }], { duration: 1200 });
    }
  }
}