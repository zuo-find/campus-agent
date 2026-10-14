@echo off
chcp 65001 >nul
title 校园服务智能体 - 后端服务
cd /d "%~dp0backend"

set PYTHONPATH=%CD%

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 没找到虚拟环境 .venv，请先在 backend 目录执行:
  echo        uv venv .venv ^&^& uv pip install --python .venv -r requirements.txt
  echo.
  pause
  exit /b 1
)

rem 取本机局域网 IP：手机 / 体验版要连的就是这个地址
set LANIP=127.0.0.1
for /f "delims=" %%i in ('.venv\Scripts\python.exe scripts\lan_ip.py') do set LANIP=%%i

echo ================================================
echo   校园服务智能体 · 后端服务
echo ================================================
echo.
echo   启动后【不要关闭这个黑窗口】。
echo   关闭窗口 = 后端停止 = 小程序里的功能会连不上。
echo.
echo   本机访问（开发者工具）: http://127.0.0.1:8000
echo   手机访问（体验版）    : http://%LANIP%:8000
echo                          ^> 小程序「我的 - 服务器地址」里填这一条
echo.
echo   接口文档: http://127.0.0.1:8000/docs
echo.
echo   手机连不上时依次检查:
echo     1. 手机和这台电脑连的是同一个 WiFi
echo     2. 首次启动 Windows 弹窗要点「允许访问」
echo     3. 还不行：用管理员身份执行一次下面这行（放行 8000 端口）
echo        netsh advfirewall firewall add rule name="campus-agent" dir=in action=allow protocol=TCP localport=8000
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo 后端已停止。
pause
