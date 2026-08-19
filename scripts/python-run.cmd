@echo off
setlocal
where python >nul 2>&1
if errorlevel 1 goto :try_py
python --version >nul 2>&1
if errorlevel 1 goto :try_py
python %*
exit /b %errorlevel%

:try_py
where py >nul 2>&1
if errorlevel 1 goto :missing
py -3 --version >nul 2>&1
if errorlevel 1 goto :missing
py -3 %*
exit /b %errorlevel%

:missing
echo [ERROR] Python 3 was not found.
echo Install Python 3.10 or newer from python.org and enable "Add Python to PATH",
echo or install the Windows Python Launcher ^(py.exe^), then retry.
exit /b 9009
