@echo off
rem ======================================================
rem           AI智能助手 v21.0 - 最终版启动器
rem ======================================================
rem  说明:
rem  - 本脚本用于启动【AI智能助手 v21.0】。
rem  - 它会自动激活Python环境、设置代理并运行主程序。
rem ======================================================

set SCRIPT_NAME=aa.py
title AI智能助手 v21.0 (%SCRIPT_NAME%) - 正在启动...

echo [1/3] 正在激活 Python 虚拟环境 (venv)...
call "venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo.
    echo 错误: 激活虚拟环境失败！
    echo 请检查当前目录下是否存在 venv\Scripts\activate.bat 文件。
    pause
    exit /b
)
echo       虚拟环境已成功激活。
echo.

echo [2/3] 正在设置网络代理 (如不需要可删除这两行)...
set http_proxy=http://127.0.0.1:10808
set https_proxy=http://127.0.0.1:10808
echo       代理已设置为 http://127.0.0.1:10808
echo.

echo [3/3] 正在启动主程序: %SCRIPT_NAME%...
echo       程序已启动，请在弹出的窗口中按功能键操作：
echo         - F1: 开始/结束会议
echo         - F2: 启动实时字幕
echo       要彻底关闭程序，请直接【关闭弹出的GUI窗口】。
echo       本窗口将显示后台运行日志。
echo ------------------------------------------------------
echo.

rem 关键：在已经激活的环境中，直接调用python来运行你的脚本
python %SCRIPT_NAME%

echo.
echo 程序已退出。感谢使用！
pause