# -*- coding: utf-8 -*-
"""生成 ppt/蜀道智行.pptx（05 任务单：16:9 / 18 页 / 微软雅黑）。

2026-11-02 视觉优化（用户指令）：深色主题 → **简洁清爽的浅色系**；
同步修格式规范：标题统一 32pt、表格统一 18pt、正文 19pt、注脚 15pt、
页码 12pt，行距统一 1.2 倍、段后间距统一、全部左对齐版式一致。
浅色底对比度校验：正文 #1F2328（≈16:1）、次要 #57606A（≈6:1）、
强调橙 #BC4C00（≈5.4:1）/ 蓝 #0969DA（≈5.5:1）均高于 WCAG AA 4.5:1。

素材口径（03K 任务E2：易变计数由 _ci_counts() 重出时现读，不写死会过期的数字）：
- 15 城 237 点（server/data 实测）；debug-log 十七轮；幻觉 POI 17→0（历史事实，稳定）
- 测试用例数 / 冒烟步数 / 任务单份数：重出时自动实测（实测失败回落「—」，绝不印编造数）
- docs/images/ 产品截图未拍——配图位如实写「待补录」，绝不画假界面
python-pptx 仅为文档工具依赖（requirements-dev.txt），不进主依赖。
"""
import re
import subprocess
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE as MSO_LINE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# ── 浅色主题色板（清爽白底；强调色按白底对比度加深）──
BG = RGBColor(0xFF, 0xFF, 0xFF)     # 背景：纯白
PANEL = RGBColor(0xF6, 0xF8, 0xFA)  # 面板：极浅灰
TEXT = RGBColor(0x1F, 0x23, 0x28)   # 正文：近黑（对比度 ≈16:1）
DIM = RGBColor(0x57, 0x60, 0x6A)    # 次要：中灰（≈6:1）
CD = RGBColor(0xBC, 0x4C, 0x00)     # 成都暖橙（加深保对比 ≈5.4:1）
CQ = RGBColor(0x09, 0x69, 0xDA)     # 重庆江蓝（≈5.5:1）
BAD = RGBColor(0xCF, 0x22, 0x2E)    # 违规朱红（≈4.8:1）
OK = RGBColor(0x1A, 0x7F, 0x37)     # 通过绿（≈4.5:1）
HEAD_BG = RGBColor(0xEA, 0xEE, 0xF2)  # 表头底色：浅灰蓝
LINE = RGBColor(0xD0, 0xD7, 0xDE)   # 边框线色
FONT = "微软雅黑"

W, H = Inches(13.333), Inches(7.5)

# ── 实测口径（03K 任务E2）：PPT 是快照型材料，数字必须与重出时点一致 ──
def _ci_counts():
    """pytest 用例数 / 冒烟步数 / 任务单份数——重出时现读实测值。
    任一步失败返回 None（文案回落「—」）：宁可缺数也不印一个编造的数。"""
    root = Path(__file__).resolve().parent.parent
    out = {}
    try:
        # 注意：pytest 9 的 -q collect 模式不再输出总摘要行，用非 quiet 模式取「N tests collected」
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "--collect-only", "-p", "no:warnings"],
                           cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        m = re.search(r"(\d+) tests? collected", r.stdout)
        out["tests"] = int(m.group(1)) if m else None
    except Exception:
        out["tests"] = None
    try:
        r = subprocess.run(["node", "scripts/smoke_frontend.mjs"],
                           cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        m = re.search(r"冒烟通过[（(](\d+) 步[）)]", r.stdout + r.stderr)
        out["smoke"] = int(m.group(1)) if m else None
    except Exception:
        out["smoke"] = None
    try:
        out["prompts"] = len(list((root / "codearts_proof" / "prompts" / "_已执行").glob("*.md")))
    except Exception:
        out["prompts"] = None
    return out


_N = _ci_counts()
T_STR = str(_N["tests"]) if _N["tests"] else "—"
S_STR = str(_N["smoke"]) if _N["smoke"] else "—"
P_STR = str(_N["prompts"]) if _N["prompts"] else "—"


def set_font(run, size, color=TEXT, bold=False):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    f.name = FONT
    rPr = run._r.get_or_add_rPr()          # 中文字体须显式设 eastAsia
    for tag in ("a:ea", "a:cs"):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {})
            rPr.append(e)
        e.set("typeface", FONT)


