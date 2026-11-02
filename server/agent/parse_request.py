"""自然语言 → 结构化规划参数（03G：抽取与规划分离）。

架构原则——为什么单独一层、且与三段式管线零耦合：
1. 抽取是纯理解任务，LLM 强项；规划是约束求解，规则引擎强项——混在一个提示里两边都做不好。
2. 抽取结果回填参数条让用户看见、可改——AI 的理解必须是白盒，看不见的理解无法纠错，黑盒最不可信。
3. 同一接口两种实现（在线 LLM / 离线正则+词表），断网保命设计不破——抽取器离线可用。
4. 与 revise.py 的「意图解析与执行分离」、数据层的 Provider 抽象是同一思路。

抽取器只产出参数，绝不决定点位、不推断天气/票价/开放时间——事实来自数据层，不来自模型。

03J 扩展——显式偏好记忆（对话栏同一入口，零 UI 改动）：
- 「记住：我带娃，不去博物馆」→ 写偏好画像（用户主目录，不进仓库不进提交包）
- 「忘掉我的偏好 / 忘掉博物馆」→ 清空或删指定项
- 「我记住了什么」→ 列出画像
- 记忆操作全部走规则（触发词+词表），不依赖 LLM——离线在线都能用
- 正常规划语句：抽取后合并记忆（显式优先，未说的字段由记忆填空缺并回填可见）
"""
from __future__ import annotations

import json
import re

from ..tools.poi_search import _ensure_aliases, _load_meta, expand_tags
from . import llm as llm_mod
from .events import EventBus
from .pipeline import _load_dotenv
from .preferences import clear_prefs, describe_prefs, load_prefs, merge_prefs, save_prefs

DAYS_MIN, DAYS_MAX = 1, 30
BUDGET_MIN = 500

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10}
CN_DIGIT = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9}
FAMILY_WORDS = ("亲子", "带娃", "孩子", "小孩", "老人")
ORIGIN_PATTERNS = (
    re.compile(r"我在([^，,。;；、\s]{2,8})"),
    re.compile(r"从([^，,。;；、\s]{2,8})出发"),
    re.compile(r"出发地[是:：为]?([^，,。;；、\s]{2,8})"),
    re.compile(r"([^，,。;；、\s]{2,8})出发"),
)
# 03J 记忆意图触发词（显式指令式——不做「用户说了带娃就偷偷记」的黑盒画像）
VIEW_WORDS = ("我记住了什么", "记住了什么", "看看我的偏好", "查看我的偏好",
              "我的偏好是什么", "偏好设置")
FORGET_WORDS = ("忘掉", "别记了", "忘记我的偏好", "忘了我的偏好",
                "清空我的偏好", "清空偏好")
REMEMBER_WORDS = ("记住", "别忘了", "记一下", "帮我记住", "以后都")
# 标签前的回避语境（出现即归入 avoid_tags 而非 tags）：「不去博物馆」
AVOID_CONTEXT = ("不去", "避开", "别去", "不想去", "不喜欢", "不看", "排斥", "讨厌")
TASTE_CONTEXT = ("不吃", "不喝", "爱吃", "口味")   # 口口味偏好：数据层无此维度，如实告知记不了


def _cn2int(s: str):
    """中文数字 → 整数（一~三十一 足够覆盖天数口语）。"""
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    m = re.fullmatch(r"([一二三四五六七八九]?)十([一二三四五六七八九]?)", s)
    if m:
        return (CN_NUM.get(m.group(1), 1) if m.group(1) else 1) * 10 + CN_NUM.get(m.group(2), 0)
    return CN_NUM.get(s)


def _controlled_tags():
    """受控标签词表全集 = tag_aliases 所有映射目标的并集（expand_tags 只做别名映射、
    未知词原样透传，所以归一后还要过滤一道，不让任何自造标签进打分管线）。"""
    return set().union(*_ensure_aliases().values())


# ── 03J 偏好记忆：抽取与意图处理（纯规则，离线在线都能用） ──────────────────

