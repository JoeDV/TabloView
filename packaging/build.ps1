# Builds dist\TabloView-Setup-<version>.exe
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Needs: Python 3.12, FFmpeg (winget install Gyan.FFmpeg.Essentials), Inno Setup 6 (winget install JRSoftware.InnoSetup)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Select-String -Path app\config.py -Pattern 'APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Building TabloView $Version" -ForegroundColor Cyan

# 1. Isolated build environment
$Py = Join-Path $Root '.build-venv\Scripts\python.exe'
if (-not (Test-Path $Py)) {
    python -m venv .build-venv
    & $Py -m pip install --upgrade pip
}
# winrt-*: Start with Windows in the Microsoft Store package (app/startup.py)
& $Py -m pip install -q -r requirements.txt pyinstaller pystray pillow winrt-runtime winrt-Windows.ApplicationModel winrt-Windows.ApplicationModel.Activation winrt-Windows.Foundation winrt-Windows.Services.Store
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

# 1b. Unit tests must pass before anything is packaged (they use a throwaway data folder)
if (-not $env:TABLOVIEW_SKIP_TESTS) {
    Write-Host 'Running unit tests...'
    # unittest reports on stderr; PowerShell 5.1 would turn that into a terminating error under 'Stop',
    # so relax it here and judge by the exit code
    $ErrorActionPreference = 'Continue'
    $TestOutput = & $Py -m unittest discover -s tests/unit -t . 2>&1 | ForEach-Object { "$_" }
    $TestExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $TestOutput | Select-String -Pattern '^(Ran |OK|FAILED|ERROR:|FAIL:)'
    if ($TestExit -ne 0) {
        $TestOutput | Select-Object -Last 40
        throw 'Unit tests failed; not building. (Set TABLOVIEW_SKIP_TESTS=1 to override.)'
    }
}

# 2. Clear previous outputs. Folders on this machine can pick up the ReadOnly attribute,
#    which makes PyInstaller's own --clean fail with "Access is denied".
foreach ($old in 'build', 'dist\TabloView') {
    $p = Join-Path $Root $old
    if (Test-Path $p) {
        attrib -r "$p\*" /s /d | Out-Null
        Remove-Item -Recurse -Force $p
    }
}

# 3. Stage FFmpeg, icon and version resource
$Stage = Join-Path $Root 'build\stage'
New-Item -ItemType Directory -Force (Join-Path $Stage 'ffmpeg') | Out-Null

$Ffmpeg = & $Py -c "import sys; sys.path.insert(0, '.'); from app.config import find_ffmpeg; print(find_ffmpeg())"
if (-not (Test-Path $Ffmpeg)) { throw "FFmpeg not found ($Ffmpeg). Install it: winget install Gyan.FFmpeg.Essentials" }
Copy-Item $Ffmpeg (Join-Path $Stage 'ffmpeg\ffmpeg.exe')
$FfmpegRoot = Split-Path -Parent (Split-Path -Parent $Ffmpeg)
foreach ($f in 'LICENSE', 'README.txt') {
    $src = Join-Path $FfmpegRoot $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $Stage "ffmpeg\FFmpeg-$f.txt") }
}

& $Py -c "import sys; sys.path.insert(0, '.'); from app.icon import save_ico; save_ico(r'$Stage\tabloview.ico')"

$v = ($Version.Split('.') + @('0', '0', '0'))[0..3] -join ', '
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Joe Del Vecchio'),
    StringStruct('FileDescription', 'TabloView'),
    StringStruct('FileVersion', '$Version'),
    StringStruct('ProductName', 'TabloView'),
    StringStruct('ProductVersion', '$Version'),
    StringStruct('OriginalFilename', 'TabloView.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@ | Set-Content -Encoding ascii (Join-Path $Stage 'version_info.txt')

# 4. Bundle the app (never include local credentials or caches)
& $Py -m PyInstaller packaging\tabloview.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$Leaks = Get-ChildItem -Recurse dist\TabloView -Include 'config.json', '.env', '*.db', 'settings.json' -ErrorAction SilentlyContinue
if ($Leaks) { throw "Refusing to package local data: $($Leaks.FullName -join ', ')" }

# 5. Installer
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw 'Inno Setup not found. Install it: winget install JRSoftware.InnoSetup' }
& $Iscc /Q "/DAppVersion=$Version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }

# 6. version.json for in-app update notices. After the GitHub release is published
#    (packaging\publish-release.ps1), publish it with packaging\publish-version.ps1.
#    Optional release notes: packaging\release-notes.txt
$DownloadUrl = & $Py -c "import sys; sys.path.insert(0, '.'); from app.config import RELEASE_DOWNLOAD_URL; print(RELEASE_DOWNLOAD_URL)"
$NotesFile = Join-Path $PSScriptRoot 'release-notes.txt'
$Notes = if (Test-Path $NotesFile) { (Get-Content $NotesFile -Raw).Trim() } else { '' }
$Json = [ordered]@{ version = $Version; download_url = $DownloadUrl; notes = $Notes; published = (Get-Date).ToString('yyyy-MM-dd') } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $Root 'dist\version.json'), $Json, (New-Object Text.UTF8Encoding $false))  # UTF-8 without BOM

$Out = Get-Item "dist\TabloView-Setup-$Version.exe"
Write-Host ("Done: {0} ({1:N0} MB)" -f $Out.FullName, ($Out.Length / 1MB)) -ForegroundColor Green
