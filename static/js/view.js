// view.js — 事件流 → 视图状态机（纯函数，不碰 DOM）
// 回放第 k 条事件时的界面 = 依序 apply 前 k 条事件（applyEvent 映射表）。
// 从 main.js 抽出（第十四轮后 P0 复核）：这条链路此前零冒烟覆盖——
// 「第N天选点」detail 嵌套结构被读错层级，revealed 恒空集、地图路线从未渲染过。

export function freshView() {
  return {
    revealed: new Map(),     // day → Set(poi_id)  已揭示点位
    activeDay: 1,
    advisories: new Map(),   // day → 软提醒事件
    violations: new Map(),   // day → 硬违规事件
    removed: new Map(),      // day → Set(poi_id)  被规则移除的点位（F2：地图灰叉/行程卡删除线联动）
    narrated: new Set(),     // day  叙事已生成的天
    finished: false,         // 管线完成
    fixes: [],               // 修复动作记录
  };
}

/** 解包事件 detail：violation/advisory 等事件的 detail 为 {"detail": 载荷} 嵌套结构
 *  （EventBus.emit 的 kwargs 收集所致）；decision 的 detail 为扁平 poi_id 数组。
 *  本函数是「嵌套结构」的唯一解包点——此前 main.js/map.js 各读各的层级，就是 P0 的根源。 */
export function payload(ev) {
  const d = ev.detail;
  return d && typeof d === "object" && !Array.isArray(d) && "detail" in d ? d.detail : d;
}

export function applyEvent(view, ev) {
  const vd = payload(ev);
  if (ev.type === "decision") {
    let m = ev.title.match(/第(\d+)天选点/);
    if (m) {
      const day = +m[1];
      // P0 修复（第十四轮后复核）：读解包后的 vd（载荷）而非 ev.detail——
      // 嵌套结构 {"detail":["CD-09",...]} 下 Array.isArray(ev.detail) 恒 false，
      // revealed 永远空集 → 地图路线/标签/点亮态/描线动效从未渲染。
      view.revealed.set(day, new Set(Array.isArray(vd) ? vd : []));
      view.activeDay = day;
    }
  } else if (ev.type === "violation") {
    if (vd && vd.day) view.violations.set(vd.day, ev);
  } else if (ev.type === "advisory") {
    if (vd && vd.day) view.advisories.set(vd.day, ev);
  } else if (ev.type === "fix") {
    view.fixes.push(ev);
    // F2：fix 事件 detail.removed 携带被移除 poi_id → 写入 view.removed
    const m = ev.title.match(/第(\d+)天/);
    const fd = payload(ev);
    if (m && fd && Array.isArray(fd.removed)) {
      const day = +m[1];
      if (!view.removed.has(day)) view.removed.set(day, new Set());
      fd.removed.forEach(id => view.removed.get(day).add(id));
    }
  } else if (ev.type === "done" && ev.stage === "narrate") {
    const m = ev.title.match(/第(\d+)天文案/);
    if (m) view.narrated.add(+m[1]);
  } else if (ev.type === "done" && ev.stage === "system") {
    view.finished = true;
  }
  return view;
}

export function viewAt(cursor, events) {
  let view = freshView();
  for (let i = 0; i < cursor && i < events.length; i++) applyEvent(view, events[i]);
  return view;
}