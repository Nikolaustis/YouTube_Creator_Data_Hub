@echo off
setlocal
cd /d "%~dp0"
set "PYRUN=%CD%\scripts\python-run.cmd"

echo =============================================
echo YouTube Creator Data Hub - First Run Setup
echo =============================================
echo.
echo This setup does not delete an existing SQLite database.
echo.

call "%PYRUN%" --version
if errorlevel 1 goto :python_missing
call "%PYRUN%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  pause
  exit /b 1
)

echo.
echo [1/5] Installing Python dependencies...
call "%PYRUN%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [2/5] Initializing / upgrading the local SQLite schema...
call "%PYRUN%" hub.py init
if errorlevel 1 goto :fail

echo.
echo [3/5] Checking YouTube API Key...
for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY','User')"`) do set "USER_YT_KEY=%%K"
if defined USER_YT_KEY set "YOUTUBE_API_KEY=%USER_YT_KEY%"
if not defined USER_YT_KEY (
  echo No user-level YOUTUBE_API_KEY was found.
  choice /M "Configure the API Key now"
  if errorlevel 2 goto :doctor
  call scripts\set-api-key.cmd --no-pause
  if errorlevel 1 goto :fail
  for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY','User')"`) do set "USER_YT_KEY=%%K"
  if defined USER_YT_KEY set "YOUTUBE_API_KEY=%USER_YT_KEY%"
)

:doctor
echo.
echo [4/5] Running local environment diagnostics...
call "%PYRUN%" hub.py doctor
if errorlevel 1 goto :fail

echo.
echo [5/5] Building the initial Dashboard snapshot...
call "%PYRUN%" hub.py dashboard
if errorlevel 1 goto :fail

echo.
echo =============================================
echo Setup complete.
echo =============================================
echo Interactive mode: start-dashboard.cmd
 echo   Browser -^> http://127.0.0.1:8765/ -^> local Python -^> local SQLite
 echo   Search, database writes, full filtering and XLSX export are enabled.
echo Static mode: open-static-dashboard.cmd
 echo   Opens the generated HTML snapshot directly; no Python service is started.
echo Automatic monitoring is optional and can be installed from the menu below.
echo.


:menu
echo Next step:
echo   [1] Start interactive Dashboard
echo   [2] Open static Dashboard
echo   [3] Install / refresh automatic monitoring task
echo   [4] Validate YouTube API Key online
echo   [5] Configure optional AI Copilot
echo   [6] Exit setup
choice /C 123456 /N /M "Choose 1-6: "
if errorlevel 6 goto :done
if errorlevel 5 goto :ai
if errorlevel 4 goto :online
if errorlevel 3 goto :monitor
if errorlevel 2 goto :static
if errorlevel 1 goto :interactive

:interactive
start "" "%CD%\start-dashboard.cmd"
goto :done

:static
call "%CD%\open-static-dashboard.cmd"
echo.
goto :menu

:monitor
call "%CD%\scripts\install-sync-task.cmd" --no-pause
echo.
goto :menu

:ai
call "%CD%\setup-ai.cmd"
echo.
goto :menu

:online
for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY','User')"`) do set "USER_YT_KEY=%%K"
if defined USER_YT_KEY set "YOUTUBE_API_KEY=%USER_YT_KEY%"
call "%PYRUN%" hub.py doctor --online
echo.
pause
echo.
goto :menu

:python_missing
echo.
echo Python 3.10+ is required for the local interactive Dashboard.
echo Install it from python.org and enable "Add Python to PATH" during setup.
echo If the Windows Python Launcher ^(py.exe^) is installed, this Skill can use it automatically.
echo Then run setup.cmd again.
pause
exit /b 1

:fail
echo.
echo Setup failed. Review the error above, then run setup.cmd again.
pause
exit /b 1

:done
echo Setup finished. You can run setup.cmd again safely if you need to repair dependencies.
exit /b 0
