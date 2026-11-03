"""check_placeholders.py — 占位残留自检（03L 任务L5）。

背景：材料里再冒出一个「__________」，评委解压 zip 第一眼就是横杠。这一个月
已经吃过三次同类亏（三个数字版本并存 / 四层口径不一致 / mock 双跑）——
把它变成一道必红的闸，而不是靠人记得看。

扫什么（会进 zip、且评委直接看的）：
  - README.md、readme/**/*.md、docs/**/*.md、ppt/*.md
  - scripts/gen_ppt.py（PPT 的身份信息源，常量留占位 = PPT 印横杠）
  - ppt/蜀道智行.pptx —— 当 zip 解开，查 ppt/slides/*.xml 与 ppt/notesSlides/*.xml
    （直接对二进制 grep 找不到，文字在 XML 里）

不扫什么（横杠是历史描述，不是待填占位，不许改、不许报）：
  - 任何路径含 codearts_proof 的位置（顶层与 project/codearts_proof 都算——
    历史任务单原文写着「保留 ______ 占位由参赛者手填」，那是证据，删了等于篡改记录）
  - docs/baseline/（基线输出存档）、docs/赛题情报/（赛题原文）
  - .git/、__pycache__/、.pytest_cache/、.ruff_cache/、.venv/ 等

判定规则：连续 6 个及以上下划线（_{6,}）判为未填占位。
  __________（10 个）→ 命中；___（markdown 分隔线）、__init__ → 不命中。

用法：python scripts/check_placeholders.py [根目录]（默认仓库根）。
退出码：0 = 干净；1 = 有命中（打印 路径:行号；pptx 报 ppt/xxx.pptx#slideN）。
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path

PLACEHOLDER = re.compile(r"_{6,}")

# 会进 zip、评委直接看的文本范围
TEXT_TARGETS = ["README.md", "提交清单.md"]
TEXT_GLOBS = ["readme/**/*.md", "docs/**/*.md", "ppt/*.md", "scripts/gen_ppt.py"]
PPTX_GLOB = "ppt/*.pptx"

# 横杠是历史描述而非待填占位的位置（路径包含即排除，大小写不敏感、兼容正反斜杠）
EXCLUDE_PARTS = ("codearts_proof", ".git", "__pycache__", ".pytest_cache",
                 ".ruff_cache", ".venv", "node_modules", "_stage")
EXCLUDE_DIRS = ("baseline", "赛题情报")   # docs/ 下的存档目录


def _excluded(p: Path, root: Path) -> bool:
    parts = [x.lower() for x in p.relative_to(root).parts]
    if any(seg in parts for seg in EXCLUDE_PARTS):
        return True
    # docs/baseline、docs/赛题情报（按目录名排除，兼容任意父级下的同名存档目录）
    if any(seg in parts[:-1] for seg in EXCLUDE_DIRS):
        return True
    return False


def scan_text(root: Path) -> list[str]:
    hits = []
    files = [root / t for t in TEXT_TARGETS if (root / t).is_file()]
    for pat in TEXT_GLOBS:
        files += [p for p in root.glob(pat) if p.is_file()]
    seen = set()
    for f in sorted(files):
        if f in seen or _excluded(f, root):
            continue
        seen.add(f)
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if PLACEHOLDER.search(line):
                hits.append(f"{f.relative_to(root)}:{i}")
    return hits


def scan_pptx(root: Path) -> list[str]:
    """pptx 是 zip：解包查 ppt/slides/*.xml 与 ppt/notesSlides/*.xml 里的文字。"""
    hits = []
    for pptx in sorted(root.glob(PPTX_GLOB)):
        if not pptx.is_file() or _excluded(pptx, root):
            continue
        rel = pptx.relative_to(root)
        try:
            with zipfile.ZipFile(pptx) as zf:
                for name in zf.namelist():
                    if not (name.startswith("ppt/slides/slide")
                            or name.startswith("ppt/notesSlides/notesSlide")):
                        continue
                    if not name.endswith(".xml"):
                        continue
                    text = zf.read(name).decode("utf-8", errors="replace")
                    if PLACEHOLDER.search(text):
                        slide_no = re.search(r"(\d+)\.xml$", name)
                        tag = f"#slide{slide_no.group(1)}" if slide_no else ""
                        hits.append(f"{rel}{tag}")

        except zipfile.BadZipFile:
            hits.append(f"{rel}（不是合法 zip，无法扫描——人工核）")
    return hits


def main():
    ap = argparse.ArgumentParser(description="占位残留自检（_{6,} = 未填占位）")
    ap.add_argument("root", nargs="?", default=".", help="要扫的根目录（默认当前目录）")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    hits = scan_text(root) + scan_pptx(root)
    if hits:
        print(f"✗ 发现未填占位 {len(hits)} 处（连续 ≥6 下划线；提交前必须填掉或删除）：")
        for h in hits:
            print(f"  {h}")
        return 1
    print("✓ 占位检查通过：目标范围内无未填占位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
