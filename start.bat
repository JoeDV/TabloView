@echo off
title Tablo Classic UI
echo ========================================================
echo       Tablo Classic UI - 4th Gen Recordings Manager
echo ========================================================
echo.
cd /d "%~dp0"

echo Launching browser at http://localhost:7070 ...
start http://localhost:7070

echo Starting Python FastAPI backend on port 7070...
echo (Press Ctrl+C to stop the server at any time)
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 7070
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with error.
    pause
)
