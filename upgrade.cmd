@echo off
setlocal
cd /d "%~dp0"
set "PYRUN=%CD%\scripts\python-run.cmd"

echo [1/5] Creating a consistent pre-upgrade SQLite backup...
call "%PYRUN%" "%CD%\scripts\pre_upgrade_backup.py"
if errorlevel 1 goto :fail

echo [2/5] Installing runtime and engineering dependencies...
call "%PYRUN%" -m pip install -r "%CD%\requirements.txt"
if errorlevel 1 goto :fail
call "%PYRUN%" -m pip install -r "%CD%\requirements-dev.txt"
if errorlevel 1 goto :fail

echo [3/5] Applying neutral public-surface migration...
call "%PYRUN%" "%CD%\apply_upgrade.py"
if errorlevel 1 goto :fail

echo [4/5] Running engineering, portability and neutral-surface checks...
call "%PYRUN%" -m pytest -q "%CD%\tests"
if errorlevel 1 goto :fail
call "%PYRUN%" "%CD%\scripts\check_core_portability.py"
if errorlevel 1 goto :fail
call "%PYRUN%" "%CD%\scripts\check_public_surface_neutrality.py"
if errorlevel 1 goto :fail

echo [5/5] Rebuilding Dashboard...
call "%PYRUN%" "%CD%\hub.py" dashboard
if errorlevel 1 goto :fail

echo Upgrade complete. Creator Intelligence Hub 4.2.0 is ready.
echo Default Dashboard surface is domain-neutral.
echo If Dashboard was already running, close it and run start-dashboard.cmd again.
echo Dashboard: http://127.0.0.1:8765/
echo Typed API: start-api.cmd ^> http://127.0.0.1:8766/docs
exit /b 0

:fail
echo Upgrade failed. Review the error above.
echo The pre-upgrade SQLite backup is retained under backups.
pause
exit /b 1
