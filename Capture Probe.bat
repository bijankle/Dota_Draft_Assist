@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No environment yet - running Setup first.
    call Setup.bat
    if not exist ".venv\Scripts\python.exe" exit /b 1
)
echo Start Dota 2 in borderless windowed mode first, then cover its window
echo with any other window once frames start saving. Frames go to:
echo   %~dp0captures\probe\
echo.
".venv\Scripts\python.exe" tools\probe_capture.py
pause
