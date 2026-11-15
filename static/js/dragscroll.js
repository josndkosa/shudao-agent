// dragscroll.js — 横向拖动滚动（03I：day-tabs 与 map-row 共用）
// overflow-x: auto 支持触摸板横滑和 Shift+滚轮，但不支持「鼠标按住内容直接拖」——
// 用户说"拖不动"多半就是试了直接拖。触摸设备走原生滚动，不拦截。
// 用原生 Pointer Events，零依赖；别抢按钮/链接/输入件的按下。
//
// 修复（2026-11-15）：旧版在 pointerdown 就 setPointerCapture 到容器，
// click 事件随之被重定向到容器、永远到不了子元素（如 .day-tab）的监听器，
// 表现为「鼠标点第 N 天没反应」（触摸与 JS .click() 不受影响，故自动测试漏检）。
// 改为：移动超过阈值才算拖动并捕获指针；真拖动后的收尾 click 要吞掉，
// 否则松手落在某个 tab 上会误触发切换。

export function enableDragScroll(el) {
  if (!el || !el.addEventListener) return el;
  let dragging = false, moved = false, startX = 0, startLeft = 0;

  el.addEventListener("pointerdown", e => {
    if (e.pointerType === "touch") return;                       // 触摸交给原生
    if (e.target?.closest?.("button, a, input, select")) return;  // 别抢控件的按下
    dragging = true;
    moved = false;
    startX = e.clientX;
    startLeft = el.scrollLeft;
  });
  el.addEventListener("pointermove", e => {
    if (!dragging) return;
    const dx = e.clientX - startX;
    if (!moved) {
      if (Math.abs(dx) <= 4) return;                              // 阈值内当点击，不捕获、不滚动
      moved = true;
      el.setPointerCapture?.(e.pointerId);
      el.classList.add("dragging");
    }
    el.scrollLeft = startLeft - dx;
  });
  const stop = () => {
    if (!dragging) return;
    dragging = false;
    el.classList.remove("dragging");
  };
  el.addEventListener("pointerup", stop);
  el.addEventListener("pointercancel", stop);
  // 真拖动后浏览器仍会派发一次 click：捕获阶段拦下，避免误触子元素
  el.addEventListener("click", e => {
    if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; }
  }, true);
  return el;
}

/** 溢出提示更新（03I）：总宽超出容器才显示——scrollWidth 实测，不写死"超过 N 个"。 */
export function updateOverflowHint(el, hint) {
  if (!el || !hint) return;
  hint.hidden = !(el.scrollWidth > el.clientWidth + 4);
}
