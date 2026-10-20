# Runs TabloView from source on Windows: sets up a private Python environment the first time, then
# starts the server on this computer only and opens it in the browser. Stop it with Ctrl+C.
#   powershell -ExecutionPolicy Bypass -File start.ps1
# Needs Python 3.12+ and FFmpeg (winget install Gyan.FFmpeg.Essentials).
Set-Location -Path $PSScriptRoot

if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Host "First run: setting up TabloView (this takes a minute)..." -ForegroundColor Cyan
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't create the environment. Is Python 3.12+ installed?" -ForegroundColor Red; exit 1 }
    .venv\Scripts\python -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't install TabloView's packages." -ForegroundColor Red; Remove-Item -Recurse -Force .venv; exit 1 }
}

Write-Host "TabloView is starting at http://localhost:7070  (press Ctrl+C to stop)" -ForegroundColor Green
Start-Job { Start-Sleep 3; Start-Process "http://localhost:7070" } | Out-Null
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 7070
