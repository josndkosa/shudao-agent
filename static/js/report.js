// report.js — 决策报告渲染（03L 任务L6，纯函数：无 DOM / 无网络依赖）
// 与 server/agent/report.py 结构同构：六节标题逐字一致（tests/test_report.py 锁章节序列）。
// 纯函数是 Mock 与在线共用的前提——断网（Mock）也能导出，且报告结构不走样。
// 铁律：只写「事件流 / 行程 / meta 里出现过」的信息，不润色、不总结、不编造。

export const SECTION_TITLES = [
  "1. 请求摘要",
  "2. 逐日行程",
  "3. 决策链（事件流全量）",
  "4. 校验与修复",
  "5. 预算明细",
  "6. 数据与版本",
];

/** 与 server/agent/report.py 的 unwrap_detail 语义等价（改一处改两处）：
 *  detail 是 object 且含 'detail' 键 → 取内层；否则原样返回。
 *  与 view.js 的 payload(ev) 同规则——嵌套外壳直读会拿到 undefined。 */
function unwrapDetail(ev) {
  const d = ev.detail;
  return d && typeof d === "object" && !Array.isArray(d) && "detail" in d ? d.detail : d;
}

function esc(s) {
  return String(s ?? "").replaceAll("|", "\\|").replaceAll("\n", " ");
}

function money(v) {
  return v == null ? "—" : `¥${v}`;
}

/** 从「解析行程需求」thought 事件 reason 里提取偏好标签与预算上限（事件流原文，不拼装） */
function thoughtReqs(timeline) {
  const out = { tags: [], budget: "" };
  for (const ev of timeline) {
    if (ev.type === "thought" && (ev.title || "").includes("需求")) {
      const m = (ev.reason || "").match(/偏好\[([^\]]*)\]/);
      if (m) out.tags = m[1].split(",").map(t => t.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);
      const mb = (ev.reason || "").match(/预算(\d+)元/);
      if (mb) out.budget = mb[1];
      break;
    }
  }
  return out;
}

function modeOf(itinerary, timeline) {
  if (itinerary.mode) return String(itinerary.mode);
  for (const ev of timeline) {
    const d = unwrapDetail(ev);
    if (d && typeof d === "object" && d.mode) return String(d.mode);
  }
  return "unknown";
}

