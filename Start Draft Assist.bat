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
    echo If it says no dataset cache: run "Update Data.bat" first.
    echo If it says no portrait library: run "Update Data.bat" first.
    echo If it says no Dota window: start Dota in borderless windowed mode,
    echo or use "Start Demo.bat" to try the app without the game.
    pause
)