def txbox(slide, lf, t, w, h, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """lines: [(text, size, color, bold, space_after_pt), ...]
    版式统一（2026-11-02 视觉优化）：行距 1.2 倍、段后间距按 lines 给定、左对齐。
    """
    tb = slide.shapes.add_textbox(lf, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    first = True
    for text, size, color, bold, gap in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        p.line_spacing = 1.2
        p.space_after = Pt(gap)
        r = p.add_run()
        r.text = text
        set_font(r, size, color, bold)
    return tb


def rect(slide, lf, t, w, h, fill=PANEL, line=None, dash=False, radius=None):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, lf, t, w, h)
    if radius is not None:  # 0=直角
        try:
            sp.adjustments[0] = radius
        except Exception:
            pass
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(1.25)
        if dash:
            sp.line.dash_style = MSO_LINE.DASH
    sp.shadow.inherit = False
    return sp


def arrow(slide, lf, t, w, h, color=DIM):
    sp = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, lf, t, w, h)
    sp.fill.solid()
    sp.fill.fore_color.rgb = color
    sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def label(sp, text, size=16, color=TEXT, bold=False):
    tf = sp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    set_font(r, size, color, bold)


def new_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])   # blank
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s


def header(slide, title, sub=None, accent=CD):
    """页眉：左上角竖条 + 标题（结论式）；标题统一 32pt（规范修正）"""
    rect(slide, Inches(0.55), Inches(0.42), Inches(0.09), Inches(0.78), fill=accent)
    lines = [(title, 32, TEXT, True, 4)]
    if sub:
        lines.append((sub, 15, DIM, False, 0))
    txbox(slide, Inches(0.85), Inches(0.38), Inches(12.0), Inches(1.1), lines)


def bullets(slide, items, top=Inches(1.75), left=Inches(0.85), width=Inches(11.6), size=19, height=None):
    lines = []
    for it in items:
        if isinstance(it, tuple):
            text, color = it
        else:
            text, color = it, TEXT
        lines.append(("▸ " + text, size, color, False, 10))
    # 高度按 top 自适应（底边距 0.45″）：原硬编码 4.8″ 在 top=5.0 时框底 9.8″ 越出页面
    if height is None:
        height = Inches(7.05) - top
    txbox(slide, left, top, width, height, lines)


def footer(slide, no):
    txbox(slide, Inches(12.35), Inches(7.02), Inches(0.8), Inches(0.4),
          [(f"{no} / 18", 12, DIM, False, 0)], align=PP_ALIGN.RIGHT)


prs = Presentation()
prs.slide_width, prs.slide_height = W, H

# ═══════════ P1 封面 ═══════════
s = new_slide(prs)
rect(s, Inches(0), Inches(0), W, H, fill=BG)
rect(s, Inches(0.9), Inches(1.05), Inches(0.14), Inches(1.6), fill=CD)
txbox(s, Inches(1.25), Inches(1.0), Inches(11.2), Inches(2.4), [
    ("蜀道智行", 54, TEXT, True, 6),
    ("西南行程规划智能体", 30, CD, False, 0),
])
txbox(s, Inches(1.25), Inches(3.05), Inches(11.0), Inches(0.8), [
    ("规划 → 校验 → 叙事 的三段式管线，把 Agent 的决策过程做成可回放的产品", 20, DIM, False, 0)])
rect(s, Inches(1.25), Inches(4.35), Inches(10.9), Inches(1.5), fill=PANEL)
txbox(s, Inches(1.55), Inches(4.55), Inches(10.4), Inches(1.2), [
    ("参赛组别：高校组 ｜ 队伍名称：__________ ｜ 本人专业：__________", 16, TEXT, False, 6),
    ("联系人与联系方式：__________ ｜ 版本 v1.0 ｜ 日期 __________", 16, TEXT, False, 0)])
