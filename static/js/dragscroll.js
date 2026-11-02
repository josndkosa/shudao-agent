// dragscroll.js — 横向拖动滚动（03I：day-tabs 与 map-row 共用）
// overflow-x: auto 支持触摸板横滑和 Shift+滚轮，但不支持「鼠标按住内容直接拖」——
// 用户说"拖不动"多半就是试了直接拖。触摸设备走原生滚动，不拦截。
// 用原生 Pointer Events，零依赖；别抢按钮/链接/输入件的按下。

export function enableDragScroll(el) {
  if (!el || !el.addEventListener) return el;
  let dragging = false, startX = 0, startLeft = 0;

  el.addEventListener("pointerdown", e => {
    if (e.pointerType === "touch") return;                       // 触摸交给原生
    if (e.target?.closest?.("button, a, input, select")) return;  // 别抢控件的按下
    dragging = true;
    startX = e.clientX;
    startLeft = el.scrollLeft;
    el.setPointerCapture?.(e.pointerId);
    el.classList.add("dragging");
  });
  el.addEventListener("pointermove", e => {
    if (!dragging) return;
    el.scrollLeft = startLeft - (e.clientX - startX);
  });
  const stop = () => {
    if (!dragging) return;
    dragging = false;
    el.classList.remove("dragging");
  };
  el.addEventListener("pointerup", stop);
  el.addEventListener("pointercancel", stop);
  return el;
}

/** 溢出提示更新（03I）：总宽超出容器才显示——scrollWidth 实测，不写死"超过 N 个"。 */
export function updateOverflowHint(el, hint) {
  if (!el || !hint) return;
  hint.hidden = !(el.scrollWidth > el.clientWidth + 4);
}