@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

REM ======================================================================
REM           周期性复盘AI v5.4 - 交互式启动器 (输入优化版)
REM ======================================================================
REM 更新日志 v5.4:
REM   - 【体验优化】彻底修复了在某些环境下需要输入两次日期的问题。
REM     通过调整输入与判断逻辑，确保一次输入即可被正确识别。
REM ======================================================================

cd /d "%~dp0"

:menu
cls
title 周期性复盘AI v5.4 - 请选择操作

echo.
echo ======================================================
echo           周期性复盘AI v5.4 (输入优化版)
echo ======================================================
echo.
echo --- 请选择要生成的报告类型 ---
echo.
echo   [1] 生成日报 (Daily Review)
echo   [2] 生成周报 (Weekly Review)
echo   [3] 生成月报 (Monthly Review)
echo   [4] 生成季报 (Quarterly Review)
echo   [5] 生成年报 (Yearly Review)
echo.
echo --- 其他功能 ---
echo   [6] 补写历史日报 (Refill History)
echo.
echo   [Q] 退出程序 (Quit)
echo.
echo ------------------------------------------------------
echo.

set "choice="
set /p choice="请输入您的选择 (1-6 或 Q) 并按回车: "

set "command_args="
if /i "%choice%"=="1" set command_args=--type daily
if /i "%choice%"=="2" set command_args=--type weekly
if /i "%choice%"=="3" set command_args=--type monthly
if /i "%choice%"=="4" set command_args=--type quarterly
if /i "%choice%"=="5" set command_args=--type yearly
if /i "%choice%"=="q" exit /b

if /i "%choice%"=="6" (
    goto refill_date_input
)

if not defined command_args (
    echo.
    echo  !! 无效的输入。请按任意键返回菜单。
    pause > nul
    goto menu
)

goto run_script

:refill_date_input
cls
echo.
echo --- 补写历史日报 ---
echo.
set "refill_date="
set /p refill_date="请输入要补写的日期 (格式: YYYY-MM-DD), 例如 2024-07-28: "

if not defined refill_date (
    echo.
    echo  !! 错误: 您没有输入任何日期！
    echo     请按任意键重新输入...
    pause > nul
    goto refill_date_input
)
set command_args=--date %refill_date%
goto run_script


:run_script
cls
title 周期性复盘AI v5.4 - 正在执行...

echo ======================================================
echo           正在为您执行任务...
echo ======================================================
echo.

REM --- 步骤 1: 设置网络代理 ---
echo [1/4] 正在为本次运行设置网络代理...
set http_proxy=http://127.0.0.1:10808
set https_proxy=http://127.0.0.1:10808
echo.

REM --- 步骤 2: 激活 Python 虚拟环境 ---
echo [2/4] 正在激活 Python 虚拟环境...
call "venv\Scripts\activate.bat"
echo.

REM --- 步骤 3: 运行主程序并传入选择的类型 ---
echo [3/4] 正在启动 Python 主程序 (review_ai.py)...
echo       AI正在分析数据，请稍候...
echo ------------------------------------------------------
echo.

python daily.py %command_args%

echo.
echo ------------------------------------------------------
echo [4/4] 所有任务已执行完毕。
pause
goto menu