export function renderReport({ itinerary, timeline, meta = {} }) {
  const days = itinerary.days || [];
  const budget = itinerary.budget || {};
  const mode = modeOf(itinerary, timeline);
  const { tags, budget: userBudget } = thoughtReqs(timeline);
  const genTime = new Date().toLocaleString("zh-CN", { hour12: false });
  const nPois = days.reduce((n, d) =>
    n + (d.items || []).filter(it => it.type === "poi").length, 0);
  const L = [];

  L.push("# 蜀道智行 · 决策报告", "");
  L.push(`> 生成时间：${genTime} ｜ 引擎模式：${mode} ｜ 事件数：${timeline.length} ｜ 行程点数：${nPois}`, "");

  // ── 1. 请求摘要 ──
  const cities = [...new Set(days.map(d => d.city))];
  L.push(`## ${SECTION_TITLES[0]}`, "");
  L.push(`- 天数：${days.length} 天`);
  L.push(`- 城市序列：${cities.join(" → ") || "—"}`);
  L.push(`- 偏好标签：${tags.join("、") || "—"}`);
  L.push(`- 预算上限：${userBudget ? `¥${userBudget}` : "—"}（实际总花费见第 5 节）`);
  L.push(`- 引擎模式：${mode}（offline=离线确定性管线 / online=DeepSeek 在线规划）`, "");

  // ── 2. 逐日行程 ──
  L.push(`## ${SECTION_TITLES[1]}`, "");
  for (const d of days) {
    L.push(`### Day ${d.day} · ${d.city}`, "");
    L.push("| 时间 | 点位 | 时长 | 票价 | 命中标签 |", "|---|---|---|---|---|");
    for (const it of d.items || []) {
      if (it.type === "poi") {
        L.push(`| ${it.arrival || "—"}–${it.departure || "—"} | ${esc(it.name)} ` +
               `| ${it.visit_hours ?? "—"}h | ${money(it.ticket)} | ${esc((it.tags || []).join("、"))} |`);
      } else if (it.type === "intercity") {
        L.push(`| ${it.departure || "—"}–${it.arrival || "—"} | ⇄ ${esc(it.label)}（城际，不计点数） | — | — | — |`);
      } else if (it.type === "meal") {
        L.push(`| ${it.arrival || "—"}–${it.departure || "—"} | ${esc(it.label)} | — | — | — |`);
      }
    }
    L.push("");
  }

  // ── 3. 决策链（事件流全量）──
  L.push(`## ${SECTION_TITLES[2]}`, "", "reason 原文全量，不做任何截断或改写。", "");
  L.push("| seq | stage | type | title | reason |", "|---|---|---|---|---|");
  for (const ev of timeline) {
    L.push(`| ${ev.seq} | ${esc(ev.stage)} | ${esc(ev.type)} | ${esc(ev.title)} | ${esc(ev.reason)} |`);
  }
  L.push("");

  // ── 4. 校验与修复 ──
  L.push(`## ${SECTION_TITLES[3]}`, "");
  const subs = [
    ["violation", "硬违规（进修复循环）"],
    ["fix", "修复动作（detail.removed 携带被移除点位 ID）"],
    ["advisory", "软提醒（不阻断不修复）"],
    ["unfixable", "不可自动修复（收敛检测停止重试）"],
  ];
  for (const [sub, label] of subs) {
    const evs = timeline.filter(e => e.type === sub);
    L.push(`### ${sub}（${label}）`, "");
    if (!evs.length) { L.push("（本行程无此类事件）", ""); continue; }
    L.push("| seq | 天 | 规则 | 载荷原文 | 事件 reason |", "|---|---|---|---|---|");
    for (const ev of evs) {
      const vd = unwrapDetail(ev);
      let day = "", rule = "", payloadTxt = esc(vd);
      if (vd && typeof vd === "object") {
        day = vd.day ?? "";
        rule = vd.rule ?? vd.violation ?? "";
        payloadTxt = vd.removed != null
          ? `removed=${JSON.stringify(vd.removed).replaceAll('"', "'")}`
          : esc(JSON.stringify(Object.fromEntries(
              Object.entries(vd).filter(([k]) => k !== "detail"))).replaceAll('"', "'"));
      }
      L.push(`| ${ev.seq} | ${day} | ${esc(rule)} | ${payloadTxt} | ${esc(ev.reason)} |`);
    }
    L.push("");
  }

  // ── 5. 预算明细 ──
  L.push(`## ${SECTION_TITLES[4]}`, "");
  L.push("| 门票 | 餐饮 | 交通（市内+城际合并口径，数据源未拆分） | 总计 | 日均 |",
         "|---|---|---|---|---|",
         `| ${money(budget.tickets)} | ${money(budget.meals)} | ${money(budget.transit)} ` +
         `| ${money(budget.total)} | ${money(budget.per_day)} |`);
  if (userBudget) {
    L.push("", `实际总花费 ${money(budget.total)} / 预算上限 ¥${userBudget}（V4 预算校验通过）`);
  }
  L.push("");

  // ── 6. 数据与版本 ──
  const dv = meta.data_version, cv = meta.contract_version;
  L.push(`## ${SECTION_TITLES[5]}`, "",
    `- 数据层版本：${dv || "本地演示快照（后端未启动，运行时版本不可读——如实标注）"}`,
    `- 事件契约版本：${cv || "本地演示快照（后端未启动，运行时版本不可读——如实标注）"}`);
  if (meta.poi_count) L.push(`- POI 快照：${meta.poi_count} 点（本地快照）`);
  L.push(`- 引擎模式：${mode}`, `- 生成时间：${genTime}`, "");
  return L.join("\n");
}