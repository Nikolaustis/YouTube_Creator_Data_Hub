@echo off
cd /d "%~dp0"
call scripts\python-run.cmd hub.py serve --host 127.0.0.1 --port 8765
if errorlevel 1 (
  echo.
  echo Interactive Dashboard failed to start.
  echo Run: scripts\python-run.cmd hub.py doctor
  pause
)