def _scan_pref_content(text: str):
    """从「记住：xxx」语句抽偏好内容：{family, budget, tags, avoid_tags}。

    标签按上下文分流：词表词前面 4 字窗口内含回避语境（不去/避开…）→ avoid_tags，
    否则 → tags——「记住：喜欢夜景，不去博物馆」两头都对。
    """
    out: dict = {}
    if any(w in text for w in FAMILY_WORDS):
        out["family"] = True
    b = _budget_scan(text)
    if b:
        out["budget"] = b
    like, avoid = [], []
    for t in _ensure_aliases():
        i = text.find(t)
        while i >= 0:
            ctx = text[max(0, i - 4):i]
            (avoid if any(w in ctx for w in AVOID_CONTEXT) else like).append((i, t))
            i = text.find(t, i + 1)
    out["tags"] = [t for _, t in sorted(set(like))]
    out["avoid_tags"] = [t for _, t in sorted(set(avoid))]
    return out


def _taste_unsupported(text: str, scanned: dict) -> str | None:
    """口味类偏好的如实提示：句中有口味语境（不吃/不喝…）但快照没有该维度。"""
    if any(w in text for w in TASTE_CONTEXT):
        return "口味偏好这块，当前快照的数据维度还不支持，先记不下来"
    if any(w in text for w in AVOID_CONTEXT) and not scanned.get("avoid_tags"):
        # 回避语境命中但目标不在受控词表（如具体景点名）→ 同样如实提示
        return "其余偏好记不了（能记：亲子/预算/喜欢或排斥的标签；具体景点、口味等维度暂不支持）"
    return None


def _merge_profile(cur: dict, new: dict) -> dict:
    """画像增量合并：记住夜景后再记住徒步 → 两者都在；预算新值覆盖旧值。"""
    out = dict(cur)
    if new.get("family"):
        out["family"] = True
    if new.get("budget"):
        out["budget"] = new["budget"]
    for k in ("tags", "avoid_tags"):
        if new.get(k):
            cur_l = list(out.get(k) or [])
            out[k] = cur_l + [t for t in new[k] if t not in cur_l]
    return {k: v for k, v in out.items() if v}


def _intent_out(intent: str, prefs: dict, note: str) -> dict:
    """记忆操作分支的统一返回结构（与正常抽取分支同构，前端零分叉）。"""
    return {"origin": None, "cities": [], "days": None, "budget": None, "tags": [],
            "family": False, "source": "rules", "note": note,
            "remember": intent == "remember", "forget": intent == "forget",
            "view": intent == "view", "prefs": prefs}


def _handle_remember(text: str, bus: EventBus) -> dict:
    """「记住：我带娃，不去博物馆」→ 增量写入画像 + 发「已记住」事件。

    没抽到任何可记内容（如「记住：我不吃辣」）→ 如实提示，绝不写空画像、
    绝不说"记住了"然后默默丢掉——那是欺骗。
    """
    new = _scan_pref_content(text)
    new = {k: v for k, v in new.items() if v}
    taste = _taste_unsupported(text, new)
    if not new:
        reason = taste or "这句话里没有能记住的偏好（能记：亲子/预算/喜欢或排斥的标签）"
        bus.emit("system", "fallback", "这条偏好记不了",
                 reason=reason + "；画像未做任何修改")
        return _intent_out("remember", load_prefs(), reason)

    merged = _merge_profile(load_prefs(), new)
    ok = save_prefs(merged)
    if not ok:
        note = "偏好保存失败（存储目录不可写），本次未记住；规划不受影响"
        bus.emit("system", "fallback", "偏好保存失败", reason="目录不可写，已如实告知用户")
        return _intent_out("remember", load_prefs(), note)
    note = "已记住：" + describe_prefs(new)
    if taste:
        note += "。" + taste
    bus.emit("system", "decision", "已记住偏好",
             reason=describe_prefs(merged) + "（画像存于用户主目录 ~/.shudao/，"
                    "不随作品分发；说「忘掉我的偏好」即可删除）")
    return _intent_out("remember", merged, note)


