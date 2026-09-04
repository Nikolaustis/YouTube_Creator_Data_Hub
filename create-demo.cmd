@echo off
setlocal
cd /d "%~dp0"
set "PYRUN=%CD%\scripts\python-run.cmd"

call "%PYRUN%" -m scripts.neutralize_public_surface --source-only
if errorlevel 1 exit /b 1
call "%PYRUN%" -m scripts.neutralize_discovery_surface --source-only
if errorlevel 1 exit /b 1
call "%PYRUN%" -m creator_hub.portfolio.demo --db "%CD%\data\demo_creator_hub.sqlite" --creators 100 --videos 3000 --output "%CD%\output\demo-dashboard" --build-dashboard
if errorlevel 1 exit /b 1
call "%PYRUN%" -m scripts.check_public_surface_neutrality
exit /b %errorlevel%
