"""ctl.py — 跨平台任务入口（Windows / macOS / Linux，替代 Makefile）。

用法：
  python scripts/ctl.py test      # pytest 全量测试
  python scripts/ctl.py lint      # ruff check（未安装则跳过并提示）
  python scripts/ctl.py smoke     # node scripts/smoke_frontend.mjs 前端冒烟
  python scripts/ctl.py assets    # 重新生成 static/demo*.json 演示资产
  python scripts/ctl.py serve     # 启动 uvicorn（0.0.0.0:8000）
  python scripts/ctl.py ci        # 依次 lint → test → smoke，任一失败非零退出
  python scripts/ctl.py preflight # 提交预检板：视频/六图/常量/地址/占位/任务单/版本号（03M）
  python scripts/ctl.py verify    # 公网部署验证：python scripts/ctl.py verify http://IP:8000
  python scripts/ctl.py package   # 组装提交 zip（scripts/package.py）
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(cmd, **kw):
    """跑子进程：继承输出，返回退出码。"""
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    return subprocess.run([str(c) for c in cmd], cwd=ROOT, **kw).returncode


def cmd_test():
    return sh([sys.executable, "-X", "utf8", "-m", "pytest"])


def cmd_lint_safe():
    """ruff 未安装时跳过并提示（不阻塞 ci）。"""
    probe = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"],
        capture_output=True, cwd=ROOT,
    )
    if probe.returncode != 0:
        print("ruff 未安装，跳过 lint（可选装：pip install ruff）")
        return 0
    return sh([sys.executable, "-m", "ruff", "check", "."])


def cmd_smoke():
    return sh(["node", "scripts/smoke_frontend.mjs"])


def cmd_assets():
    rc = sh([sys.executable, "-X", "utf8", "scripts/export_demo_assets.py"])
    if rc == 0:
        print("演示资产已重新生成（真实运行产物，含 SHA-256）")
    return rc


def cmd_serve():
    print("启动 uvicorn: http://0.0.0.0:8000 （Ctrl+C 停止）")
    return sh([sys.executable, "-X", "utf8", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"])


def cmd_ci():
    steps = [("lint", cmd_lint_safe), ("test", cmd_test), ("smoke", cmd_smoke)]
    for name, fn in steps:
        print(f"\n===== CI 步骤：{name} =====")
        rc = fn()
        if rc != 0:
            print(f"✗ CI 失败于 {name}（退出码 {rc}）")
            return rc
    print("\n✓ CI 全部通过：lint + test + smoke")
    return 0


def cmd_preflight():
    """提交预检板（03M 任务B）：--offline 跳过地址可达项。"""
    return sh([sys.executable, "-X", "utf8", "scripts/preflight.py", *sys.argv[2:]])


def cmd_verify():
    """公网部署验证（03M 任务C）：python scripts/ctl.py verify http://IP:8000"""
    if len(sys.argv) < 3:
        print("用法：python scripts/ctl.py verify http://<公网IP>:8000")
        return 2
    return sh([sys.executable, "-X", "utf8", "scripts/verify_deploy.py", sys.argv[2]])


def cmd_package():
    return sh([sys.executable, "-X", "utf8", "scripts/package.py", *sys.argv[2:]])


COMMANDS = {
    "test": cmd_test, "lint": cmd_lint_safe, "smoke": cmd_smoke,
    "assets": cmd_assets, "serve": cmd_serve, "ci": cmd_ci, "package": cmd_package,
    "preflight": cmd_preflight, "verify": cmd_verify,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())

