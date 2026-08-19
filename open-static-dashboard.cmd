@echo off
cd /d "%~dp0"
if not exist "output\dashboard\index.html" (
  call scripts\python-run.cmd hub.py dashboard
  if errorlevel 1 (
    echo Failed to build the static Dashboard.
    pause
    exit /b 1
  )
)
start "" "%CD%\output\dashboard\index.html"
