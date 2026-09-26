@echo off
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo [info] Requesting administrator permission...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0.'"
    if errorlevel 1 (
        echo [error] Administrator permission was not granted.
        pause
    )
    exit /b
)

echo ================================
echo   Pet Warehouse
echo ================================
echo.

where uv >nul 2>&1
if errorlevel 1 goto try_python

echo [info] Starting server as administrator. Press Ctrl+C to stop.
echo [info] Open http://localhost:8000
echo.
uv run python backend/main.py
goto done

:try_python
where python >nul 2>&1
if errorlevel 1 (
    echo [error] Neither uv nor python was found. Install one and add it to PATH.
    pause
    exit /b 1
)

echo [info] uv was not found. Starting with python.
echo [info] Open http://localhost:8000
echo.
python backend/main.py

:done
if errorlevel 1 (
    echo.
    echo [error] Server exited with code %ERRORLEVEL%
)
pause
