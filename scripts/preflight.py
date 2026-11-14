"""preflight.py — 提交预检板（03M 任务B）：`python scripts/ctl.py preflight`。

回答的问题不是「exit 0/1」，而是「我现在还差什么、下一步该干嘛」——
最后六天每天早上跑一次，按表逐项补齐，全绿即可打包提交。

七项检查（每行 ✅/❌/⚠️ + 一句人话）：
  1. 视频        video/ 有 mp4 且时长 ≤ 190 秒（赛题 ≤3 分钟）
  2. 六张图      docs/images/ 规格表列出的文件都存在且 ≥ 100KB
  3. PPT 常量    gen_ppt.py 的 SUBMIT_DATE / DEMO_URL 已填（不含下划线）
  4. 地址可达    3 秒内 /api/health 200 且含 mode（--offline 跳过）
  5. 占位残留    复用 check_placeholders（不重写第二份实现）
  6. 任务单份数  已归档 ≥ package.py need_prompts 项数
  7. 版本号一致  CHANGELOG 顶条 / gen_ppt.VERSION / 提交清单 --version 三处相同

mp4 时长用纯标准库解析（不引 ffprobe）；读不出时长如实给 ⚠️，不冒充通过。
六个图片文件名从 docs/images/README.md 的表格解析——不硬编码第二份清单。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_placeholders  # noqa: E402  第 5 项复用同一份实现

MARK = {"ok": "✅", "bad": "❌", "warn": "⚠️ ", "skip": "⏭️ "}


# ── 公共解析函数（package.py 任务E 复用，同一份实现不写两遍）──────────────

def mp4_duration(path: Path) -> float | None:
    """纯标准库解析 mp4 时长：读文件前 2MB 找 mvhd box。

    box 布局：… size(4) "mvhd" version(1)+flags(3)，随后——
      version 0：creation(4) modification(4) timescale(4) duration(4)
      version 1：creation(8) modification(8) timescale(4) duration(8)
    时长 = duration / timescale。解析失败返回 None（如实说读不出，不假装通过）。
    """
    try:
        with path.open("rb") as f:
            head = f.read(2 * 1024 * 1024)
        i = head.find(b"mvhd")
        if i < 0:
            return None
        p = i + 4                                  # version(1) + flags(3)
        version = head[p]
        p += 4
        if version == 1:
            p += 16                                 # creation(8) + modification(8)
            timescale = int.from_bytes(head[p:p + 4], "big")
            duration = int.from_bytes(head[p + 4:p + 12], "big")
        else:
            p += 8                                  # creation(4) + modification(4)
            timescale = int.from_bytes(head[p:p + 4], "big")
            duration = int.from_bytes(head[p + 4:p + 8], "big")
        if not timescale:
            return None
        return duration / timescale
    except (OSError, ValueError, IndexError):
        return None


def image_spec_list(root: Path = ROOT) -> list[str]:
    """六个图片文件名从 docs/images/README.md 的规格表解析（第一列 `xxx.png`）。

    不硬编码第二份清单——README 加图改表即可，预检板与 package.py 自动跟上。
    """
    md = (root / "docs" / "images" / "README.md").read_text(encoding="utf-8")
    return re.findall(r"^\|\s*`([^`\s]+\.png)`", md, re.M)


def changelog_top_version(root: Path = ROOT) -> str | None:
    m = re.search(r"^## \[([0-9][0-9A-Za-z.\-]*)\]", (root / "CHANGELOG.md").read_text("utf-8"), re.M)
    return m.group(1) if m else None


def ppt_constants(root: Path = ROOT) -> dict:
    """gen_ppt.py 顶部常量（SUBMIT_DATE / DEMO_URL / VERSION）——源码级读取，
    不 import（import 会顺带跑 _ci_counts 子进程，预检板要快）。"""
    src = (root / "scripts" / "gen_ppt.py").read_text("utf-8")
    out = {}
    for name in ("SUBMIT_DATE", "DEMO_URL", "VERSION"):
        m = re.search(rf'^{name}\s*=\s*"([^"]*)"', src, re.M)
        out[name] = m.group(1) if m else None
    return out


def need_prompts_count(root: Path = ROOT) -> int | None:
    """package.py 的 need_prompts 清单项数（源码解析，不 import——main() 会打包）。"""
    src = (root / "scripts" / "package.py").read_text("utf-8")
    m = re.search(r"need_prompts\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        return None
    return len(re.findall(r'"[^"]+"', m.group(1)))


def checklist_pack_version(root: Path = ROOT) -> str | None:
    """提交清单.md 里打包命令的 --version 值。"""
    src = (root / "提交清单.md").read_text("utf-8")
    m = re.search(r"--version\s+([0-9][0-9A-Za-z.\-]*)", src)
    return m.group(1) if m else None


# ── 七项检查 ──────────────────────────────────────────────────

def check_video(root: Path) -> tuple[str, str]:
    mp4s = sorted((root / "video").glob("*.mp4")) if (root / "video").is_dir() else []
    if not mp4s:
        return "bad", "video/ 无 mp4 —— 先录；起手用 /plan.html?shot=overview"
    durs = []
    for m in mp4s:
        d = mp4_duration(m)
        if d is None:
            return "warn", f"{m.name} 读不出时长（非标准 mvhd？人工核 ≤ 3 分钟）"
        if d > 190:
            return "bad", f"{m.name} 实际 {d:.0f} 秒，超 3 分钟（赛题硬限）——重剪或重录"
        durs.append(f"{m.name} {d:.0f}s")
    return "ok", "、".join(durs)


def check_images(root: Path) -> tuple[str, str]:
    names = image_spec_list(root)
    missing = [n for n in names
               if not (root / "docs" / "images" / n).is_file()
               or (root / "docs" / "images" / n).stat().st_size < 100 * 1024]
    if missing:
        shot_map = {"overview.png": "overview", "map.png": "map", "player.png": "player",
                    "replay.png": "replay", "chat.png": "chat", "home.png": None}
        hint = "；".join(f"{n} 用 /plan.html?shot={shot_map[n]} 打开直接截" for n in missing if shot_map.get(n))
        extra = "；home.png 打开 http://localhost:8000/ 直截" if "home.png" in missing else ""
        return "bad", f"缺 {'、'.join(missing)} —— {hint}{extra}"
    return "ok", f"{len(names)} 张规格图齐全（≥100KB）"


def check_ppt_consts(root: Path) -> tuple[str, str]:
    c = ppt_constants(root)
    unfilled = [k for k in ("SUBMIT_DATE", "DEMO_URL") if c.get(k) and "_" in c[k]]
    if unfilled:
        return "bad", f"{unfilled[0]} 还空着 —— 地址/日期拿到后填进 gen_ppt.py 再重出 PPT"
    if not all(c.get(k) for k in ("SUBMIT_DATE", "DEMO_URL")):
        return "bad", "gen_ppt.py 常量读取失败——人工核对 SUBMIT_DATE / DEMO_URL"
    return "ok", f"SUBMIT_DATE={c['SUBMIT_DATE']} / DEMO_URL={c['DEMO_URL']}"


def check_deploy_url(root: Path, offline: bool) -> tuple[str, str]:
    if offline:
        return "skip", "--offline：跳过地址可达检查"
    url = ppt_constants(root).get("DEMO_URL")
    if not url or "_" in url:
        return "bad", "DEMO_URL 未填 —— 公网地址拿到后填进 gen_ppt.py（ECS 部署见 readme 第 2 节）"
    origin = re.match(r"(https?://[^/]+)", url)
    if not origin:
        return "bad", f"DEMO_URL 不是 http(s) 地址：{url[:40]}"
    try:
        with urllib.request.urlopen(origin.group(1) + "/api/health", timeout=3) as r:
            body = r.read(200).decode("utf-8", "replace")
        mode = json.loads(body).get("mode", "?")
        return "ok", f"/api/health 200（mode={mode}）"
    except Exception as e:
        return "bad", f"公网地址打不开（{type(e).__name__}）—— 先确认安全组放行 8000"


def check_placeholders_run(root: Path) -> tuple[str, str]:
    hits = check_placeholders.scan_text(root) + check_placeholders.scan_pptx(root)
    if hits:
        return "bad", f"还有 {len(hits)} 处未填占位：{'；'.join(hits[:3])}…"
    return "ok", "目标范围内无未填占位"


def check_prompts(root: Path) -> tuple[str, str]:
    need = need_prompts_count(root)
    archived = len(list((root / "codearts_proof" / "prompts" / "_已执行").glob("*.md")))
    if need is None:
        return "warn", "package.py 的 need_prompts 解析失败——人工核对归档"
    if archived < need:
        return "bad", f"归档 {archived} 份 < 清单 {need} 项 —— 少归档了任务单（对照 _已执行/ 补）"
    return "ok", f"归档 {archived} 份 ≥ 清单 {need} 项"


def check_versions(root: Path) -> tuple[str, str]:
    cl = changelog_top_version(root)
    gp = ppt_constants(root).get("VERSION")
    ck = checklist_pack_version(root)
    if not (cl and gp and ck):
        return "bad", f"版本号读取不全：CHANGELOG={cl} / gen_ppt.VERSION={gp} / 提交清单={ck}"
    vs = {"CHANGELOG": cl, "gen_ppt": gp, "提交清单": ck}
    uniq = set(vs.values())
    if len(uniq) > 1:
        detail = " / ".join(f"{k} {v}" for k, v in vs.items())
        return "bad", f"三处版本号不一致：{detail} —— 以 CHANGELOG 顶条为准，改提交清单后重出 PPT"
    return "ok", f"三处一致（v{cl}）"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="提交预检板：现在能不能交、还差什么")
    ap.add_argument("--offline", action="store_true", help="跳过「演示地址可达」一项（无网络时用）")
    args = ap.parse_args()

    rows = [
        ("视频", check_video(ROOT)),
        ("六张图", check_images(ROOT)),
        ("PPT 常量", check_ppt_consts(ROOT)),
        ("地址可达", check_deploy_url(ROOT, args.offline)),
        ("占位残留", check_placeholders_run(ROOT)),
        ("任务单份数", check_prompts(ROOT)),
        ("版本号一致", check_versions(ROOT)),
    ]
    print("========== 提交预检板（每天早上跑一次，全绿即可打包）==========")
    n_bad = n_warn = 0
    for name, (st, text) in rows:
        if st == "bad":
            n_bad += 1
        if st == "warn":
            n_warn += 1
        print(f"{MARK[st]} {name:<6s} {text}")
    print("--------------------------------------------------------------")
    if n_bad:
        print(f"结论：还有 {n_bad} 项硬缺口" + (f" + {n_warn} 项待人工核" if n_warn else ""))
        return 1
    if n_warn:
        print(f"结论：无硬缺口，{n_warn} 项待人工确认")
        return 0
    print("结论：全部就绪 —— python scripts/package.py 正式打包（不带 --allow-missing-media）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
