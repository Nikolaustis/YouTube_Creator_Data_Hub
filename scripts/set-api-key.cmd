@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set-api-key.ps1"
if errorlevel 1 exit /b 1
echo.
echo API Key has been saved to the Windows user environment variable YOUTUBE_API_KEY.
echo New terminals and start-dashboard.cmd will read it automatically.
if /I not "%~1"=="--no-pause" pause
exit /b 0
