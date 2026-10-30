#!/usr/bin/env bash
# 一键安装（Linux / macOS）：venv + 依赖
set -e
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then python -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
python -X utf8 -m pytest -q && echo "安装完成，测试全绿"