import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "pois.json"

TAG_ALIASES = {
    "文化": ["历史文化", "博物馆", "红色历史", "宗教", "古镇"],
    "历史": ["历史文化", "红色历史", "古镇"],
    "美食": ["美食"],
    "吃货": ["美食"],
    "亲子": ["亲子", "动物"],
    "遛娃": ["亲子", "动物"],
    "自然": ["自然", "动物", "园林"],
    "购物": ["购物"],
    "夜景": ["夜景"],
    "夜生活": ["夜生活", "夜景"],
    "文创": ["文创", "音乐"],
    "艺术": ["艺术", "文创"],
    "网红": ["奇观", "夜景", "文创"],
    "打卡": ["奇观", "夜景", "文创", "建筑"],
    "徒步": ["徒步"],
    "博物馆": ["博物馆"],
    "茶": ["茶文化"],
}


@lru_cache(maxsize=1)
def load_pois():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)["pois"]


def expand_tags(user_tags):
    """用户口语化偏好映射到受控标签词表。"""
    out = set()
    for t in user_tags or []:
        t = t.strip()
        if not t:
            continue
        out.update(TAG_ALIASES.get(t, [t]))
    return sorted(out)


def poi_search(city=None, tags=None, family=False, must_first=False, limit=None):
    """检索并按决策相关性打分。

    评分构成：标签命中 x3 + must_see x5 + 亲子加成 - 预约/拥挤惩罚。
    打分可解释，事件流会带 reason 供前端倒带回放。
    """
    pois = load_pois()
    want = expand_tags(tags)
    scored = []
    for p in pois:
        if city and p["city"] != city:
            continue
        reasons, score = [], 0.0
        hits = [t for t in want if t in p["tags"]] if want else []
        if hits:
            score += 3.0 * len(hits)
            reasons.append(f"标签命中{hits}")
        if p["must_see"]:
            score += 5.0
            reasons.append("必游地标")
        if family:
            if p["family"] < 2:
                continue
            score += p["family"] * 0.6
            reasons.append(f"亲子友好度{p['family']}")
        score -= p["reserve"] * 0.8
        score -= p["crowd_level"] * 0.4
        if p["reserve"] >= 2:
            reasons.append(f"预约难度{p['reserve']}")
        if must_first and not p["must_see"]:
            score -= 2.0
        scored.append({**p, "_score": round(score, 2), "_reasons": reasons or ["基础候选"]})
    scored.sort(key=lambda x: -x["_score"])
    if limit:
        scored = scored[:limit]
    return {"count": len(scored), "pois": scored}
