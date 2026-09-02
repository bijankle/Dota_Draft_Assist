@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No environment yet - running Setup first.
    call Setup.bat
    if not exist ".venv\Scripts\python.exe" exit /b 1
)
".venv\Scripts\python.exe" -m draft_assist.ui.app
if errorlevel 1 (
    echo.
    echo The app exited with an error - read the message above.
    echo If it says no dataset cache or no portrait library: run "Update Data.bat".
    echo The app no longer exits when Dota is not running - it opens with no
    echo capture source, and you choose one in its Debug tab.
    echo "List Windows.bat" shows what is available to capture.
    echo "Start Demo.bat" runs the interface without the game.
    pause
)
