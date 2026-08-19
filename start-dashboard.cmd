@echo off
cd /d "%~dp0"
call scripts\python-run.cmd hub.py serve
if errorlevel 1 (
  echo.
  echo Interactive Dashboard failed to start.
  echo Run: scripts\python-run.cmd hub.py doctor
  pause
)
