@echo off
setlocal
cd /d "%~dp0.."
call "%CD%\scripts\python-run.cmd" scripts\ai_setup.py --key-only
if /I not "%~1"=="--no-pause" pause
exit /b %errorlevel%
