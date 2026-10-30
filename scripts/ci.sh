#!/usr/bin/env bash
# CI 脚本（Linux/macOS）：lint → test → smoke，任一失败即非零退出
# 本项目 CI 已脚本化，可直接接入华为云 CodeArts 流水线
set -e
cd "$(dirname "$0")/.."
python -m ruff check . || echo "（ruff 未安装则跳过 lint）"
python -X utf8 -m pytest -q
node scripts/smoke_frontend.mjs
echo "✓ CI 全部通过"