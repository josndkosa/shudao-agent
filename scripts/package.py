"""package.py — 一键组装提交 zip（任务 F）。

用法：
  python scripts/package.py --team 队伍名 --version 1.0.0 --name 姓名 --phone 手机号
                            [--max-mb 100] [--allow-missing-media]

按 codearts_proof/zip-layout.md 的映射组装：
  project/         ← 本仓库（除 codearts_proof/ 缓存与密钥）
  codearts_proof/  ← 码道留痕（任务单/调试记录/截图）
  readme/ ppt/ video/ ← 对应交付目录

自检（任一不过 → 非零退出，不产出 zip）：
  - 五个必需目录存在且非空（video/ppt 未就绪时给出清晰提示而非崩溃）
  - video/ 有 .mp4；codearts_proof/ 截图 ≥ 8；已执行 prompt 原文在
  - 包内无 .env / __pycache__ / .pytest_cache（只有 .env.example）
  - 密钥扫描（03K 任务F4）：staging 内容级搜 sk- 前缀与带值的 DEEPSEEK_API_KEY=
    ——排除表正确不是可以依赖的假设，这是最后一道防线
  - zip 体积 ≤ --max-mb（默认 100，超限删包退出并打印实际体积）
  - 收尾打印每个顶层目录的解压体积（评委一眼看出哪个目录畸大）
"""
import argparse
import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "_stage"
NEED_DIRS = ["project", "codearts_proof", "readme", "ppt", "video"]

EXCLUDE_FILES = {".env", ".env.local"}
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".git", "_stage",
                ".mypy_cache", ".ruff_cache", "node_modules", ".codeartsdoer"}

# 密钥形态（字节级匹配）：
#   sk- 后跟 ≥16 位字母数字 → DeepSeek/OpenAI 风格密钥（短词「sk-」不误伤文档叙述）
#   DEEPSEEK_API_KEY= 紧跟 ≥8 位 key 形态字符 → 带真实值的配置行
#   （.env.example 里注释掉的空值模板 `# DEEPSEEK_API_KEY=` 两条都不命中——
#    注释行与空值不是泄漏；曾经误填过一次 key 的教训见 CHANGELOG v1.1.6）
SECRET_PATTERNS = [
    (re.compile(rb"sk-[A-Za-z0-9]{16,}"), "sk- 前缀密钥"),
    (re.compile(rb"DEEPSEEK_API_KEY=[A-Za-z0-9_\-]{8,}"), "DEEPSEEK_API_KEY 带值"),
]
# 压缩/媒体二进制不做内容扫描（密钥在压缩容器内不可见）
SKIP_SCAN_EXT = {".mp4", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
                 ".woff", ".woff2", ".ttf", ".otf", ".pptx", ".pdf"}


def copy_tree_filtered(src: Path, dst: Path):
    """递归拷贝并过滤（密钥/缓存/临时物绝入不了包）。"""
    dst.mkdir(parents=True, exist_ok=True)
    for it in src.iterdir():
        if it.name in EXCLUDE_DIRS or it.name in EXCLUDE_FILES or it.name.endswith(".tmp.json"):
            continue
        if it.is_dir():
            copy_tree_filtered(it, dst / it.name)
        else:
            shutil.copy2(it, dst / it.name)


