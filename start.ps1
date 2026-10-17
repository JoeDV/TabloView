# Tablo Classic UI PowerShell Launcher
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "      Tablo Classic UI - 4th Gen Recordings Manager" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location -Path $PSScriptRoot

Write-Host "Opening web interface at http://localhost:7070 ..." -ForegroundColor Green
Start-Process "http://localhost:7070"

Write-Host "Starting backend server on port 7070 (Press Ctrl+C to stop)..." -ForegroundColor Yellow
python -m uvicorn app.main:app --host 0.0.0.0 --port 7070
