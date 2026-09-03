@echo off
setlocal
cd /d "%~dp0"
set "PYRUN=%CD%\scripts\python-run.cmd"

echo Installing demo/runtime dependencies...
call "%PYRUN%" -m pip install -r "%CD%\requirements.txt"
if errorlevel 1 goto :fail

echo Applying source-only neutral public-surface migration...
call "%PYRUN%" "%CD%\scripts\neutralize_public_surface.py" --source-only
if errorlevel 1 goto :fail

echo Creating deterministic synthetic demo dataset...
call "%PYRUN%" -m creator_hub.portfolio.demo --db "%CD%\data\demo_creator_hub.sqlite" --creators 100 --videos 3000 --output "%CD%\output\demo-dashboard" --build-dashboard
if errorlevel 1 goto :fail

echo Validating neutral demo surface...
call "%PYRUN%" -m scripts.check_public_surface_neutrality
if errorlevel 1 goto :fail

echo Demo setup complete.
echo Run start-demo.cmd to open the synthetic Dashboard.
exit /b 0

:fail
echo Demo setup failed.
pause
exit /b 1
