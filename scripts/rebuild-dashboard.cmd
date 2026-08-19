@echo off
cd /d "%~dp0.."
call scripts\python-run.cmd hub.py dashboard
if errorlevel 1 exit /b %errorlevel%
start "" "%CD%\output\dashboard\index.html"
