@echo off
setlocal
cd /d "%~dp0"

echo [1/6] Creating a consistent pre-upgrade SQLite backup when an existing database is present...
call "%~dp0scripts\python-run.cmd" "%~dp0scripts\pre_upgrade_backup.py"
if errorlevel 1 goto :fail

echo [2/6] Applying V3.10.6 fixed Rule workspace update...
call "%~dp0scripts\python-run.cmd" "%~dp0apply_v3_10_6.py"
if errorlevel 1 goto :fail

echo [3/6] Upgrading local SQLite schema...
call "%~dp0scripts\python-run.cmd" "%~dp0hub.py" init
if errorlevel 1 goto :fail

echo [4/6] Running self-check...
call "%~dp0scripts\python-run.cmd" "%~dp0scripts\self_check.py"
if errorlevel 1 goto :fail

echo [5/6] Removing old Dashboard output...
if exist "%~dp0output\dashboard" rmdir /s /q "%~dp0output\dashboard"

echo [6/6] Rebuilding Dashboard...
call "%~dp0scripts\python-run.cmd" "%~dp0hub.py" dashboard
if errorlevel 1 goto :fail

echo Upgrade complete. V3.10.6 is ready.
echo Existing SQLite data was preserved.
echo Use start-dashboard.cmd for interactive mode.
exit /b 0

:fail
echo Upgrade failed. Review the error above.
pause
exit /b 1
