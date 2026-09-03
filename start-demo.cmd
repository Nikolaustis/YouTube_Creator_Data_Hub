@echo off
setlocal
cd /d "%~dp0"
call "%CD%\scripts\python-run.cmd" "%CD%\hub.py" serve --db "%CD%\data\demo_creator_hub.sqlite" --output "%CD%\output\demo-dashboard" --host 127.0.0.1 --port 8765
