// parsefill.js — 抽取结果 → 参数条回填（03G：纯函数，不依赖 main.js 状态）
// 设计原则（与后端 parse_request 的「抽取与规划分离」同源）：
//   回填不是替换——抽取没识别的字段保留参数条原值，用户改过的参数不被一句话抹掉；
//   回填即白盒——AI 把话理解成什么样，用户看得见、可改，然后才触发规划。
// DOM 访问仅经 document.getElementById 与注入的 cityBoxes()（冒烟可测）。

const $ = id => document.getElementById(id);

/** 把 /api/parse 的返回回填到参数条。
 *  r: {origin, cities, days, budget, tags, family, source, note}
 *  opts.cityBoxes: () => [{value, checked}] 城市勾选框的注入式访问
 *  opts.onHint: 回填后回调（main.js 传 updateCityDayHint，让「已选 N 城」提示跟上）
 *  返回 {applied: [...字段名], kept: [...字段名]}——回填了什么、保留了什么，供测试断言 */
export function applyParseResult(r, opts = {}) {
  const applied = [], kept = [];
  const setVal = (id, v, name) => {
    if (v == null) { kept.push(name); return; }
    const el = $(id);
    if (el) el.value = String(v);
    applied.push(name);
  };

  setVal("p-days", r.days, "days");
  setVal("p-budget", r.budget, "budget");
  setVal("p-tags", Array.isArray(r.tags) && r.tags.length ? r.tags.join(",") : null, "tags");
  if (r.family === true) {
    const el = $("p-family");
    if (el) el.checked = true;
    applied.push("family");
  } else {
    kept.push("family");   // 抽取没提到亲子就不动原勾选
  }

  if (Array.isArray(r.cities) && r.cities.length) {
    const boxes = opts.cityBoxes ? opts.cityBoxes() : [];
    for (const b of boxes) b.checked = r.cities.includes(b.value);
    applied.push("cities");
  } else {
    kept.push("cities");
  }

  const oEl = $("parse-origin");
  if (oEl) {
    if (r.origin) {
      oEl.textContent = `出发地：${r.origin}（暂未计入行程时间与交通费）`;
      oEl.hidden = false;
      applied.push("origin");
    } else {
      oEl.hidden = true;   // 本次没有出发地 → 收起旧提示（它只描述当次抽取）
    }
  }

  if (typeof opts.onHint === "function") opts.onHint();
  return { applied, kept };
}

/** 拼对话栏的「我理解为…」提示语（含 note 的如实提示） */
export function describeParse(r) {
  const parts = [];
  if (r.days) parts.push(`${r.days} 天`);
  if (r.budget) parts.push(`预算 ${r.budget}`);
  if (r.cities?.length) parts.push(r.cities.join("、"));
  if (r.tags?.length) parts.push(r.tags.join("、"));
  if (r.family) parts.push("亲子模式");
  let s = parts.length
    ? `我理解为：${parts.join(" / ")}，已按这个开始规划（可在上方参数条修改后重新规划）`
    : "没太看懂，你也可以直接用上方参数条填写";
  if (r.origin) s += `；出发地 ${r.origin}（暂未计入行程时间与交通费）`;
  if (r.note) s += `；${r.note}`;
  return s;
}