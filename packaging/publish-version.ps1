# Publishes dist\version.json to the update gist, so installed copies see "Update available".
# Run AFTER the new installer is in the OneDrive folder:
#   powershell -ExecutionPolicy Bypass -File packaging\publish-version.ps1
# Uses your normal git credentials for github.com.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Json = Join-Path $Root 'dist\version.json'
if (-not (Test-Path $Json)) { throw 'dist\version.json not found. Run packaging\build.ps1 first.' }
$Gist = (Select-String -Path app\config.py -Pattern 'UPDATE_GIST = "(.+)"').Matches[0].Groups[1].Value
$GitUrl = ($Gist -replace 'gist\.github\.com/[^/]+/', 'gist.github.com/') + '.git'

$Work = Join-Path $Root 'build\gist'
if (Test-Path $Work) { attrib -r "$Work\*" /s /d | Out-Null; Remove-Item -Recurse -Force $Work }
git clone --quiet $GitUrl $Work
if ($LASTEXITCODE -ne 0) { throw "Couldn't clone $GitUrl" }

Copy-Item $Json (Join-Path $Work 'version.json') -Force
$Version = (Get-Content $Json -Raw | ConvertFrom-Json).version
git -C $Work add version.json
git -C $Work diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host "Gist already at $Version" -ForegroundColor Yellow; exit 0 }
git -C $Work commit --quiet -m "TabloView $Version"
git -C $Work push --quiet
if ($LASTEXITCODE -ne 0) { throw 'Push to gist failed' }
Write-Host "Published version.json for $Version (GitHub may take up to 5 minutes to serve it)" -ForegroundColor Green
