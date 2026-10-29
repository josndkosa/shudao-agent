@echo off
rem 蜀道智行后端启动脚本（Windows）：venv → 依赖 → uvicorn 8000
cd /d "%~dp0.."
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000