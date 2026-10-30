@echo off
rem 一键安装（Windows）：venv + 依赖
cd /d "%~dp0.."
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -X utf8 -m pytest -q && echo 安装完成，测试全绿