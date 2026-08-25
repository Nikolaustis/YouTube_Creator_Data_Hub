@echo off
setlocal
cd /d "%~dp0"

echo [1/5] Creating a consistent pre-upgrade SQLite backup when an existing database is present...
call "%~dp0scripts\python-run.cmd" "%~dp0scripts\pre_upgrade_backup.py"
if errorlevel 1 goto :fail

echo [2/5] Upgrading local SQLite schema and running registered migrations...
call "%~dp0scripts\python-run.cmd" "%~dp0hub.py" init
if errorlevel 1 goto :fail

echo [3/5] Running self-check...
call "%~dp0scripts\python-run.cmd" "%~dp0scripts\self_check.py"
if errorlevel 1 goto :fail

echo [4/5] Removing old Dashboard output...
if exist "%~dp0output\dashboard" rmdir /s /q "%~dp0output\dashboard"

echo [5/5] Rebuilding Dashboard...
call "%~dp0scripts\python-run.cmd" "%~dp0hub.py" dashboard
if errorlevel 1 goto :fail

echo Upgrade complete. Source version: 3.10.3. Existing data was migrated in place.
echo A pre-upgrade backup is kept under backups when an existing database was found.
echo Use start-dashboard.cmd for interactive mode.
exit /b 0

:fail
echo Upgrade failed. Review the error above.
echo If a pre-upgrade backup was created, keep it until the issue is resolved.
pause
exit /b 1
