# Paste Guard on Windows

Runs the backend on a Windows 10 or 11 PC with the `accurate` profile (MiniLM OR 3-gram OR TF-IDF).

Needs: Windows 10/11, about 1 GB free disk, about 400 MB RAM while running, internet for the first run only
(Python packages and the 90 MB model). Python 3.10+ and git are installed with winget if missing.

```powershell
# from any folder, in a normal (not admin) PowerShell
iwr https://raw.githubusercontent.com/sandeep-paluru/paste-guard/main/deploy/windows/setup.ps1 -OutFile setup.ps1
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Options: `-InstallDir C:\paste-guard`, `-PgProfile default`, `-Threads 4`, `-NoTask` (start once, no logon task).

The script clones the repo, creates `.venv`, installs dependencies, builds the index, registers a per-user
Scheduled Task "Paste Guard" that starts the backend at logon on `127.0.0.1:8765`, and checks `/health`.
Then load `extension\` in `chrome://extensions` (Developer mode, Load unpacked). If the extension was pointed
at the VM, set the backend URL on its options page to `http://localhost:8765`.

Stop or remove: `Stop-ScheduledTask "Paste Guard"`, `Unregister-ScheduledTask "Paste Guard" -Confirm:$false`.
Log: `data\server.log`. Admin page: http://127.0.0.1:8765/admin
