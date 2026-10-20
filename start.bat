@echo off
rem Runs TabloView from source: double-click, or run from a command prompt. See start.ps1.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1
if %ERRORLEVEL% NEQ 0 pause
