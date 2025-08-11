@echo off
rem 设置窗口标题，方便识别
title 人才分析报告AI - 自动化启动器 (代理版)

echo ======================================================
echo      人才分析报告AI v2.0 (代理版) 启动器
echo ======================================================
echo.

REM --- 步骤 1: 设置网络代理 (关键步骤!) ---
echo [1/3] 正在为本次运行设置网络代理...
REM !!! 请确保这里的端口号 (例如 10808) 和你科学上网工具的端口号一致 !!!
REM !!! 如果你的代理端口不是 10808, 请务必修改下面两行 !!!
set http_proxy=http://127.0.0.1:10808
set https_proxy=http://127.0.0.1:10808
echo       网络代理已设置为: %http_proxy%
echo.


REM --- 步骤 2: 激活 Python 虚拟环境 ---
echo [2/3] 正在激活 Python 虚拟环境...
call "venv\Scripts\activate.bat"

REM 检查虚拟环境是否激活成功
if %errorlevel% neq 0 (
    echo.
    echo 错误: 激活虚拟环境失败！
    echo       请检查 "venv" 文件夹是否存在于当前目录。
    echo.
    pause
    exit /b
)
echo       虚拟环境 'venv' 已成功激活。
echo.


REM --- 3: 运行人才报告生成的主程序 ---
echo [3/3] 正在启动 Python 主程序 (talent_report_pdf_generator.py)...
echo       AI正在分析您的候选人数据并生成PDF报告，这可能需要1-2分钟...
echo --------------------------------------------------------------------
echo.

python talent_report_pdf_generator.py

echo.
echo --------------------------------------------------------------------
echo 所有任务已执行完毕。
echo 请在 "output" 文件夹中查看生成的PDF报告。
echo.
pause