def scan_secrets(stage: Path) -> list[str]:
    """staging 内容级密钥扫描：返回命中描述列表（空 = 干净）。"""
    hits = []
    for f in sorted(stage.rglob("*")):
        if not f.is_file() or f.suffix.lower() in SKIP_SCAN_EXT:
            continue
        if f.stat().st_size > 2 * 1024 * 1024:   # 超大文本跳过（防误配的二进制拖慢）
            continue
        raw = f.read_bytes()
        for pat, desc in SECRET_PATTERNS:
            if pat.search(raw):
                hits.append(f"{desc}：{f.relative_to(stage)}")
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True, help="队伍名（必填）")
    ap.add_argument("--version", required=True, help="版本号（必填，如 1.0.0）")
    ap.add_argument("--name", required=True, help="姓名（必填）")
    ap.add_argument("--phone", required=True, help="手机号（必填）")
    ap.add_argument("--max-mb", type=float, default=100.0,
                    help="zip 体积上限（MB，默认 100；超限删包退出）")
    ap.add_argument("--allow-missing-media", action="store_true",
                    help="允许 video/ppt 暂缺（仅开发期自测用；正式提交不要带）")
    args = ap.parse_args()

    # 1. staging
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "project").mkdir(parents=True)
    copy_tree_filtered(ROOT, STAGE / "project")
    # project/ 不含 codearts_proof（zip 里两者是并列目录）
    shutil.rmtree(STAGE / "project" / "codearts_proof", ignore_errors=True)
    # 顶层四目录（readme/ppt/video 来自仓库根，尚未就绪则建占位目录并提示）
    for d in ("codearts_proof", "readme", "ppt", "video"):
        src = ROOT / d
        dst = STAGE / d
        if src.exists():
            shutil.copytree(src, dst)
        else:
            dst.mkdir(parents=True)

    # 2. 自检
    # 2.0 密钥扫描（03K 任务F4）——**不可放行的失败**：媒体缺失可以 --allow-missing-media
    #     放行（开发期自测），密钥泄漏不行——排除表永远正确不是可以依赖的假设
    secret_hits = scan_secrets(STAGE)
    if secret_hits:
        print("自检未通过（不产出 zip）：密钥扫描命中（--allow-missing-media 也不放行）：")
        for h in secret_hits:
            print(f"  ✗ {h}")
        shutil.rmtree(STAGE, ignore_errors=True)
        return 1
    problems = []
    for d in NEED_DIRS:
        if not any((STAGE / d).iterdir()):
            problems.append(f"必需目录为空：{d}/")
    media = list((STAGE / "video").glob("*.mp4"))
    if not media:
        problems.append("video/ 中没有 .mp4（3 分钟演示视频尚未录制）")
    shots = [p for p in (STAGE / "codearts_proof").rglob("*.png")] + \
            [p for p in (STAGE / "codearts_proof").rglob("*.jpg")]
    if len(shots) < 8:
        problems.append(f"codearts_proof/ 截图仅 {len(shots)} 张（要求 ≥ 8：码道对话/生成过程留痕）")
    prompts_dir = STAGE / "codearts_proof" / "prompts" / "_已执行"
    # 已归档任务单前缀全量清单（03H 任务H6）：03E 此前漏列；03F 前缀被两个任务单
    # 历史复用（瑞士网格/在线截断修复），一个前缀匹配多份原文属预期；03G~03J/05 已归档补入
    need_prompts = ["00_", "01_", "01B_", "01C_", "02_", "03_", "03B_", "03C_",
                    "03D_", "03E_", "03F_", "03G_", "03H_", "03I_", "03J_", "03K_",
                    "04_", "05_"]
    archived = list(prompts_dir.glob("*.md")) if prompts_dir.exists() else []
    for tag in need_prompts:
        if not any(p.name.startswith(tag) for p in archived):
            problems.append(f"codearts_proof/prompts/_已执行/ 缺 {tag}* 任务单原文")
    if len(archived) < len(need_prompts):
        problems.append(f"归档任务单 {len(archived)} 份 < 清单 {len(need_prompts)} 项（有前缀漏归档）")
    # tests/ 临时调试文件：会随 copy 进 zip 的 project/tests/（03H 任务H6——
    # 03F 前夜 _tmp_debug2.py 曾 untracked 挡 lint 且险进包）
    for bad in (ROOT / "tests").glob("_tmp*"):
        problems.append(f"tests/ 下存在临时文件：{bad.name}（会打进 zip，先清理）")
    # codearts_proof 01-07 编号子目录必须齐全且非空（空目录进 zip 就是空文件夹）
    for i in range(1, 8):
        subs = [d for d in (STAGE / "codearts_proof").iterdir()
                if d.is_dir() and d.name.startswith(f"{i:02d}-")]
        if not subs:
            problems.append(f"codearts_proof/ 缺 {i:02d}- 编号子目录")
        elif not any(sub.iterdir() for sub in subs):
            problems.append(f"codearts_proof/{subs[0].name} 为空目录（补材料或删空目录）")
    # 密钥/缓存泄漏检查
    for bad in (STAGE).rglob(".env"):
        problems.append(f"包内出现 .env：{bad}")
    for bad in (STAGE).rglob("__pycache__"):
        problems.append(f"包内出现 __pycache__：{bad}")

    if problems:
        print("自检未通过（不产出 zip）：")
        for p in problems:
            print(f"  ✗ {p}")
        if not args.allow_missing_media:
            print("\n提示：视频/截图尚未就绪属正常（开发期）。加 --allow-missing-media 可先产出"
                  "结构自测包；正式提交前必须补齐并通过完整自检。")
            shutil.rmtree(STAGE, ignore_errors=True)
            return 1
        print("\n（--allow-missing-media：媒体缺失已放行，仅作结构自测）")

    # 3. 打 zip
    zip_name = f"蜀道智行_{args.team}_{args.version}_{args.name}_{args.phone}.zip"
    zip_path = ROOT / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in STAGE.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(STAGE))

    # 3.5 体积闸（03K 任务F4）：超限即删包退出——宁可失败也不交一个打不开的 zip
    raw = zip_path.read_bytes()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > args.max_mb:
        zip_path.unlink()
        print(f"\n✗ 打包失败：zip 实际 {size_mb:.1f} MB，超过上限 {args.max_mb:g} MB（已删除，不产出）")
        print("  排查方向：video/ 与 ppt/ 通常是大头——压缩参数或素材规格需复核")
        shutil.rmtree(STAGE, ignore_errors=True)
        return 1

    # 4. 报告
    print(f"\n✓ 打包完成：{zip_path}")
    print(f"  大小：{len(raw):,} bytes（{size_mb:.1f} MB / 上限 {args.max_mb:g} MB）"
          f"  SHA-256：{hashlib.sha256(raw).hexdigest()}")
    with zipfile.ZipFile(zip_path) as zf:
        inner = zf.namelist()
        by_top: dict[str, int] = {}
        for info in zf.infolist():
            top = info.filename.split("/")[0]
            by_top[top] = by_top.get(top, 0) + info.file_size
    tops = sorted(by_top, key=by_top.get, reverse=True)
    print("  顶层目录体积（解压后，定位畸大目录）：")
    for top in tops:
        print(f"    {top:<16s} {by_top[top] / (1024 * 1024):>8.1f} MB")
    print(f"  顶层结构：{' / '.join(sorted(tops))}")
    print(f"  文件数：{len(inner)}")
    shutil.rmtree(STAGE, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
