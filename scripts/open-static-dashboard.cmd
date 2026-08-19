@echo off
cd /d "%~dp0.."
if not exist "output\dashboard\index.html" call scripts\python-run.cmd hub.py dashboard
if errorlevel 1 exit /b %errorlevel%
start "" "%CD%\output\dashboard\index.html"
