// player.js — 可倒带事件回放器
// 职责：播放器 UI（进度条/播放暂停/单步/倍速/搜索）+ 事件列表渲染 + seek 语义。
// 状态机与视图联动在 main.js（onSeek 回调携带 cursor 与事件数组）。

const TYPE_MARK = {
  start: "▶", thought: "◌", tool_call: "⚙", tool_result: "✓",
  decision: "◆", violation: "✗", fix: "↻", pass: "✔",
  done: "■", fallback: "▽", advisory: "⚠", unfixable: "⊘",
};
const BASE_STEP_MS = 350;   // 与 MockApi 的流式间隔同源

export class Player {
  constructor({ onSeek, onEventClick }) {
    this.events = [];
    this.cursor = 0;              // 已播放到第 cursor 条（含）
    this.playing = false;
    this.speed = 2;
    this.onSeek = onSeek;
    this.onEventClick = onEventClick;
    this.listEl = document.getElementById("event-list");
    this.seekEl = document.getElementById("pc-seek");
    this._timer = null;
    this._bind();
  }

  _bind() {
    document.getElementById("pc-play").addEventListener("click", () => this.toggle());
    document.getElementById("pc-prev").addEventListener("click", () => this.step(-1));
    document.getElementById("pc-next").addEventListener("click", () => this.step(1));
    document.getElementById("pc-first").addEventListener("click", () => this.seek(0));
    document.getElementById("pc-last").addEventListener("click", () => this.seek(this.events.length));
    this.seekEl.addEventListener("input", () => this.seek(+this.seekEl.value));
    document.getElementById("pc-speed").addEventListener("change", e => { this.speed = +e.target.value; });
    document.getElementById("evt-search").addEventListener("input", e => this._filter(e.target.value.trim()));
  }

  setEvents(events, cursor = null) {
    this.events = events;
    this.seekEl.max = events.length;
    this._renderList();
    // 传 cursor 则直接定位目标（避免按旧 cursor 先闪一次旧画面）
    this.seek(cursor != null ? cursor : this.cursor);
  }

  appendEvents(events) {           // revise 时续接第二幕
    this.events = this.events.concat(events);
    this.seekEl.max = this.events.length;
    this._renderList();
  }

  _renderList() {
    this.listEl.replaceChildren();
    const rows = [];
    for (let i = 0; i < this.events.length; i++) {
      const ev = this.events[i];
      const row = document.createElement("div");
      row.className = "evt";
      row.dataset.idx = i;
      const icon = TYPE_MARK[ev.type] || "·";
      row.innerHTML =
        `<span class="evt-seq">#${String(ev.seq).padStart(3, "0")}</span>` +
        `<span class="evt-icon ty-${ev.type}">${icon}</span>` +
        `<div class="evt-title"><span class="evt-stage st-${ev.stage}">[${ev.stage}]</span>${this._esc(ev.title)}</div>` +
        (ev.reason ? `<div class="evt-reason">└ 因为 ${this._esc(ev.reason)}</div>` : "");
      row.addEventListener("click", () => {
        this.seek(i + 1);
        this.onEventClick?.(ev);
      });
      this.listEl.appendChild(row);
      rows.push(row);
    }
    this._rows = rows;
  }

  _esc(s) { const d = document.createElement("div"); d.textContent = String(s); return d.innerHTML; }

  _filter(q) {
    for (let i = 0; i < this.events.length; i++) {
      const ev = this.events[i];
      const hit = !q || (ev.title + " " + (ev.reason || "")).includes(q);
      this._rows[i].classList.toggle("hidden", !hit);
    }
  }

  /** 核心：seek 到第 k 条（视图状态由 main.js 依此重建） */
  seek(k) {
    this.cursor = Math.max(0, Math.min(k, this.events.length));
    this.seekEl.value = this.cursor;
    for (let i = 0; i < this._rows.length; i++) {
      this._rows[i].classList.toggle("cur", i === this.cursor - 1);
      this._rows[i].classList.toggle("future", i >= this.cursor);
    }
    const cur = this._rows[this.cursor - 1];
    if (cur) cur.scrollIntoView({ block: "nearest" });
    this.onSeek?.(this.cursor, this.events);
  }

  step(d) { this.pause(); this.seek(this.cursor + d); }

  toggle() { this.playing ? this.pause() : this.play(); }

  play() {
    if (this.cursor >= this.events.length) this.seek(0);
    this.playing = true;
    document.getElementById("pc-play").textContent = "⏸";
    const loop = () => {
      if (!this.playing) return;
      if (this.cursor >= this.events.length) { this.pause(); return; }
      this.seek(this.cursor + 1);
      this._timer = setTimeout(loop, BASE_STEP_MS / this.speed);
    };
    loop();
  }

  pause() {
    this.playing = false;
    clearTimeout(this._timer);
    document.getElementById("pc-play").textContent = "▶";
  }
}