@echo off
setlocal
cd /d "%~dp0"
title Dota Draft Assist

rem One launcher. First run installs everything; later runs just start the
rem app. Updating the app, refreshing data, tuning recognition and choosing a
rem capture source are all menu items inside the application itself.

if exist ".venv\Scripts\pythonw.exe" goto :launch

echo First run - setting up. This takes a few minutes and happens once.
echo.

set "PYCMD="
where py >/dev/null 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
    where python >/dev/null 2>&1 && set "PYCMD=python"
)
if not defined PYCMD (
    echo Python 3.11 or newer is required but was not found.
    echo Install it from https://www.python.org/downloads/ and be sure to
    echo tick "Add python.exe to PATH", then run this again.
    echo.
    pause
    exit /b 1
)

echo Creating the Python environment...
%PYCMD% -m venv .venv || goto :failed
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-windows.txt || goto :failed

if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo Paste your Stratz API key into the file that just opened, then save
    echo and close it. Get a free key at https://stratz.com/api
    start /wait notepad .env
)

echo.
echo Setup complete. Starting the application...
echo In the app: Data - Update statistics and portraits, to fetch data.
echo.

:launch
start "" ".venv\Scripts\pythonw.exe" -m draft_assist.ui.app %*
exit /b 0

:failed
echo.
echo Setup failed - the error above says why.
pause
exit /b 1
