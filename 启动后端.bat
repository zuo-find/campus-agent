@echo off
chcp 65001 >nul
title 校园服务智能体 - 后端服务
cd /d "%~dp0backend"

echo ================================================
echo   校园服务智能体 · 后端服务
echo ================================================
echo.
echo   启动后【不要关闭这个黑窗口】。
echo   关闭窗口 = 后端停止 = 小程序里的功能会连不上。
echo.
echo   地址: http://127.0.0.1:8000
echo   接口文档: http://127.0.0.1:8000/docs
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 没找到虚拟环境 .venv，请先在 backend 目录执行:
  echo        uv venv .venv ^&^& uv pip install --python .venv -r requirements.txt
  echo.
  pause
  exit /b 1
)

set PYTHONPATH=%CD%
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo 后端已停止。
pause
