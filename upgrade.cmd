@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] Removing legacy launcher filenames...
if exist "启动Dashboard.cmd" del /q "启动Dashboard.cmd"
if exist "打开只读Dashboard.cmd" del /q "打开只读Dashboard.cmd"

echo [2/3] Running self-check...
python scripts\self_check.py
if errorlevel 1 goto :fail

echo [3/3] Rebuilding Dashboard from clean output...
if exist "output\dashboard" rmdir /s /q "output\dashboard"
python hub.py dashboard
if errorlevel 1 goto :fail

echo Upgrade complete. Use start-dashboard.cmd for interactive mode.
exit /b 0

:fail
echo Upgrade failed. Review the error above.
pause
exit /b 1
