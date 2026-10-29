#!/usr/bin/env bash
# 蜀道智行后端启动脚本（Linux/macOS）：venv → 依赖 → uvicorn 8000
set -e
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then python -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000