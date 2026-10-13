<#
Paste Guard on Windows 10/11, "accurate" profile.

  powershell -ExecutionPolicy Bypass -File deploy\windows\setup.ps1 [-InstallDir C:\paste-guard] [-PgProfile accurate] [-NoTask]

What it does:
  1. Checks for Python 3.10+ (installs Python 3.12 with winget if missing) and git.
  2. Clones github.com/sandeep-paluru/paste-guard into -InstallDir, or pulls if it is already there.
  3. Creates .venv and installs backend/requirements.txt.
  4. Builds the index for the chosen profile (downloads the embedding model once into
     %LOCALAPPDATA%\paste-guard\models; the accurate profile model is about 1.3 GB).
  5. Registers a per-user Scheduled Task "Paste Guard" that starts the backend at logon on
     127.0.0.1:8765, starts it now, and checks /health.
Nothing listens on the network: the server binds to 127.0.0.1 only. Uninstall with
  Unregister-ScheduledTask -TaskName "Paste Guard" -Confirm:$false ; then delete -InstallDir.
#>
param(
  [string]$InstallDir = "$env:USERPROFILE\paste-guard",
  [string]$PgProfile = "accurate",
  [string]$Repo = "https://github.com/sandeep-paluru/paste-guard.git",
  [int]$Threads = 4,
  [switch]$NoTask
)
$ErrorActionPreference = "Stop"
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }

Step "Checking Python and git"
$py = $null
foreach ($c in @("py -3", "python")) {
  try {
    $v = & cmd /c "$c -c ""import sys;print('%d.%d'%sys.version_info[:2])""" 2>$null
    if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { $py = $c; break }
  } catch {}
}
if (-not $py) {
  Step "Installing Python 3.12 with winget"
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
  $py = "py -3"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Step "Installing git with winget"
  winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + $env:Path
}

Step "Getting the code into $InstallDir"
if (Test-Path "$InstallDir\.git") { git -C $InstallDir pull --ff-only } else { git clone $Repo $InstallDir }
Set-Location $InstallDir
New-Item -ItemType Directory -Force (Join-Path $InstallDir "data") | Out-Null
# The demo "company repository" is a public open source project (pallets/itsdangerous) pinned to the
# commit the eval was built on. It is not committed to this repo, so fetch it here.
if (-not (Test-Path "demo\company-repo\.git")) {
  git clone -q https://github.com/pallets/itsdangerous demo\company-repo
  git -C demo\company-repo checkout -q 672971d66a2ef9f85151e53283113f33d642dabd
}

Step "Creating virtualenv and installing dependencies"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & cmd /c "$py -m venv .venv" }
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

# Launcher used by the scheduled task (keeps the env vars with the task).
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

if (-not $NoTask) {
  Step "Registering Scheduled Task 'Paste Guard' (runs at logon, current user)"
  $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$run`""
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName "Paste Guard" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName "Paste Guard"
} else {
  Start-Process -WindowStyle Hidden cmd.exe "/c `"$run`""
}

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
