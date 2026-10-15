@echo off
rem Paste Guard backend in a visible console: one line per check (verdict, scores, latency, text hash).
rem Stops any Paste Guard backend already on port 8765 first (your own user only, no admin), then starts.
title Paste Guard backend (live log)
set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
call "%~dp0stop-backend.cmd" quiet
set "PG_CONFIG=%ROOT%\paste-guard.toml"
if not defined PG_PROFILE set PG_PROFILE=accurate
if not defined PG_THREADS set PG_THREADS=4
if not defined PG_MODEL_CACHE set "PG_MODEL_CACHE=%LOCALAPPDATA%\paste-guard\models"
set PYTHONUNBUFFERED=1
cd /d "%ROOT%\backend"
echo Paste Guard from %ROOT%
echo Live log page: http://127.0.0.1:8765/logs     Close this window or press Ctrl+C to stop.
echo.
"%ROOT%\.venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8765 --no-access-log
echo.
echo Backend stopped.
pause
