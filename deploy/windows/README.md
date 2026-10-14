# Paste Guard on Windows

Runs the backend on a Windows 10 or 11 PC with the `accurate` profile (MiniLM OR 3-gram OR TF-IDF, two-step fast path on).
Tested on Windows 10 with Python 3.13.7 (fastembed, sqlite-vec and scikit-learn all install as wheels).

Needs: Windows 10/11, Python 3.10+ and git already installed (per-user installs are fine), about 1 GB free disk,
about 400 MB RAM while running, internet for the first run only (Python packages and the 90 MB model).
**No admin rights, no UAC prompt, no services, no firewall changes.** The server binds to 127.0.0.1 only.

```powershell
# from any folder, in a normal (not admin) PowerShell
iwr https://raw.githubusercontent.com/sandeep-paluru/paste-guard/main/deploy/windows/setup.ps1 -OutFile setup.ps1
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Options: `-InstallDir C:\paste-guard`, `-PgProfile fast`, `-Threads 4`, `-NoAutostart` (start once, no Startup shortcut).

The script clones the repo, creates `.venv`, installs dependencies, fetches the demo company repo
(pallets/itsdangerous at the pinned commit), builds the index, writes `deploy\windows\run.cmd`, adds a
"Paste Guard" shortcut to your Startup folder so the backend starts hidden at logon on `127.0.0.1:8765`,
starts it now, and checks `/health`. If Python or git is missing it stops with a download link instead of installing.

Then load `extension\` in `chrome://extensions` (Developer mode, Load unpacked). If the extension was pointed
at the VM, set the backend URL on its options page to `http://localhost:8765`.

Stop the server:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -like '*uvicorn app:app*8765*' | % { Stop-Process -Id $_.ProcessId }
```
Start it again: double-click `deploy\windows\run.cmd` (or log off and on). Remove autostart: delete
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Paste Guard.lnk`.
Log: `data\server.log`. Admin page: http://127.0.0.1:8765/admin. Latency: `.venv\Scripts\python eval\http_latency.py`.
