@echo off
setlocal
cd /d "%~dp0"
call "%CD%\scripts\python-run.cmd" -m creator_hub.portfolio.benchmark --profile small --json "%CD%\benchmarks\results\small.json" %*