def _handle_forget(text: str, bus: EventBus) -> dict:
    """「忘掉我的偏好」全清；「忘掉博物馆/带娃/预算」只删提及的项。"""
    prefs = load_prefs()
    if not prefs:
        note = "还没有记住任何偏好，无需忘掉"
        bus.emit("system", "fallback", "没有可忘掉的偏好", reason="画像为空")
        return _intent_out("forget", {}, note)

    mentioned_tags = [t for t in _ensure_aliases() if t in text]
    mentioned_family = any(w in text for w in FAMILY_WORDS)
    mentioned_budget = "预算" in text
    if not (mentioned_tags or mentioned_family or mentioned_budget):
        clear_prefs()
        bus.emit("system", "decision", "已忘掉全部偏好",
                 reason="画像已清空（删除 ~/.shudao/preferences.json）")
        return _intent_out("forget", {}, "已忘掉全部偏好")

    removed = []
    if mentioned_family and prefs.get("family"):
        prefs.pop("family")
        removed.append("亲子模式")
    if mentioned_budget and prefs.get("budget"):
        removed.append(f"预算 {prefs.pop('budget')}")
    for k in ("tags", "avoid_tags"):
        hit = [t for t in mentioned_tags if t in prefs.get(k, [])]
        if hit:
            prefs[k] = [t for t in prefs[k] if t not in hit]
            if not prefs[k]:
                prefs.pop(k)
            removed.append(("喜欢 " if k == "tags" else "避开 ") + "、".join(hit))
    prefs = {k: v for k, v in prefs.items() if v}
    save_prefs(prefs)
    note = "已忘掉：" + "、".join(removed) if removed else "没有匹配到要忘掉的偏好项"
    rest = f"；仍记住：{describe_prefs(prefs)}" if prefs else "；画像已空"
    bus.emit("system", "decision", "已忘掉指定偏好", reason=note + rest)
    return _intent_out("forget", prefs, note + rest)


def _handle_view(bus: EventBus) -> dict:
    """「我记住了什么」→ 列出当前画像（用户必须能看见我们替他记了什么）。"""
    prefs = load_prefs()
    if prefs:
        note = "当前记住的偏好：" + describe_prefs(prefs)
        bus.emit("system", "tool_result", "查看偏好画像", reason=note)
    else:
        note = "还没有记住任何偏好（说「记住：我带娃，不去博物馆」即可开始记录）"
        bus.emit("system", "tool_result", "查看偏好画像", reason="画像为空")
    return _intent_out("view", prefs, note)


