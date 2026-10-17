# Builds dist\TabloView-<version>.msix for the Microsoft Store from the PyInstaller output of build.ps1.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1          (first: builds dist\TabloView)
#   powershell -ExecutionPolicy Bypass -File packaging\build-msix.ps1     Store package (unsigned; the Store signs it)
#   powershell -ExecutionPolicy Bypass -File packaging\build-msix.ps1 -LocalTest
#       registers the unpacked package on this PC under a separate test identity, so it runs exactly
#       as a Store install would. Needs Windows Developer Mode (Settings > System > For developers);
#       unsigned .msix files can't be installed when they contain a desktop .exe.
#       Remove it with: Get-AppxPackage JoeDelVecchio.TabloViewforTabloTV | Remove-AppxPackage
# makeappx comes from Microsoft's Windows SDK BuildTools NuGet package, downloaded once into .build-tools.
param([switch]$LocalTest)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Select-String -Path app\config.py -Pattern 'APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
# The Store needs four parts and reserves the last one (must be 0)
$PackageVersion = (($Version.Split('.') + @('0', '0', '0'))[0..2] -join '.') + '.0'
$App = Join-Path $Root 'dist\TabloView'
if (-not (Test-Path "$App\TabloView.exe")) { throw 'dist\TabloView not found; run packaging\build.ps1 first.' }

# 1. makeappx
$SdkVersion = '10.0.28000.2705'
$Tools = Join-Path $Root ".build-tools\sdk-buildtools-$SdkVersion"
if (-not (Test-Path $Tools)) {
    $Zip = Join-Path $env:TEMP "sdk-buildtools-$SdkVersion.zip"
    Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.buildtools/$SdkVersion/microsoft.windows.sdk.buildtools.$SdkVersion.nupkg" -OutFile $Zip -UseBasicParsing
    Expand-Archive $Zip $Tools -Force
    Remove-Item $Zip
}
$MakeAppx = Get-ChildItem $Tools -Recurse -Filter makeappx.exe | Where-Object { $_.FullName -match '\\x64\\' } | Select-Object -First 1 -ExpandProperty FullName
if (-not $MakeAppx) { throw "makeappx.exe not found under $Tools" }

# 2. Package layout: the app folder, the manifest and tile images
$Layout = Join-Path $Root 'build\msix'
if (Test-Path $Layout) { attrib -r "$Layout\*" /s /d | Out-Null; Remove-Item -Recurse -Force $Layout }
New-Item -ItemType Directory -Force $Layout | Out-Null
Copy-Item "$App\*" $Layout -Recurse

$Py = Join-Path $Root '.build-venv\Scripts\python.exe'
& $Py -c "import sys; sys.path.insert(0, '.'); from app.icon import save_msix_assets; save_msix_assets(r'$Layout\Assets')"
if ($LASTEXITCODE -ne 0) { throw 'Could not draw the package images' }

# Partner Center > Product identity. The local test uses its own publisher so it never collides with the Store copy.
$Publisher = if ($LocalTest) { 'CN=TabloView Local Test' }
             else { 'CN=53C7BC35-D730-44D1-842F-09789A9CF005' }
$Manifest = (Get-Content (Join-Path $PSScriptRoot 'msix\AppxManifest.xml') -Raw).Replace('{{PUBLISHER}}', $Publisher).Replace('{{VERSION}}', $PackageVersion)
[IO.File]::WriteAllText((Join-Path $Layout 'AppxManifest.xml'), $Manifest, (New-Object Text.UTF8Encoding $false))

$Leaks = Get-ChildItem -Recurse $Layout -Include 'config.json', '.env', '*.db', 'settings.json' -ErrorAction SilentlyContinue
if ($Leaks) { throw "Refusing to package local data: $($Leaks.FullName -join ', ')" }

if ($LocalTest) {
    # Register from a copy outside build\ so the next build doesn't pull files out from under it
    $TestDir = Join-Path $Root '.build-tools\msix-localtest'
    Get-AppxPackage JoeDelVecchio.TabloViewforTabloTV | Where-Object { $_.InstallLocation -eq $TestDir } | Remove-AppxPackage
    if (Test-Path $TestDir) { attrib -r "$TestDir\*" /s /d | Out-Null; Remove-Item -Recurse -Force $TestDir }
    Copy-Item $Layout $TestDir -Recurse
    Add-AppxPackage -Register (Join-Path $TestDir 'AppxManifest.xml')
    Write-Host "Registered test package $PackageVersion; start it from the Start menu (TabloView for TabloTV)." -ForegroundColor Green
    return
}

# 3. Pack
$Out = Join-Path $Root "dist\TabloView-$Version.msix"
& $MakeAppx pack /d $Layout /p $Out /o /h SHA256
if ($LASTEXITCODE -ne 0) { throw 'makeappx failed' }

$Item = Get-Item $Out
Write-Host ("Done: {0} ({1:N0} MB, package version {2})" -f $Item.FullName, ($Item.Length / 1MB), $PackageVersion) -ForegroundColor Green
