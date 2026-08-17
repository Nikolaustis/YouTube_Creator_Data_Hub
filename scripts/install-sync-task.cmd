@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install-daily-sync-task.ps1"
if errorlevel 1 (
  echo Failed to install monitoring schedule.
  pause
  exit /b 1
)
echo Monitoring schedule installed. The task runs every 6 hours; due creators are selected by priority cadence.
pause