txbox(s, Inches(1.25), Inches(6.55), Inches(11.0), Inches(0.5), [
    ("2026 华为开发者大赛 · 智能体创新赛（西南赛区）", 14, DIM, False, 0)])

# ═══════════ P2 场景分析 ═══════════
s = new_slide(prs)
header(s, "问题不在「能不能生成行程」，而在「靠不靠谱、能不能解释」", "场景分析 · 痛点与选题贴合")
bullets(s, [
    ("开放时段 / 预约难度 / 人流高峰信息分散，人肉查攻略排行程", TEXT),
    ("重庆立体地形：爬坡强度与体力分配被忽略，日程排到 21 点还在爬坡", TEXT),
    ("亲子出行要「强度可控 + 开放窗口匹配」，人工排几乎必然踩坑", TEXT),
], top=Inches(1.85))
rect(s, Inches(0.85), Inches(4.15), Inches(11.6), Inches(2.3), fill=PANEL)
txbox(s, Inches(1.15), Inches(4.4), Inches(11.0), Inches(1.9), [
    ("地域贴合：赛题定义西南赛区 = 川、渝、云、贵、桂、海、藏——数据层 15 城快照直接对齐赛区划分，不是自选叙事", 17, TEXT, False, 8),
    ("高校组贴合：定位 AI Agent 课程实训 / 示范项目——换一组 POI 快照即可复现到其他城市与学科场景", 17, TEXT, False, 8),
    ("完整展示「AI Coding → 工程化交付」闭环，学生可照着跑通", 17, TEXT, False, 0),
])

# ═══════════ P3 整体架构 ═══════════
s = new_slide(prs)
header(s, "三段式管线：每段职责单一、可独立单测", "方案设计 · 整体架构")
# 布局修正：6 块（4 主 + 2 前端）原总宽 15.2″ 超出页宽 13.33″——
# 块宽 2.15→1.85、间距 0.32→0.26，总宽 12.4″ + 左缘 0.7″，右留边距 0.23″
bw, bh, gap, y1 = Inches(1.85), Inches(1.05), Inches(0.26), Inches(2.05)
x = Inches(0.7)
blocks = [
    ("用户输入\n天数/预算/偏好", PANEL, TEXT),
    ("规划段 Planner\n贪心装箱 / LLM FC", PANEL, CD),
    ("校验段 Validator\n纯规则 V1–V5", PANEL, OK),
    ("叙事段 Narrator\nLLM / 模板兜底", PANEL, CQ),
]
for i, (t, fill, lc) in enumerate(blocks):
    sp = rect(s, x, y1, bw, bh, fill=fill, line=lc)
    label(sp, t.replace("\n", " · "), 14, TEXT, True)
    if i < 3:
        arrow(s, x + bw + Inches(0.02), y1 + Inches(0.34), Inches(0.22), Inches(0.36))
    x += bw + gap
# 前端两块（图注字号与其他块统一 14pt）
x2 = x
for t, lc in [("前端 · 分城 SVG 路网图", CD), ("前端 · 可倒带决策时间轴", BAD)]:
    sp = rect(s, x2, y1, bw, bh, fill=PANEL, line=lc)
    label(sp, t, 14, TEXT, True)
    arrow(s, x2 - Inches(0.24), y1 + Inches(0.34), Inches(0.22), Inches(0.36))
    x2 += bw + gap
# 回流标注（校验段 → 规划段）：左向箭头才符合「回流」语义
back = s.shapes.add_shape(MSO_SHAPE.LEFT_ARROW, Inches(3.5), Inches(3.35), Inches(0.9), Inches(0.34))
back.fill.solid()
back.fill.fore_color.rgb = BAD
back.line.fill.background()
back.shadow.inherit = False
txbox(s, Inches(3.05), Inches(3.3), Inches(9.4), Inches(0.5), [
    ("⟲ 硬违规回流规划段定向修复：最多 3 轮 + 收敛检测（同一违规集不变即停，不空转）", 14, BAD, False, 0)],
    align=PP_ALIGN.CENTER)
