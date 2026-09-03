@echo off
setlocal
cd /d "%~dp0"
set "PYRUN=%CD%\scripts\python-run.cmd"

echo [1/6] Creating a consistent pre-upgrade SQLite backup...
call "%PYRUN%" "%CD%\scripts\pre_upgrade_backup.py"
if errorlevel 1 goto :fail

echo [2/6] Installing runtime dependencies...
call "%PYRUN%" -m pip install -r "%CD%\requirements.txt"
if errorlevel 1 goto :fail

echo [3/6] Applying engineering overlay and schema-safe cleanup...
call "%PYRUN%" "%CD%\apply_upgrade.py"
if errorlevel 1 goto :fail

echo [4/6] Running existing release self-check...
call "%PYRUN%" "%CD%\scripts\self_check.py"
if errorlevel 1 goto :fail

echo [5/6] Running focused engineering tests...
call "%PYRUN%" -m pip install -r "%CD%\requirements-dev.txt"
if errorlevel 1 goto :fail
call "%PYRUN%" -m pytest -q "%CD%\tests"
if errorlevel 1 goto :fail
call "%PYRUN%" "%CD%\scripts\check_core_portability.py"
if errorlevel 1 goto :fail

echo [6/6] Rebuilding Dashboard...
call "%PYRUN%" "%CD%\hub.py" dashboard
if errorlevel 1 goto :fail

echo Upgrade complete. Creator Intelligence Hub 4.1.0 is ready.
echo Dashboard: http://127.0.0.1:8765/
echo Typed API: start-api.cmd ^> http://127.0.0.1:8766/docs
exit /b 0

:fail
echo Upgrade failed. Review the error above.
echo The pre-upgrade SQLite backup is retained under backups.
pause
exit /b 1
