@echo off
title 每日复盘AI - 自动化启动器 (代理版)

echo ======================================================
echo           每日复盘AI v3.0 (代理版) 启动器
echo ======================================================
echo.

REM --- 步骤 1: 设置网络代理 (关键步骤!) ---
echo [1/3] 正在为本次运行设置网络代理...
REM !!! 请确保这里的端口号 (10808) 和你代理工具的端口号一致 !!!
REM !!! 如果你的代理端口不是10808, 请修改下面两行 !!!
set http_proxy=http://127.0.0.1:10808
set https_proxy=http://127.0.0.1:10808
echo       网络代理已设置为: http://127.0.0.1:10808
echo.


REM --- 步骤 2: 激活 Python 虚拟环境 ---
echo [2/3] 正在激活 Python 虚拟环境...
call "venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo 错误: 激活虚拟环境失败！请检查venv文件夹是否存在。
    pause
    exit /b
)
echo       虚拟环境已成功激活。
echo.


REM --- 步骤 3: 自动运行主程序 ---
echo [3/3] 正在启动 Python 主程序 (daily_review_ai.py)...
echo       AI正在分析您一天的工作，请稍候...
echo ------------------------------------------------------
echo.

python daily1.py

echo.
echo ------------------------------------------------------
echo 所有任务已执行完毕。
pause