# EventBus 长条
eb = rect(s, Inches(0.7), Inches(4.35), Inches(11.95), Inches(0.85), fill=None, line=CD)
label(eb, "EventBus 事件流——每条决策带 reason（seq / stage / type / title / reason / detail），贯穿全流程", 15, CD, True)
txbox(s, Inches(0.7), Inches(5.5), Inches(11.95), Inches(1.2), [
    (f"三个要点：① 三段职责单一、各段可独立单测（pytest {T_STR} 个用例 + 前端冒烟 {S_STR} 步）", 16, TEXT, False, 6),
    ("② 事件流是一等公民——它是前端可倒带回放的数据源  ③ 单次管线：行程与事件流同源（在线模式也只跑一次）", 16, TEXT, False, 0),
])

# ═══════════ P4 为什么不是多 Agent ═══════════
s = new_slide(prs)
header(s, "一个诚实的三段式管线，胜过包装出来的「多 Agent」", "方案设计 · 架构取舍")
bullets(s, [
    ("一个 Function Calling 循环 + 角色切换包装成「多 Agent」，经不起架构层面的追问", TEXT),
    ("三段式管线：每段独立可测、离线可跑、规则可审计——更诚实的工程表达", TEXT),
    ("校验段零 LLM：五张规则表全量可单测，「智能」与「可靠」分离", TEXT),
    ("落点：技术架构 15 分中「代码结构规范性、可维护性」的直接回应", TEXT),
], top=Inches(2.0))
txbox(s, Inches(0.85), Inches(5.9), Inches(11.6), Inches(0.7), [
    ("答辩预期问题「为什么不用多 Agent 框架」：拆到多 Agent 不会让行程更靠谱——可靠来自规则校验，不来自角色数量。", 15, DIM, False, 0)])

# ═══════════ P5 数据层 ═══════════
s = new_slide(prs)
header(s, "237 个 POI 厚字段快照：决策依据从「一个分数」变成一组硬约束", "方案设计 · 数据层")
bullets(s, [
    ("西南 15 城 237 点本地快照（每城独立 JSON，实测口径，见 /api/meta）", TEXT),
    ("厚字段：开放时段 / 预约难度 / 人流高峰 / 爬坡强度 / 亲子友好度 / 夜间体验 / 建议时长", TEXT),
    ("赛题版本用本地快照保演示稳定；数据层可对接 OTA 开放接口（server/cloud/ 已预留边界）", TEXT),
    ("新增城市零代码改动：放一个含 city 字段的 json 进 server/data/ 即被自动收录", CD),
], top=Inches(2.0))
txbox(s, Inches(0.85), Inches(5.9), Inches(11.6), Inches(0.7), [
    ("数据字段规范见 server/data/schema.md；不使用任何外部地图服务（自研经纬度→SVG 投影）。", 15, DIM, False, 0)])

# ═══════════ P6 规划段 ═══════════
s = new_slide(prs)
header(s, "规划段：每一步都发带 reason 的事件", "核心功能 · Planner")
bullets(s, [
    ("偏好打分 → 多城按候选池分数比例分天 → 逐日贪心装箱 → 最近邻排序（夜间点压轴）→ 时间线推算", TEXT),
    ("自动选城：贪心最近邻（起点 = 候选池总分最高城，逐跳取 ≤4h 可达的最高分城市，不绕路）", TEXT),
    ("多城支持：30 天 / 6 城等极端参数可跑（POI 密度决定单城上限，排不满会如实发事件说明）", TEXT),
    ("每步决策（选点 / 分天 / 摘点）都带 reason 进入事件流，前端可回放", CD),
], top=Inches(2.0))

