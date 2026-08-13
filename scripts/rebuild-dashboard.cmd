@echo off
cd /d "%~dp0.."
python hub.py dashboard
if errorlevel 1 exit /b %errorlevel%
start "" "%CD%\output\dashboard\index.html"