def _cn_amount(s: str):
    """中文/阿拉伯金额 → 整数：支持「两千」「2千」「一万五」「五千」等口语。

    「一万五」= 一万五千（万位后的裸数字按低一级单位计，中文口语惯例）；
    「两千五」= 两千五百同理。
    """
    s = s.strip()
    if s.isdigit():
        return int(s)
    last_unit = 10000 if "万" in s else (1000 if "千" in s else 0)
    total = num = 0
    for ch in s:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
        elif ch == "万":
            total = (total + num or 1) * 10000
            num = 0
        elif ch == "千":
            total += (num or 1) * 1000
            num = 0
        elif ch == "百":
            total += (num or 1) * 100
            num = 0
        elif ch == "十":
            total += (num or 1) * 10
            num = 0
        elif ch == "零":
            continue
        else:
            return None
    if num and last_unit:               # 尾部裸数字：按低一级单位（一万五 → +5000）
        num = num * (last_unit // 10)
    return (total + num) if (total or num) else None


def _budget_scan(text: str):
    """预算金额扫描：带单位（元/块/￥…）或「预算」锚点，金额支持中文数字。"""
    m = (re.search(r"([0-9一二三四五六七八九两百千万]+)\s*(?:元|块|rmb|￥|¥)", text, re.I)
         or re.search(r"预算\s*[:：]?\s*([0-9一二三四五六七八九两百千万]+)", text))
    if not m:
        return None
    v = _cn_amount(m.group(1))
    return v if v and v >= BUDGET_MIN else None


def parse_request(text: str, bus: EventBus) -> dict:
    """自然语言 → 结构化规划参数 / 偏好记忆操作。

    返回 {origin, cities, days, budget, tags, family, source, note,
          remember, forget, view, prefs}：
    source: "llm"（在线抽取） | "rules"（离线抽取） | "fallback"（完全没解析出来）
    note: 如实提示（被过滤的城市 / 出发地未参与计算 / 记忆应用说明）；两种实现返回完全同构。
    remember/forget/view（03J）：本句是「记住/忘掉/查看偏好」指令（互斥）；prefs 为当前画像。
    """
    text = (text or "").strip()
    _load_dotenv()   # 与 run_pipeline 同款幂等加载：CLI/直调场景读不到 .env 里的 key
    bus.emit("system", "thought", "解析自然语言需求", reason=text[:80])

    # ── 03J 记忆意图（规则识别，不依赖 LLM；顺序：查看 > 忘掉 > 记住）──
    if any(w in text for w in VIEW_WORDS):
        return _handle_view(bus)
    if any(w in text for w in FORGET_WORDS):
        return _handle_forget(text, bus)
    if any(w in text for w in REMEMBER_WORDS):
        return _handle_remember(text, bus)

    raw, source = None, None
    if llm_mod.resolve_mode() == "online":
        try:
            raw, source = _parse_llm(text), "llm"
        except Exception as e:
            bus.emit("system", "fallback", "LLM 抽取降级为规则实现",
                     reason=f"{type(e).__name__}: {e}")
    if raw is None:
        raw = _parse_rules(text)
        source = "rules" if _hit_any(raw) else "fallback"
    out = _finalize(raw)
    # 03J 记忆合并（自然语言路径）：显式=抽取值优先，未说的字段由记忆填空缺并回填可见
    # ——行程生效的权威点在 run_pipeline（那里发「应用偏好记忆」事件），此处只为白盒可见
    prefs = load_prefs()
    if prefs:
        merged, applied = merge_prefs(out, prefs)
        out = merged
        if applied:
            out["note"] = (out["note"] + "；" if out["note"] else "") + \
                "已按上次的偏好：" + "、".join(applied)
    out["source"] = source
    out.update({"remember": False, "forget": False, "view": False, "prefs": prefs})
    bus.emit("system", "decision", "从你的话里读到了：" + _summary(out),
             reason=f"抽取实现 {source}；结果回填参数条，用户可见可改", detail={
                 "origin": out["origin"], "cities": out["cities"], "days": out["days"],
                 "budget": out["budget"], "tags": out["tags"], "family": out["family"]})
    return out


def _parse_llm(text: str) -> dict:
    """在线实现：一次纯 JSON 调用（无 tools，可开 json_mode——03F 预留的调用点）。"""
    meta = _load_meta()
    cities = list(meta["city_info"])
    tags = sorted(_ensure_aliases())
    system = (
        "你是行程规划参数抽取器，从用户的话里抽取参数，只输出一个 JSON 对象，"
        "不要 markdown 代码块、不要任何解释。结构为 "
        '{"origin": "出发城市或null", "cities": ["城市名"], "days": 整数或null,'
        ' "budget": 整数或null, "tags": ["词"], "family": true或false}。'
        f"cities 只能从这些城市里选：{'、'.join(cities)}；"
        f"tags 只能从这些词里选：{'、'.join(tags)}；"
        "用户没提到的字段填 null（cities/tags 给空数组、family 给 false）；禁止编造。"
    )
    msg, _ = llm_mod.chat([{"role": "system", "content": system},
                           {"role": "user", "content": text}],
                          temperature=0.1, json_mode=True)
    content = (msg.content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM 抽取输出中未找到 JSON")
        return json.loads(content[start:end + 1])


def _parse_rules(text: str) -> dict:
    """离线实现：正则 + meta 词表（别名表在 meta.city_aliases，不硬编码本层）。"""
    meta = _load_meta()
    raw = {}

    m = re.search(r"([0-9一二三四五六七八九两十]{1,3})\s*天", text)
    if m:
        raw["days"] = _cn2int(m.group(1))

    b = _budget_scan(text)   # 预算支持中文金额：「预算两千」=2000（03J 升级，记住/规划共用）
    if b:
        raw["budget"] = b

    raw["family"] = any(w in text for w in FAMILY_WORDS)

    hits = []
    for t in _ensure_aliases():
        if t in text:
            hits.append((text.find(t), t))
    raw["tags"] = [t for _, t in sorted(hits)]   # 按用户说到的先后序

    cities = []
    rest = text
    for c in meta["cities"]:                      # 全名优先（按 meta 顺序）
        if c in rest:
            cities.append(c)
            rest = rest.replace(c, "，")
    for c, aliases in meta.get("city_aliases", {}).items():
        if c in cities:
            continue
        if any(a in rest for a in aliases):       # 别名只补全名未命中的城
            cities.append(c)
    raw["cities"] = cities

    for pat in ORIGIN_PATTERNS:
        m = pat.search(text)
        if m:
            raw["origin"] = m.group(1)
            break
    return raw


def _hit_any(raw: dict) -> bool:
    return bool(raw.get("days") or raw.get("budget") or raw.get("cities")
                or raw.get("tags") or raw.get("origin") or raw.get("family"))


def _finalize(raw: dict) -> dict:
    """两种实现共用的校验与归一：城市只认 city_info、标签必须落受控词表、数值 clamp。

    抽取器在此拦住一切「模型自造语义」——城市不认识就过滤并如实提示，
    标签不在词表就丢弃——后面打分管线的输入永远是本地快照的受控值。
    """
    meta = _load_meta()
    valid = meta["city_info"]
    notes = []

    origin = raw.get("origin")
    origin = str(origin).strip()[:16] if origin else None
    if origin:
        notes.append(f"出发地 {origin} 仅作展示，暂未计入行程时间与交通费")

    cities, dropped = [], []
    seen = set()
    for c in raw.get("cities") or []:
        c = str(c).strip()
        if c in valid and c not in seen:
            cities.append(c)
            seen.add(c)
        elif c and c not in seen:
            dropped.append(c)
            seen.add(c)
    if dropped:
        notes.append(f"未收录城市已忽略：{'、'.join(dropped)}（当前覆盖西南 15 城，可说成都/重庆等）")

    days = raw.get("days")
    days = min(max(int(days), DAYS_MIN), DAYS_MAX) if isinstance(days, (int, float)) and days else None

    budget = raw.get("budget")
    budget = max(int(budget), BUDGET_MIN) if isinstance(budget, (int, float)) and budget else None

    controlled = _controlled_tags()
    tags = [t for t in expand_tags([t for t in (raw.get("tags") or []) if isinstance(t, str)])
            if t in controlled]

    return {
        "origin": origin, "cities": cities, "days": days, "budget": budget,
        "tags": tags, "family": bool(raw.get("family")),
        "source": None, "note": "；".join(notes),
    }


def _summary(out: dict) -> str:
    """「每条决策带 reason」的延伸：用户也得看得见 AI 的理解。"""
    parts = []
    if out["days"]:
        parts.append(f"{out['days']} 天")
    if out["budget"]:
        parts.append(f"预算 {out['budget']}")
    if out["cities"]:
        parts.append("、".join(out["cities"]))
    if out["tags"]:
        parts.append("、".join(out["tags"]))
    if out["family"]:
        parts.append("亲子模式")
    if out["origin"]:
        parts.append(f"出发地 {out['origin']}")
    return " / ".join(parts) or "未识别到任何参数"
