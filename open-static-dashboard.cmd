@echo off
cd /d "%~dp0"
if not exist "output\dashboard\index.html" python hub.py dashboard
start "" "%CD%\output\dashboard\index.html"
