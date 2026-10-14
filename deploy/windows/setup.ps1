<#
Paste Guard on Windows 10/11, "accurate" profile.

  powershell -ExecutionPolicy Bypass -File deploy\windows\setup.ps1 [-InstallDir C:\paste-guard] [-PgProfile accurate] [-NoAutostart]

Needs no admin rights and never shows a UAC prompt: everything is per-user.

What it does:
  1. Finds Python 3.10+ (py launcher, PATH, or the per-user python.org install) and git
     (PATH or common install folders). If either is missing it stops with a download link;
     it never installs anything machine-wide. Tested on Windows 10 with Python 3.13.
  2. Clones github.com/sandeep-paluru/paste-guard into -InstallDir, or pulls if it is already there.
  3. Creates .venv and installs backend/requirements.txt.
  4. Builds the index (downloads the MiniLM model once, about 90 MB, into
     %LOCALAPPDATA%\paste-guard\models).
  5. Adds a "Paste Guard" shortcut to your Startup folder so the backend starts at logon on
     127.0.0.1:8765 (hidden), starts it now, and checks /health.
Nothing listens on the network: the server binds to 127.0.0.1 only. Uninstall with
  delete "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Paste Guard.lnk", stop the
  python.exe running uvicorn from -InstallDir\.venv, then delete -InstallDir.
Stop the server: Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  ? CommandLine -like '*uvicorn app:app*8765*' | % { Stop-Process -Id $_.ProcessId }
#>
param(
  [string]$InstallDir = "$env:USERPROFILE\paste-guard",
  [string]$PgProfile = "accurate",
  [string]$Repo = "https://github.com/sandeep-paluru/paste-guard.git",
  [int]$Threads = 4,
  [switch]$NoAutostart
)
$ErrorActionPreference = "Stop"
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }

Step "Checking Python and git"
$py = $null
$cands = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $cands += ,@("py", "-3") }
if (Get-Command python -ErrorAction SilentlyContinue) { $cands += ,@((Get-Command python).Source) }
$cands += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
  Sort-Object FullName -Descending | ForEach-Object { ,@($_.FullName) }
foreach ($c in $cands) {
  try {
    $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
    $v = & $exe @pre -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
    # The Microsoft Store stub prints nothing and exits non-zero, so it is skipped here.
    if ($LASTEXITCODE -eq 0 -and $v -and [version]$v -ge [version]"3.10") {
      $py = (& $exe @pre -c "import sys;print(sys.executable)").Trim(); break
    }
  } catch {}
}
if (-not $py) {
  throw "Python 3.10+ not found. Install it per-user (no admin) from https://www.python.org/downloads/windows/ (untick 'install for all users'), then rerun."
}
Write-Host "Python: $py"
$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) {
  $git = @("$env:ProgramFiles\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe", "D:\Git\cmd\git.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $git) { throw "git not found. Install Git for Windows (per-user is fine) from https://git-scm.com/download/win, then rerun." }
Write-Host "git: $git"

Step "Getting the code into $InstallDir"
if (Test-Path "$InstallDir\.git") { & $git -C $InstallDir pull --ff-only } else { & $git clone $Repo $InstallDir }
Set-Location $InstallDir
New-Item -ItemType Directory -Force (Join-Path $InstallDir "data") | Out-Null
# The demo "company repository" is a public open source project (pallets/itsdangerous) pinned to the
# commit the eval was built on. It is not committed to this repo, so fetch it here.
if (-not (Test-Path "demo\company-repo\.git")) {
  & $git clone -q https://github.com/pallets/itsdangerous demo\company-repo
  & $git -C demo\company-repo checkout -q 672971d66a2ef9f85151e53283113f33d642dabd
}

Step "Creating virtualenv and installing dependencies"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $py -m venv .venv }
$vpy = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $vpy -m pip install -q --upgrade pip
& $vpy -m pip install -q -r backend\requirements.txt

$env:PG_CONFIG = Join-Path $InstallDir "paste-guard.toml"
$env:PG_PROFILE = $PgProfile
$env:PG_THREADS = "$Threads"
$env:PG_MODEL_CACHE = Join-Path $env:LOCALAPPDATA "paste-guard\models"
New-Item -ItemType Directory -Force $env:PG_MODEL_CACHE | Out-Null

Step "Building the index for profile '$PgProfile' (first run downloads the model)"
Push-Location backend
& $vpy index.py reindex
Pop-Location

# Launcher used by the Startup shortcut (keeps the env vars with it).
$run = Join-Path $InstallDir "deploy\windows\run.cmd"
@"
@echo off
set PG_CONFIG=$env:PG_CONFIG
set PG_PROFILE=$PgProfile
set PG_THREADS=$Threads
set PG_MODEL_CACHE=$env:PG_MODEL_CACHE
cd /d "$InstallDir\backend"
"$vpy" -m uvicorn app:app --host 127.0.0.1 --port 8765 >> "$InstallDir\data\server.log" 2>&1
"@ | Set-Content -Encoding ASCII $run

# Per-user autostart via a Startup-folder shortcut (no admin, unlike some Scheduled Task setups).
if (-not $NoAutostart) {
  Step "Adding Startup shortcut 'Paste Guard' (starts hidden at logon, current user only)"
  $lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "Paste Guard.lnk"
  $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $sc.TargetPath = "cmd.exe"; $sc.Arguments = "/c `"$run`""; $sc.WorkingDirectory = "$InstallDir\backend"
  $sc.WindowStyle = 7; $sc.Save()
}
$running = $false
try { Invoke-RestMethod http://127.0.0.1:8765/health -TimeoutSec 2 | Out-Null; $running = $true } catch {}
if ($running) { Write-Warning "Something already answers on port 8765; not starting a second server." }
else { Start-Process -WindowStyle Hidden cmd.exe "/c `"$run`"" }

Step "Waiting for http://127.0.0.1:8765/health (model load can take 30 s)"
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
  try { $h = Invoke-RestMethod http://127.0.0.1:8765/health -TimeoutSec 3; $ok = $true; break } catch { Start-Sleep 2 }
}
if ($ok) {
  Write-Host "Paste Guard $($h.version) is up. Profile: $($h.profile). Model: $($h.model)" -ForegroundColor Green
  Write-Host "Next: chrome://extensions > Developer mode > Load unpacked > $InstallDir\extension"
  Write-Host "If the extension options point at the VM, set Backend URL to http://localhost:8765."
  Write-Host "Admin page: http://127.0.0.1:8765/admin   Log: $InstallDir\data\server.log"
} else {
  Write-Warning "Backend did not answer. See $InstallDir\data\server.log"
  exit 1
}
