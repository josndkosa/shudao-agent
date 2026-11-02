"""显式偏好画像（长期记忆的最低成本版本，03J）。

设计决定（为什么是"显式指令式"而不是黑盒画像）：
- 记忆是"我们替你记住了什么"，用户必须知道、能改、能删——只通过明确的
  「记住：xxx」指令触发，不做「用户说了带娃就偷偷推断偏好亲子」的画像推断。
- 零 UI：不加开关/面板/设置页（加了就要重拍截图重做 PPT），全部走对话栏。
- 隐私：画像存在用户主目录 ~/.shudao/preferences.json——不进仓库、不进提交包
  （server/data/ 会被 package.py 打进 zip 分发给评委，用户个性化数据绝不能放那）。
  SD_PREFERENCES_PATH 可覆盖路径（测试用）。

诚实边界（能记什么记不了什么，必须如实告诉用户）：
- 能记：亲子模式(family→V5 生效) / 预算(填本次未显式说的空缺) / 喜欢的标签(合并加权)
  / 排斥的标签(avoid_tags→候选筛选阶段硬排除)
- 记不了（数据层没有这个维度）：口味偏好（不吃辣/不吃牛羊肉）、具体景点名、
  酒店/航班偏好——遇到就如实提示「当前快照的数据维度还不支持」，绝不假装记住。

容错原则（断网保命同款）：文件不存在/损坏/目录不可写 → 一律静默降级为
"无记忆"，读不抛异常、写返回 False，绝不影响主流程。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

PREF_KEYS = ("family", "budget", "tags", "avoid_tags")


def _pref_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("SD_PREFERENCES_PATH")
    if env:
        return Path(env)
    return Path.home() / ".shudao" / "preferences.json"


def read_profile(path=None) -> dict | None:
    """读原始画像文件（含 updated_at 元信息）；不存在/损坏 → None。内部用。"""
    try:
        p = _pref_path(path)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_prefs(path=None) -> dict:
    """读偏好画像；文件不存在/损坏/读不了 → 返回空画像，绝不抛异常。

    只接受已知键且逐键类型校验（防手工编辑/损坏文件注入花活进管线）。
    """
    data = read_profile(path)
    if not data:
        return {}
    prefs = data.get("prefs")
    if not isinstance(prefs, dict):
        return {}
    out: dict = {}
    if prefs.get("family") is True:
        out["family"] = True
    b = prefs.get("budget")
    if isinstance(b, (int, float)) and not isinstance(b, bool) and b >= 500:
        out["budget"] = int(b)
    if isinstance(prefs.get("tags"), list):
        out["tags"] = [str(t) for t in prefs["tags"] if t][:8]
    if isinstance(prefs.get("avoid_tags"), list):
        out["avoid_tags"] = [str(t) for t in prefs["avoid_tags"] if t][:8]
    return out


def save_prefs(prefs: dict, path=None) -> bool:
    """写偏好画像；写失败 → 返回 False，不影响主流程。

    原子写：先写 .tmp 再 os.replace——写一半断电不会留下半个 JSON
    （损坏文件在 load 侧也只会降级为空画像，双保险）。
    """
    try:
        p = _pref_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1,
                   "updated_at": datetime.now().isoformat(timespec="seconds"),
                   "prefs": {k: prefs[k] for k in PREF_KEYS if k in prefs}}
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def clear_prefs(path=None) -> bool:
    """清空偏好画像（删文件）。失败 → False，不抛异常。"""
    try:
        p = _pref_path(path)
        if p.exists():
            p.unlink()
        return True
    except Exception:
        return False


def merge_prefs(base: dict, prefs: dict) -> tuple[dict, list[str]]:
    """把记忆合并进本次请求参数；返回 (合并后参数, 应用了哪些记忆的说明列表)。

    优先级铁律：**显式指定的值优先于记忆**——用户这次明确说了预算 5000，就用 5000。
    各键的「未显式」判定：
    - budget: None 视为未说（自然语言路径抽取不到时记忆填空缺；表单路径恒有值
      = 表单上可见即显式，记忆不覆盖——白盒原则：用户看见什么就用什么）
    - family: False 视为未提（勾选框语义是 neutral；记忆 true 生效）
    - tags / avoid_tags: 空列表可合并（记忆值去重追加）
    """
    out = dict(base)
    applied: list[str] = []
    if prefs.get("family") and not out.get("family"):
        out["family"] = True
        applied.append("亲子模式")
    if prefs.get("budget") and out.get("budget") is None:
        out["budget"] = int(prefs["budget"])
        applied.append(f"预算 {int(prefs['budget'])}")
    if prefs.get("tags"):
        cur = list(out.get("tags") or [])
        add = [t for t in prefs["tags"] if t not in cur]
        if add:
            out["tags"] = cur + add
            applied.append("偏好 " + "、".join(add))
    if prefs.get("avoid_tags"):
        cur = list(out.get("avoid_tags") or [])
        add = [t for t in prefs["avoid_tags"] if t not in cur]
        if add:
            out["avoid_tags"] = cur + add
            applied.append("避开 " + "、".join(add))
    return out, applied


def describe_prefs(prefs: dict) -> str:
    """画像的可读描述（事件 reason / 对话栏 note 共用一套口径）。"""
    parts = []
    if prefs.get("family"):
        parts.append("亲子模式")
    if prefs.get("budget"):
        parts.append(f"预算 {prefs['budget']}")
    if prefs.get("tags"):
        parts.append("喜欢 " + "、".join(prefs["tags"]))
    if prefs.get("avoid_tags"):
        parts.append("避开 " + "、".join(prefs["avoid_tags"]))
    return "、".join(parts)