# ═══════════ P7 校验段 ═══════════
s = new_slide(prs)
header(s, "校验段零 LLM：五张规则表 + 软硬分级 + 地形分档", "核心功能 · Validator")
rows = [
    ("规则", "含义", "阈值", "severity"),
    ("V1", "日时长 / 收班", "08:30–22:00；跨城日容量扣城际时长", "hard"),
    ("V2", "开放窗口", "到离时间须落在 POI 开放时段内", "hard"),
    ("V3", "体力强度", "Σ(slope+crowd×0.4) ≤ 按地形分档", "soft"),
    ("V4", "预算", "门票+餐饮+交通 ≤ 请求预算", "hard"),
    ("V5", "亲子友好", "排除亲子友好度 < 2 的点", "hard"),
]
tbl = s.shapes.add_table(6, 4, Inches(0.85), Inches(1.8), Inches(11.6), Inches(2.9)).table
tbl.columns[0].width = Inches(1.0)
tbl.columns[1].width = Inches(1.7)
tbl.columns[2].width = Inches(6.3)
tbl.columns[3].width = Inches(2.6)
for ri, row in enumerate(rows):
    for ci, val in enumerate(row):
        c = tbl.cell(ri, ci)
        c.fill.solid()
        c.fill.fore_color.rgb = PANEL if ri else HEAD_BG
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        c.margin_left, c.margin_top = Inches(0.12), Inches(0.03)
        p = c.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = val
        if ri == 0:
            set_font(r, 18, DIM, True)
        elif ci == 3:
            set_font(r, 18, BAD if val == "hard" else CD, True)
        else:
            set_font(r, 18, TEXT, val == "V3")
bullets(s, [
    ("硬违规自动回流修复（≤3 轮 + 收敛检测）；软硬分级是本页核心——见下", TEXT),
    ("V3 强度没有唯一正确的删点解：系统如实提示、把决策权交还用户，不自动删点（删会误伤必游地标与夜景压轴）", CD),
    ("地形分档：同样强度 8.5，在成都只是多走路，在高原是在海拔上走——阈值随地形收紧（盆地 8.5 / 丘陵 8.0 / 喀斯特 7.5 / 高原 7.0 / 极高海拔 6.0 / 热带 8.0）", TEXT),
], top=Inches(5.0), size=16)

# ═══════════ P8 叙事段 + 断网保命 ═══════════
s = new_slide(prs)
header(s, "断网也能完整演示：三态开关是刻意设计，不是妥协", "核心功能 · 叙事段与降级链")
bullets(s, [
    ("SD_LLM_MODE 三态开关：auto（默认）/ offline（断网保命）/ online（显式意图）", TEXT),
    ("叙事段：在线 LLM 导览词 / 离线模板兜底，产出结构完全同构", TEXT),
    ("CLI 离线管线仅用 Python 标准库；前端零构建零外链零 CDN——断网时页面 100% 自包含", TEXT),
    ("在线模式另有公网防护：SD_ALLOW_ONLINE 开关 + IP 限流 + 输入上限（422/429）", DIM),
], top=Inches(2.0))
txbox(s, Inches(0.85), Inches(5.7), Inches(11.6), Inches(1.0), [
    ("诚实口径：在线分支接 DeepSeek（OpenAI 兼容 FC），实测幻觉 POI 17→0、零降级；", 16, TEXT, False, 6),
    ("演示与录屏一律用离线模式——确定性输出，每次画面完全一致。", 16, TEXT, False, 0)])

# ═══════════ P9 可倒带时间轴（王牌页）═══════════
s = new_slide(prs)
header(s, "可倒带决策时间轴：回答「为什么第二天排这三个点」", "核心功能 · 差异化王牌")
bullets(s, [
    ("痛点：Agent 的决策过程通常是黑盒或滚动日志，看完就没了", TEXT),
    ("本作品：每个决策带 reason，前端做成可拖动、可回放的时间轴", TEXT),
    ("回放到任意一步：地图点位同步点亮、行程卡随之变化", TEXT),
    ("回放器支持播放/暂停/单步/倍速/事件搜索与点击定位", TEXT),
], top=Inches(1.95), width=Inches(6.6))
ph = rect(s, Inches(7.8), Inches(1.95), Inches(4.7), Inches(4.4), fill=None, line=DIM, dash=True)
tf = ph.text_frame
tf.word_wrap = True
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
r = p.add_run()
r.text = "截图待补录：player.png\n\n（回放器真实界面）"
set_font(r, 18, DIM, False)
p2 = tf.add_paragraph()
p2.alignment = PP_ALIGN.CENTER
r2 = p2.add_run()
r2.text = "界面已冻结；录视频后与视频画面一致补拍\n规格见 docs/images/README.md"
set_font(r2, 13, DIM, False)

