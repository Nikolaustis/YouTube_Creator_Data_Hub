@echo off
cd /d "%~dp0"
python hub.py serve
if errorlevel 1 pause
