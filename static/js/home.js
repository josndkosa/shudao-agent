// home.js — 品牌首页装配：徽标（后端连接 + 引擎模式）与旧链接参数透传。
// 工作台逻辑在 plan.html → js/main.js；本页只做叙事与入口。

import { api } from "./api.js";

const $ = id => document.getElementById(id);

/** 徽标双轨语义（与 plan.html 工作台同源，勿单边修改）：
 *  badge-api   = 后端连接状态（● 已连接后端 / 本地演示数据）
 *  badge-offline = 引擎模式（LLM 在线 / 引擎离线 / 演示数据）——修复旧版恒显「离线」
 *  与「● 已连接后端」并存的语义矛盾 */
function setBadges(h) {
  const b = $("badge-api");
  if (api.kind() === "live") {
    b.textContent = "● 已连接后端";
    b.classList.add("badge-live");
    $("badge-offline").textContent = h.mode === "online" ? "LLM 在线" : "引擎离线";
  } else {
    b.textContent = "本地演示数据（后端未启动）";
    $("badge-offline").textContent = "演示数据";
  }
}

/** 旧链接兼容：README/演示脚本里的 `?days=3&budget=3000&tags=…&auto=1`
 *  打到首页时原样透传给 plan.html（含 cities/family/seq——03K 深链带 seq 进首页也能落到工作台对应位置），不打断既有用法 */
function passThrough() {
  const u = new URLSearchParams(location.search);
  const keys = ["days", "budget", "tags", "family", "cities", "auto", "seq"];
  const hit = keys.filter(k => u.has(k));
  if (!hit.length) return;
  const q = hit.map(k => `${k}=${encodeURIComponent(u.get(k))}`).join("&");
  location.replace("plan.html?" + q);
}

/** 首页统计动态化（任务D）：POI 数/城数来自 api.meta() 的真实数据层——
 *  硬编码必然随数据演进过期（「101 POI / 6 城」在 15 城 237 点后早就不实）。
 *  后端未启动时走 MockApi 的 demo-geo 快照统计（徽标已如实标注「本地演示数据」）；
 *  连快照都拿不到才保持占位「—」——不显示 undefined/NaN，也不显示过时的具体数字。 */
async function fillStats() {
  const poiEl = document.querySelector("[data-stat='poi']");
  const cityEl = document.querySelector("[data-stat='city']");
  try {
    const m = await api.meta();
    if (poiEl && m.meta?.count != null) poiEl.textContent = m.meta.count;
    if (cityEl && Array.isArray(m.cities)) cityEl.textContent = m.cities.length;
  } catch (err) {
    console.warn("统计填充失败，保持占位：", err?.message || err);
  }
}

async function boot() {
  passThrough();
  const h = await api.health();
  setBadges(h);
  fillStats();
}

boot().catch(err => {
  console.error(err);
  const b = $("badge-api");
  if (b) b.textContent = "初始化失败";
});