# Creates the GitHub release for the current version: tag v<version>, with the Windows installer, the
# Mac zip and the Linux download attached, and the release notes. Run after build.ps1 and git push.
#   powershell -ExecutionPolicy Bypass -File packaging\publish-release.ps1
#   ... -Commit <sha>   release an earlier commit (default: the current one, which must be on GitHub)
# Needs the GitHub CLI, signed in once: winget install GitHub.cli, then gh auth login.
param([string]$Commit = '')
$ErrorActionPreference = 'Stop'
# Read git's output as UTF-8 (Windows PowerShell otherwise garbles characters like an em dash)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $Gh) { $Gh = "$env:ProgramFiles\GitHub CLI\gh.exe" }
if (-not (Test-Path $Gh)) { throw 'GitHub CLI not found: winget install GitHub.cli, then gh auth login' }

if (-not $Commit) { $Commit = 'HEAD' }
$Commit = git rev-parse "$Commit^{commit}"  # GitHub needs the full commit ID
$Version = ((git show "${Commit}:app/config.py") | Select-String 'APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
$Tag = "v$Version"
$Setup = "dist\TabloView-Setup-$Version.exe"
if (-not (Test-Path $Setup)) { throw "$Setup not found. Run packaging\build.ps1 first." }

# The release points at a commit GitHub must already have
git fetch --quiet origin
git merge-base --is-ancestor $Commit origin/main
if ($LASTEXITCODE -ne 0) { throw "Push first: $Commit isn't on GitHub yet" }

# Mac and Linux downloads: the source of that commit (the start scripts stay runnable)
$Mac = "dist\TabloView-$Version-mac.zip"
$Linux = "dist\TabloView-$Version-linux.tar.gz"
git archive --format=zip --prefix=TabloView/ -o $Mac $Commit
git archive --format=tar.gz --prefix=TabloView/ -o $Linux $Commit

$Notes = ((git show "${Commit}:packaging/release-notes.txt") -join "`n").Trim()
$Body = @"
$Notes

**Downloads**
- **Windows:** ``TabloView-Setup-$Version.exe``, or get it from the [Microsoft Store](https://apps.microsoft.com/detail/9NCWVSC7KX2N) (updates automatically). The installer isn't code-signed, so Windows may say "Windows protected your PC": click **More info**, then **Run anyway**.
- **Mac:** ``TabloView-$Version-mac.zip``, see [MAC.md](https://github.com/JoeDV/TabloView/blob/main/MAC.md)
- **Linux:** ``TabloView-$Version-linux.tar.gz``, see [LINUX.md](https://github.com/JoeDV/TabloView/blob/main/LINUX.md)
"@

$exists = $false
try { & $Gh release view $Tag 2>$null | Out-Null; $exists = ($LASTEXITCODE -eq 0) } catch { $exists = $false }
if ($exists) { throw "Release $Tag already exists on GitHub" }

# Notes go through a file: Windows PowerShell splits a quoted argument with quotes inside it
$NotesFile = Join-Path $Root 'dist\release-notes.md'
[IO.File]::WriteAllText($NotesFile, $Body, (New-Object Text.UTF8Encoding $false))
& $Gh release create $Tag $Setup $Mac $Linux --target $Commit --title "TabloView $Version" --notes-file $NotesFile
if ($LASTEXITCODE -ne 0) { throw 'Creating the release failed' }
Write-Host "Released $Tag on GitHub: https://github.com/JoeDV/TabloView/releases/tag/$Tag" -ForegroundColor Green
