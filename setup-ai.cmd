@echo off
setlocal
cd /d "%~dp0"
call "%CD%\scripts\python-run.cmd" scripts\ai_setup.py
exit /b %errorlevel%
