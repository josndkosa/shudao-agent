"""决策报告渲染（03L 任务L6，补 03K 砍掉的任务 C）。

这是答辩时「评委可以自己下载一份证据」的交付物——下载下来的 md 里
每个决策的 reason 原样在。六节结构固定（缺一节算没做完），reason 全量不截断，
不做 PDF（中文字体渲染是运维坑，Markdown 交给浏览器打印）。

Python 版（服务端 /api/plan/report）与 JS 版（static/js/report.js，断网 Mock 导出）
结构同构：六节标题逐字一致（tests/test_report.py 锁）；内容允许实现差异，
但两边都只写「事件流 / 行程 / meta 里出现过」的信息——不润色、不总结、不编造。
"""
from __future__ import annotations

import re
from datetime import datetime

# 六节标题——与 static/js/report.js 的 SECTION_TITLES 逐字一致（改一处改两处）
SECTION_TITLES = [
    "1. 请求摘要",
    "2. 逐日行程",
    "3. 决策链（事件流全量）",
    "4. 校验与修复",
    "5. 预算明细",
    "6. 数据与版本",
]

_NEED_THOUGHT = re.compile(r"偏好\[([^\]]*)\]")
_NEED_BUDGET = re.compile(r"预算(\d+)元")


def unwrap_detail(ev: dict) -> object:
    """与前端 static/js/view.js 的 payload(ev) 语义等价：
    detail 是 object 且含 'detail' 键 → 取内层；否则原样返回。

    规则必须与前端逐字一致（改一处改两处）：
    前端判定 `d && typeof d === 'object' && !Array.isArray(d) && 'detail' in d`
    ——对应 Python 的 isinstance(d, dict) 且 'detail' in d（JSON object 即 dict，
    天然排除 list）。直读 ev.detail 会拿到嵌套外壳：violation/advisory 等事件
    的载荷在内层，读错层级 = 第 4 节静默空白（03H 任务 H5 那次 P0 的重演）。
    """
    d = ev.get("detail")
    if isinstance(d, dict) and "detail" in d:
        return d["detail"]
    return d


def _esc(s: object) -> str:
    """Markdown 表格单元格转义：竖线与换行。"""
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def _fmt_money(v) -> str:
    try:
        return f"¥{v:g}"
    except (TypeError, ValueError):
        return "—"


def _thought_reqs(timeline: list[dict]) -> tuple[list[str], str]:
    """从「解析行程需求」thought 事件的 reason 里提取偏好标签与预算上限。

    只用事件流里出现过的原文（如「3天 预算3000元 偏好['美食', '文化']」），
    不从别处拼装——报告铁律：不出现事件流/行程之外的信息。
    """
    tags: list[str] = []
    budget = ""
    for ev in timeline:
        if ev.get("type") == "thought" and "需求" in ev.get("title", ""):
            m = _NEED_THOUGHT.search(ev.get("reason", ""))
            if m:
                tags = [t.strip().strip("'\"") for t in m.group(1).split(",") if t.strip()]
            mb = _NEED_BUDGET.search(ev.get("reason", ""))
            if mb:
                budget = mb.group(1)
            break
    return tags, budget


def _mode_of(itinerary: dict, timeline: list[dict]) -> str:
    """引擎模式：itinerary.mode 优先，缺失时回落 timeline 首条 start 事件的 detail.mode。"""
    m = itinerary.get("mode")
    if not m:
        for ev in timeline:
            d = unwrap_detail(ev)
            if isinstance(d, dict) and d.get("mode"):
                m = d["mode"]
                break
    return str(m or "unknown")


