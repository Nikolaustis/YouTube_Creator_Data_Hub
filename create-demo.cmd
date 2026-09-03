@echo off
setlocal
cd /d "%~dp0"
call "%CD%\scripts\python-run.cmd" -m creator_hub.portfolio.demo --db "%CD%\data\demo_creator_hub.sqlite" --creators 100 --videos 3000 --output "%CD%\output\demo-dashboard" --build-dashboard
