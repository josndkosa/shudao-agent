"""POI 检索与打分工具。

数据层 v2：分城快照（chengdu.json / chongqing.json）+ meta.json（词表/枢纽/城际）。
load_pois() 遍历 data 目录下的城市快照合并——新增城市只需新增数据文件，不用改代码。
字段规范见 server/data/schema.md。
"""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def _load_meta():
    with open(DATA_DIR / "meta.json", encoding="utf-8") as f:
        return json.load(f)


TAG_ALIASES = None      # 延迟初始化：从 meta.json 读取（见 _ensure_aliases）


def _ensure_aliases():
    global TAG_ALIASES
    if TAG_ALIASES is None:
        TAG_ALIASES = _load_meta()["tag_aliases"]
    return TAG_ALIASES


@lru_cache(maxsize=1)
def load_pois():
    """遍历 data/*.json（城市快照）合并返回全量 POI 列表。

    排除项：meta.json（总表）/ pois.json（v1 遗留名）/ provenance.json（03K 溯源旁挂，
    是 dict 不是 POI 列表——不排除会把它的键当 POI 迭代，直接 TypeError）。
    对外接口与 v1（单文件 pois.json）完全一致：返回 list[dict]。
    """
    pois = []
    for fn in sorted(DATA_DIR.glob("*.json")):
        if fn.name in ("meta.json", "pois.json", "provenance.json"):
            continue
        with open(fn, encoding="utf-8") as f:
            pois.extend(json.load(f))
    return pois


@lru_cache(maxsize=1)
def load_cities():
    """西南赛区城市总表（meta.json city_info）：terrain 分档 / 天气快照 / 省份 / 图幅注记行。"""
    return _load_meta()["city_info"]


@lru_cache(maxsize=1)
def _city_file_map():
    """城市 → 数据文件名：扫数据文件的 city 字段自动建索引。

    新增城市零代码改动（docs/开发指南.md 的承诺在这里兑现）：
    丢一个含 "city" 字段的城市 json 进 data/ 即被 load_pois/load_city_pois 同时收录。
    """
    m = {}
    for fn in sorted(DATA_DIR.glob("*.json")):
        if fn.name in ("meta.json", "pois.json", "provenance.json"):
            continue
        try:
            with open(fn, encoding="utf-8") as f:
                pois = json.load(f)
        except Exception:
            continue
        for p in pois:
            if p.get("city"):
                m.setdefault(p["city"], fn.name)
                break
    return m


@lru_cache(maxsize=16)
def load_city_pois(city):
    """单城快照读取（分城文件的直接用途；未收录城市返回空）。"""
    fn = _city_file_map().get(city)
    if fn is None:
        return []
    with open(DATA_DIR / fn, encoding="utf-8") as f:
        return json.load(f)


def expand_tags(user_tags):
    """用户口语化偏好映射到受控标签词表。"""
    aliases = _ensure_aliases()
    out = set()
    for t in user_tags or []:
        t = t.strip()
        if not t:
            continue
        out.update(aliases.get(t, [t]))
    return sorted(out)


def poi_search(city=None, tags=None, family=False, must_first=False, limit=None):
    """检索并按决策相关性打分。

    评分构成：标签命中 x3 + must_see x5 + 亲子加成 - 预约/拥挤惩罚。
    打分可解释，事件流会带 reason 供前端倒带回放。
    """
    _ensure_aliases()
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
