@echo off
setlocal
cd /d "%~dp0"
echo === Dota Draft Assist setup ===

set "PYCMD="
where py >nul 2>&1
if not errorlevel 1 set "PYCMD=py -3"
if not defined PYCMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    echo Python 3.11+ not found. Install it from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add python.exe to PATH" in the installer, then
    echo run this Setup.bat again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYCMD% -m venv .venv || goto :fail
)

echo Installing dependencies - the first run can take a few minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-windows.txt || goto :fail

if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo Created .env - Notepad will open it now: replace the placeholder
    echo with your real Stratz API key and save.
    start notepad .env
)

echo.
echo Setup complete. Recommended order from here:
echo   1. "Capture Probe.bat"       (Dota running, confirm occluded capture)
echo   2. "Update Data.bat"         (download stats + portraits)
echo   3. "Tune Recognition.bat"    (train the recogniser, no Dota needed)
echo   4. "Start Draft Assist.bat"  (the app itself)
echo "Start Demo.bat" shows the app with a fake draft, no Dota needed.
pause
exit /b 0

:fail
echo.
echo Setup failed - see the error above.
pause
exit /b 1
