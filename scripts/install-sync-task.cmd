@echo off
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install-daily-sync-task.ps1"
if errorlevel 1 (
  echo Failed to install monitoring schedule.
  if /I not "%~1"=="--no-pause" pause
  exit /b 1
)
echo Monitoring schedule installed. The task runs every 6 hours; due creators are selected by priority cadence.
if /I not "%~1"=="--no-pause" pause
exit /b 0