# ═══════════ P10 对话式交互 ═══════════
s = new_slide(prs)
header(s, "对话栏：一句话开始规划、一句话微调、「记住」我的偏好", "核心功能 · 对话式交互")
bullets(s, [
    ("一句话规划：「我在北京，想去成都和重庆玩3天」→ 抽取参数回填表单（可见可改）→ 自动规划", TEXT),
    ("对话改行程：「第二天太赶」→ 只重排那一天（容量收紧→重选→重建→复查），回放出现「第二幕」", TEXT),
    ("偏好记忆：「记住：我带娃，不去博物馆」→ 偏好画像存用户主目录，下次规划自动带上（显式优先）", TEXT),
    ("时间线计算始终在本地：LLM 只负责意图与顺序，不负责编时间", CD),
], top=Inches(2.0))
txbox(s, Inches(0.85), Inches(5.9), Inches(11.6), Inches(0.8), [
    ("抽取与规划分离：抽取层双实现（在线 LLM 纯 JSON / 离线正则+词表），断网同样可用；画像不进仓库不进提交包。", 15, DIM, False, 0)])

# ═══════════ P11 可视化 ═══════════
s = new_slide(prs)
header(s, "分城 SVG 自绘路网：零构建、零外链、零 CDN", "核心功能 · 可视化")
bullets(s, [
    ("成渝各一幅独立投影（250km 尺度下同图会挤压成团）+ 城际连线；多城动态渲染 N 幅，容器内横向滚动", TEXT),
    ("按天着色 / 路线描绘动效 / 点位 tooltip / 负载与预算条", TEXT),
    ("双页面：index.html 品牌首页（定位+数据+CTA）/ plan.html 工作台；旧链接自动透传，零破坏", TEXT),
    ("参数条 + 对话栏 + 决策回放抽屉：一屏完成「输入→生成→解释」", TEXT),
], top=Inches(1.95), width=Inches(6.6))
ph = rect(s, Inches(7.8), Inches(1.95), Inches(4.7), Inches(4.4), fill=None, line=DIM, dash=True)
tf = ph.text_frame
tf.word_wrap = True
tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
r = p.add_run()
r.text = "截图待补录：map.png\n\n（双城路网真实界面）"
set_font(r, 18, DIM, False)
p2 = tf.add_paragraph()
p2.alignment = PP_ALIGN.CENTER
r2 = p2.add_run()
r2.text = "界面已冻结；录视频后与视频画面一致补拍\n规格见 docs/images/README.md"
set_font(r2, 13, DIM, False)

# ═══════════ P12 创新亮点 ═══════════
s = new_slide(prs)
header(s, "四个差异化创新点", "创新亮点")
items = [
    ("决策过程即产品", "把 Agent 的 reason 变成可回放的可视化资产，而不是日志"),
    ("规则引擎做校验", "LLM 产出 + 纯规则校验 + 违规回流修复——「智能」与「可靠」分离"),
    ("软硬分级 + 地形分档", "强度是软约束就如实提示不删点；阈值随盆地/丘陵/喀斯特/高原/热带收紧"),
    ("分城 SVG 自绘 + 厚字段快照", "不依赖任何地图服务；断网保命，且决策依据可解释"),
]
top = Inches(2.0)
for i, (t, d) in enumerate(items):
    y = Inches(1.95 + i * 1.18)
    rect(s, Inches(0.85), y, Inches(11.6), Inches(1.0), fill=PANEL)
    txbox(s, Inches(1.1), y + Inches(0.14), Inches(4.2), Inches(0.75), [
        (f"{i+1} · {t}", 19, CD if i in (0, 2) else TEXT, True, 0)])
    txbox(s, Inches(5.4), y + Inches(0.18), Inches(6.9), Inches(0.7), [
        (d, 16, TEXT, False, 0)])

