@echo off
chcp 936 >nul
title 校园服务智能体 - 内网穿透
cd /d "%~dp0"

echo ================================================
echo   校园服务智能体 · 后端 + 内网穿透
echo ================================================
echo.

where cpolar >nul 2>&1
if errorlevel 1 (
  echo [没找到 cpolar] 先按下面步骤装好再来:
  echo    1. 到 https://www.cpolar.com 注册（不用实名）
  echo    2. 下载 Windows 客户端并安装
  echo    3. 复制后台「验证」页里的 authtoken，执行一次:
  echo         cpolar authtoken ^<你的token^>
  echo    详细说明见 docs\内网穿透.md
  echo.
  pause
  exit /b 1
)

echo [1/2] 正在启动后端（会弹出一个新窗口，那个窗口不要关）...
start "校园助手-后端" "%~dp0启动后端.bat"

echo       等后端起来...
timeout /t 4 /nobreak >nul

echo.
echo [2/2] 正在打开公网通道...
echo.
echo   ^>^> 下面 Forwarding 这一行，箭头左边的网址就是公网地址，
echo   ^>^> 复制它填到小程序「我的 - 服务器地址」里。
echo.
echo   注意: cpolar 免费版每次重启网址都会变，变了就重新填一次。
echo.

cpolar http 8000

echo.
echo 通道已关闭。
pause
