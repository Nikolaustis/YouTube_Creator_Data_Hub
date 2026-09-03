@echo off
setlocal
cd /d "%~dp0"
set "PYRUN=%CD%\scripts\python-run.cmd"
call "%PYRUN%" "%CD%\scripts\neutralize_public_surface.py" --source-only
if errorlevel 1 exit /b 1
call "%PYRUN%" -m creator_hub.portfolio.demo --db "%CD%\data\demo_creator_hub.sqlite" --creators 100 --videos 3000 --output "%CD%\output\demo-dashboard" --build-dashboard
exit /b %errorlevel%
