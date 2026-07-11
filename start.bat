@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================
echo   洛克王国世界 — 宠物仓库
echo ================================
echo.

REM 检查 Python 是否可用
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Python，请确保 Python 已安装并加入 PATH
    pause
    exit /b 1
)

REM 检查依赖是否已安装
python -c "import fastapi, uvicorn" 2>nul
if %ERRORLEVEL% neq 0 (
    echo [提示] 首次运行，正在安装依赖...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo.
)

echo [信息] 启动服务器...（按 Ctrl+C 停止）
echo [信息] 浏览器访问 http://localhost:8000
echo.
python backend/main.py

pause
