"""自然语言 → 结构化规划参数（03G：抽取与规划分离）。

架构原则——为什么单独一层、且与三段式管线零耦合：
1. 抽取是纯理解任务，LLM 强项；规划是约束求解，规则引擎强项——混在一个提示里两边都做不好。
2. 抽取结果回填参数条让用户看见、可改——AI 的理解必须是白盒，看不见的理解无法纠错，黑盒最不可信。
3. 同一接口两种实现（在线 LLM / 离线正则+词表），断网保命设计不破——抽取器离线可用。
4. 与 revise.py 的「意图解析与执行分离」、数据层的 Provider 抽象是同一思路。

抽取器只产出参数，绝不决定点位、不推断天气/票价/开放时间——事实来自数据层，不来自模型。
"""
from __future__ import annotations

import json
import re

from ..tools.poi_search import _ensure_aliases, _load_meta, expand_tags
from . import llm as llm_mod
from .events import EventBus
from .pipeline import _load_dotenv

DAYS_MIN, DAYS_MAX = 1, 30
BUDGET_MIN = 500

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10}
FAMILY_WORDS = ("亲子", "带娃", "孩子", "小孩", "老人")
ORIGIN_PATTERNS = (
    re.compile(r"我在([^，,。;；、\s]{2,8})"),
    re.compile(r"从([^，,。;；、\s]{2,8})出发"),
    re.compile(r"出发地[是:：为]?([^，,。;；、\s]{2,8})"),
    re.compile(r"([^，,。;；、\s]{2,8})出发"),
)


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


def parse_request(text: str, bus: EventBus) -> dict:
    """自然语言 → 结构化规划参数。

    返回 {origin, cities, days, budget, tags, family, source, note}：
    source: "llm"（在线抽取） | "rules"（离线抽取） | "fallback"（完全没解析出来）
    note: 如实提示（被过滤的城市 / 出发地未参与计算）；两种实现返回完全同构。
    """
    text = (text or "").strip()
    _load_dotenv()   # 与 run_pipeline 同款幂等加载：CLI/直调场景读不到 .env 里的 key
    bus.emit("system", "thought", "解析自然语言需求", reason=text[:80])
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
    out["source"] = source
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

    m = re.search(r"([0-9一二三四五六七八九十]{1,3})\s*天", text)
    if m:
        raw["days"] = _cn2int(m.group(1))

    m = (re.search(r"([0-9]{2,6})\s*(?:元|块|rmb|￥|¥)", text, re.I)
         or re.search(r"预算\s*[:：]?\s*([0-9]{2,6})", text))
    if m:
        raw["budget"] = int(m.group(1))

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