# ═══════════ P13 码道 · 覆盖度 + 案例一 ═══════════
s = new_slide(prs)
header(s, "码道全流程覆盖：从脚手架到文档；排错一律先红后绿", "码道应用成果（一）开发全流程覆盖度")
bullets(s, [
    ("环境搭建 / 代码生成 / 调试排错 / 文档生成 四类活动全覆盖（证据见 codearts_proof/）", TEXT),
    ("经典案例：跨城日 V1 误报——城际 1.8h 计入占用而容量未预留，阈值被压到 20:13，磁器口、湖广会馆被误删", TEXT),
    ("定位：对比 span 与 cap 的口径差 → 先写红测试再改实现 → 转绿", TEXT),
    ("before/after：baseline-demo.json（修复前）vs demo.json（修复后，地标回归）", TEXT),
], top=Inches(1.95), size=18)
txbox(s, Inches(0.85), Inches(6.1), Inches(11.6), Inches(0.6), [
    ("红转绿过程记录在 debug-log；本轮产出 12 个回归测试。", 15, DIM, False, 0)])

# ═══════════ P14 码道 · 案例二（幻觉）═══════════
s = new_slide(prs)
header(s, "17 个幻觉 POI：只有真实运行才会暴露的缺陷", "码道应用成果（二）调试排错 · 在线模式实测", accent=BAD)
bullets(s, [
    ("现象：首次真实调用 LLM，工具结果被硬截断在 JSON 结构中间，模型把残缺 JSON「补全」成 17 个不存在的 POI", TEXT),
    ("探针实测：五城工具结果全量 5624–8024 字符，全部超 4000 截断线——每城必烂，不是偶发", TEXT),
    ("根因：精简投影函数 _poi_brief 写了却从未被调用；修复四件套（投影接入 / 整点截断 / prompt 禁造 / 解析兜底）后幻觉 17 → 0", OK),
    ("证据：debug-log 第十七轮 + codearts_proof/07-在线模式实测/（完整 CLI 输出存档）", TEXT),
], top=Inches(1.95), size=18)
rect(s, Inches(0.85), Inches(5.55), Inches(11.6), Inches(1.2), fill=PANEL)
txbox(s, Inches(1.15), Inches(5.75), Inches(11.0), Inches(0.9), [
    ("工程教训一：写好的工具函数要检查是否真的被调用", 17, CD, True, 4),
    ("工程教训二：断网离线路径与在线路径的缺陷类型不同——两条路都得跑（离线测试永远测不到「模型补全残缺 JSON」）", 17, TEXT, False, 0)])

# ═══════════ P15 码道 · Prompt 质量与证明材料 ═══════════
s = new_slide(prs)
header(s, f"{P_STR} 份任务单：背景 → 硬约束 → 验收标准；两次返工如实留存", "码道应用成果（三）Prompt 质量与证明材料")
bullets(s, [
    ("组织方式：背景与现状 → 硬约束（不许做的事）→ 逐条任务（含可执行验收标准）→ 交付要求", TEXT),
    ("两次视觉返工（03D 测绘图鉴 → 03F 瑞士网格）被人工评审否决后重做，原文如实归档——人机协作的证据", TEXT),
    ("最有价值的契约演进：LLM 输出从「整份行程」收窄为「只报 poi_id，其余本地重算」——幻觉面从字段级收窄到 id 选择级", TEXT),
    ("证明材料 01–07 目录（截图 + README）；W1 截图缺口如实申报，以任务单原文 + git 历史替代", TEXT),
    ("本 PPT、讲稿、分镜由码道生成（IDE 模式完成，如实说明）；开发期 AI ≠ 运行期模型", DIM),
], top=Inches(1.95), size=17)

