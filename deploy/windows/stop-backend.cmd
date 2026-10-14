@echo off
rem Stops Paste Guard backends (python running "uvicorn app:app ... 8765") started by this user. No admin.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ? { $_.CommandLine -like '*uvicorn app:app*8765*' } | %% { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; if ('%1' -ne 'quiet') { Write-Host ('Stopped PID ' + $_.ProcessId) } }; Start-Sleep -Milliseconds 500"