def render_report(itinerary: dict, timeline: list[dict], meta: dict | None = None) -> str:
    """渲染六节 Markdown 决策报告。meta：{data_version, contract_version, poi_count, source}。"""
    meta = meta or {}
    days = itinerary.get("days", [])
    budget = itinerary.get("budget", {}) or {}
    mode = _mode_of(itinerary, timeline)
    tags, user_budget = _thought_reqs(timeline)
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_pois = sum(1 for d in days for it in d.get("items", []) if it.get("type") == "poi")

    L: list[str] = []
    L.append("# 蜀道智行 · 决策报告")
    L.append("")
    L.append(f"> 生成时间：{gen_time} ｜ 引擎模式：{mode} ｜ "
             f"事件数：{len(timeline)} ｜ 行程点数：{n_pois}")
    L.append("")

    # ── 1. 请求摘要 ──
    L.append(f"## {SECTION_TITLES[0]}")
    L.append("")
    cities = list(dict.fromkeys(d.get("city", "") for d in days))
    L.append(f"- 天数：{len(days)} 天")
    L.append(f"- 城市序列：{' → '.join(cities) if cities else '—'}")
    L.append(f"- 偏好标签：{'、'.join(tags) if tags else '—'}")
    L.append(f"- 预算上限：{f'¥{user_budget}' if user_budget else '—'}"
             f"（预估总花费见第 5 节）")
    L.append(f"- 引擎模式：{mode}（offline=离线确定性管线 / online=DeepSeek 在线规划）")
    L.append("")

    # ── 2. 逐日行程 ──
    L.append(f"## {SECTION_TITLES[1]}")
    L.append("")
    for d in days:
        L.append(f"### Day {d.get('day')} · {d.get('city')}")
        L.append("")
        L.append("| 时间 | 点位 | 时长 | 票价 | 命中标签 |")
        L.append("|---|---|---|---|---|")
        for it in d.get("items", []):
            if it.get("type") == "poi":
                L.append(
                    f"| {it.get('arrival', '—')}–{it.get('departure', '—')} "
                    f"| {_esc(it.get('name'))} "
                    f"| {it.get('visit_hours', '—')}h "
                    f"| {_fmt_money(it.get('ticket'))} "
                    f"| {_esc('、'.join(it.get('tags', [])))} |")
            elif it.get("type") == "intercity":
                L.append(f"| {it.get('departure', '—')}–{it.get('arrival', '—')} "
                         f"| ⇄ {_esc(it.get('label'))}（城际，不计点数） | — | — | — |")
            elif it.get("type") == "meal":
                L.append(f"| {it.get('arrival', '—')}–{it.get('departure', '—')} "
                         f"| {_esc(it.get('label'))} | — | — | — |")
        L.append("")

    # ── 3. 决策链（事件流全量）──
    L.append(f"## {SECTION_TITLES[2]}")
    L.append("")
    L.append("reason 原文全量，不做任何截断或改写。")
    L.append("")
    L.append("| seq | stage | type | title | reason |")
    L.append("|---|---|---|---|---|")
    for ev in timeline:
        L.append(f"| {ev.get('seq')} | {_esc(ev.get('stage'))} | {_esc(ev.get('type'))} "
                 f"| {_esc(ev.get('title'))} | {_esc(ev.get('reason'))} |")
    L.append("")

    # ── 4. 校验与修复 ──
    L.append(f"## {SECTION_TITLES[3]}")
    L.append("")
    for sub, label in (("violation", "硬违规（进修复循环）"),
                       ("fix", "修复动作（detail.removed 携带被移除点位 ID）"),
                       ("advisory", "软提醒（不阻断不修复）"),
                       ("unfixable", "不可自动修复（收敛检测停止重试）")):
        evs = [e for e in timeline if e.get("type") == sub]
        L.append(f"### {sub}（{label}）")
        L.append("")
        if not evs:
            L.append("（本行程无此类事件）")
            L.append("")
            continue
        L.append("| seq | 天 | 规则 | 载荷原文 | 事件 reason |")
        L.append("|---|---|---|---|---|")
        for ev in evs:
            vd = unwrap_detail(ev)          # 嵌套取内层 / 扁平原样——与前端 payload 同语义
            if isinstance(vd, dict):
                day = vd.get("day", "")
                rule = vd.get("rule", vd.get("violation", ""))
                removed = vd.get("removed")
                if removed is not None:
                    payload_txt = f"removed={removed}"
                else:
                    payload_txt = _esc({k: v for k, v in vd.items() if k != "detail"})
            else:
                day, rule, payload_txt = "", "", _esc(vd)
            L.append(f"| {ev.get('seq')} | {day} | {_esc(rule)} | {payload_txt} "
                     f"| {_esc(ev.get('reason'))} |")
        L.append("")

    # ── 5. 预算明细 ──
    L.append(f"## {SECTION_TITLES[4]}")
    L.append("")
    L.append("| 门票 | 餐饮 | 交通（市内+城际合并口径，数据源未拆分） | 总计 | 日均 |")
    L.append("|---|---|---|---|---|")
    L.append(f"| {_fmt_money(budget.get('tickets'))} | {_fmt_money(budget.get('meals'))} "
             f"| {_fmt_money(budget.get('transit'))} | {_fmt_money(budget.get('total'))} "
             f"| {_fmt_money(budget.get('per_day'))} |")
    if user_budget:
        # 03M P0-04：结论必须反映真实状态，不许无条件写「通过」——
        # ① 总花费超上限 → 报超额与差额；② 校验段有「仍残留违规」done 事件 → 如实标注；
        # ③ 费用是本地快照+固定费率估算，统一用「预估」而非「实际总花费」。
        total_v = budget.get("total") or 0
        over = round(total_v - int(user_budget), 1)
        residual = any(ev.get("type") == "done" and ev.get("stage") == "validate"
                       and "残留" in ev.get("title", "") for ev in timeline)
        if over > 0:
            verdict = f"超出预算 ¥{over}，未通过 V4 预算校验"
        elif residual:
            verdict = "预算内，但校验段仍有硬违规残留（如实标注）"
        else:
            verdict = "V4 预算校验通过"
        L.append("")
        L.append(f"预估总花费 {_fmt_money(total_v)} / 预算上限 ¥{user_budget}（{verdict}）")
    L.append("")

    # ── 6. 数据与版本 ──
    L.append(f"## {SECTION_TITLES[5]}")
    L.append("")
    dv = meta.get("data_version")
    cv = meta.get("contract_version")
    L.append(f"- 数据层版本：{dv if dv else '本地演示快照（后端未启动，运行时版本不可读——如实标注）'}")
    L.append(f"- 事件契约版本：{cv if cv else '本地演示快照（后端未启动，运行时版本不可读——如实标注）'}")
    if meta.get("poi_count"):
        L.append(f"- POI 快照：{meta['poi_count']} 点（本地快照）")
    L.append(f"- 引擎模式：{mode}")
    L.append(f"- 生成时间：{gen_time}")
    L.append("")
    return "\n".join(L)
