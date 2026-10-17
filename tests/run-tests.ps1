# Runs TabloView's tests.
#   powershell -ExecutionPolicy Bypass -File tests\run-tests.ps1          unit tests, then browser tests if TabloView is running
#   powershell -ExecutionPolicy Bypass -File tests\run-tests.ps1 -Unit    unit tests only
# Unit tests use a throwaway data folder. Browser tests need TabloView running and signed in; they fake
# every change (deletes, rules, progress, tuning), so the only real Tablo requests are page loads and
# playing a recording.
param([switch]$Unit, [string]$Url = 'http://localhost:7070')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "`n== Unit tests" -ForegroundColor Cyan
python -m unittest discover -s tests/unit -t .
$unitFailed = $LASTEXITCODE -ne 0
if ($Unit) { exit [int]$unitFailed }

Write-Host "`n== Browser tests ($Url)" -ForegroundColor Cyan
try { Invoke-WebRequest "$Url/api/system/info" -UseBasicParsing -TimeoutSec 5 | Out-Null }
catch { Write-Host "TabloView isn't running at $Url; skipping browser tests." -ForegroundColor Yellow; exit [int]$unitFailed }
$env:TABLOVIEW_URL = $Url
node tests/ui/run.mjs
$uiFailed = $LASTEXITCODE -ne 0

if ($unitFailed -or $uiFailed) { Write-Host "`nSome tests failed." -ForegroundColor Red; exit 1 }
Write-Host "`nAll tests passed." -ForegroundColor Green
