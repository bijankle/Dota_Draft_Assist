@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No environment yet - run Setup.bat first.
    pause
    exit /b 1
)
echo Listing visible windows so you can see what the app can capture.
echo.
".venv\Scripts\python.exe" tools\list_windows.py
pause
