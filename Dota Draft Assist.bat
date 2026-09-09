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
rem Redirect the Windows way, to nul. The Unix null device is not a path
rem cmd.exe knows, so it printed "The system cannot find the path
rem specified." before the setup had done anything -- which made a first
rem run look broken on exactly the machines this launcher exists for.
rem Everything else in this file already redirected correctly; these two
rem lines were the only exceptions.
where py >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
    where python >nul 2>&1 && set "PYCMD=python"
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

rem THE KEY IS THE APP'S JOB, not this script's. This used to copy
rem .env.example over and open it in Notepad, which meant a new user was
rem asked for a Stratz key twice: once by a text editor, before the app
rem had even opened, and again by the first-run wizard inside it. The
rem wizard is the better of the two -- it checks the key against Stratz
rem before accepting it, and takes the rank brackets in the same pass --
rem so this script now does nothing but build the environment and start
rem the app. The wizard writes .env itself when it needs to.

echo.
echo Setup complete. Starting the application...
echo It will ask for a free Stratz API key and which ranks to use.
echo.

:launch
start "" ".venv\Scripts\pythonw.exe" -m draft_assist.ui.app %*
exit /b 0

:failed
echo.
echo Setup failed - the error above says why.
pause
exit /b 1
