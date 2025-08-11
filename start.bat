@echo off
title AI实时字幕工具 v4.0 - 自动化启动器

echo ======================================================
echo           AI实时字幕工具 v4.0 启动器
echo ======================================================
echo.

REM --- 步骤 1: 自动激活 Python 虚拟环境 ---
echo [1/3] 正在激活 Python 虚拟环境 (venv)...
call "venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo 错误: 激活虚拟环境失败！请检查 venv 文件夹是否存在。
    pause
    exit /b
)
echo       虚拟环境已成功激活。
echo.

REM --- 步骤 2: 自动设置网络代理 (如果需要) ---
echo [2/3] 正在设置网络代理...
set http_proxy=http://127.0.0.1:10808
set https_proxy=http://127.0.0.1:10808
echo       代理已设置为 http://127.0.0.1:10808
echo.

REM --- 步骤 3: 自动运行主程序 ---
echo [3/3] 正在启动 Python 主程序 (main.py)...
echo       程序已启动，请查看弹出的字幕窗口。
echo       要彻底关闭程序，请直接关闭本窗口。
echo ------------------------------------------------------
echo.

REM 关键：在已经激活的环境中，直接调用python来运行你的脚本
python mai.py

echo.
echo 程序已退出。
pause