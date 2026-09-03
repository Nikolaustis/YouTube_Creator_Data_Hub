@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Creating a consistent pre-upgrade SQLite backup...
call "%~dp0scripts\python-run.cmd" "%~dp0scripts\pre_upgrade_backup.py"
if errorlevel 1 goto :fail

echo [2/4] Applying Creator Intelligence Hub V4.0.2 localhost fix...
call "%~dp0scripts\python-run.cmd" "%~dp0apply_upgrade.py"
if errorlevel 1 goto :fail

echo [3/4] Running self-check...
call "%~dp0scripts\python-run.cmd" "%~dp0scripts\self_check.py"
if errorlevel 1 goto :fail

echo [4/4] Rebuilding Dashboard with cached builder...
call "%~dp0scripts\python-run.cmd" "%~dp0hub.py" dashboard
if errorlevel 1 goto :fail

echo Upgrade complete. Creator Intelligence Hub V4.0.2 is ready.
echo Start with start-dashboard.cmd. Local URL: http://127.0.0.1:8765/
exit /b 0

:fail
echo Upgrade failed. Review the error above.
echo A pre-upgrade SQLite backup is retained under backups.
pause
exit /b 1