# ═══════════ P16 华为云结合 ═══════════
s = new_slide(prs)
header(s, "华为云三件套：CodeArts 流水线 + FunctionGraph + OBS，全部可选可降级", "技术架构 · 华为云服务结合", accent=CQ)
bullets(s, [
    (f"CodeArts Repo 托管工程；CI 已脚本化（ruff → pytest {T_STR} → 前端冒烟 {S_STR} 步），可直接接入流水线", TEXT),
    ("FunctionGraph：天气查询走函数计算，未配置时 2 秒超时静默回落本地快照", TEXT),
    ("OBS：行程快照对象存储，提交后生成可分享链接", TEXT),
    ("不配置任何华为云变量也不影响演示——「可选增强」而非「硬依赖」", TEXT),
], top=Inches(1.95), size=18)
txbox(s, Inches(0.85), Inches(5.7), Inches(11.6), Inches(1.0), [
    ("为什么工具层用 Function Calling 而不是 MCP：同进程调用、零延迟、零网络、断网可用；", 16, TEXT, False, 4),
    ("将来接第三方 MCP Server 只需在工具层加一个适配分支，管线不动。", 16, TEXT, False, 0)])

# ═══════════ P17 落地规划 ═══════════
s = new_slide(prs)
header(s, "落地规划：从赛题快照到课程实训模板", "落地规划")
bullets(s, [
    ("近端：版本冻结 + 稳定交付 + 云上部署（在线演示地址）", TEXT),
    ("中期：数据层对接 OTA 开放接口——替换 server/data/ 分城快照即可，新增城市零代码改动", TEXT),
    ("远端：作为高校 AI Agent 课程实训模板推广（换城市 / 换学科场景复现）", TEXT),
    ("商业：西南文旅定制版（旅行社 / 文旅局）", TEXT),
], top=Inches(2.0))
txbox(s, Inches(0.85), Inches(5.6), Inches(11.6), Inches(0.8), [
    ("下一版方向（如实）：出发城市交通计算（origin 已抽取展示、暂未计入时间与费用）、数据维度扩展（口味等偏好）。", 15, DIM, False, 0)])

# ═══════════ P18 团队与结束 ═══════════
s = new_slide(prs)
header(s, "团队与分工", "参赛信息（占位由参赛者填写）")
rect(s, Inches(0.85), Inches(1.9), Inches(11.6), Inches(2.6), fill=PANEL)
txbox(s, Inches(1.15), Inches(2.15), Inches(11.0), Inches(2.2), [
    ("组别：高校组（可设指导教师 1 名，本队不设） ｜ 队名：__________", 18, TEXT, False, 10),
    ("分工：架构与后端 __________ ／ 前端与可视化 __________ ／ 数据与测试 __________", 18, TEXT, False, 10),
    ("（人工负责：任务单撰写与评审、方向决策、真实运行验证与截图录屏；码道负责：实现）", 15, DIM, False, 0),
])
rect(s, Inches(0.85), Inches(4.9), Inches(0.09), Inches(1.3), fill=CD)
txbox(s, Inches(1.15), Inches(4.85), Inches(11.2), Inches(1.5), [
    ("「行程规划的价值不在于生成得漂亮，", 24, TEXT, True, 4),
    ("而在于每一步都解释得清、扛得住规则校验。」", 24, CD, True, 0)])
txbox(s, Inches(1.15), Inches(6.5), Inches(11.0), Inches(0.6), [
    ("联系方式：__________ ｜ 仓库 / 演示地址二维码位：预留", 15, DIM, False, 0)])

for i in range(1, 19):
    footer(prs.slides[i - 1], i)

out = "ppt/蜀道智行.pptx"
prs.save(out)
print(f"已生成 {out}：{len(prs.slides.__iter__.__self__._sldIdLst)} 页")
print(f"实测口径（重出时点现读）：pytest {T_STR} / 冒烟 {S_STR} 步 / 任务单 {P_STR} 份"
      + ("（有「—」表示该项实测失败，跑 scripts/ctl.py ci 核对，绝不印编造数）" if "—" in (T_STR + S_STR + P_STR) else ""))
