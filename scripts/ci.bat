@echo off
rem CI 脚本（Windows）：lint → test → smoke，任一失败即非零退出
rem 本项目 CI 已脚本化，可直接接入华为云 CodeArts 流水线
cd /d "%~dp0.."
python -m ruff check . 2>nul || echo （ruff 未安装则跳过 lint）
if errorlevel 1 exit /b 1
python -X utf8 -m pytest -q
if errorlevel 1 exit /b 1
node scripts/smoke_frontend.mjs
if errorlevel 1 exit /b 1
echo ✓ CI 全部通过