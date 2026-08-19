@echo off
cd /d "%~dp0.."
call scripts\python-run.cmd hub.py serve
if errorlevel 1 pause
