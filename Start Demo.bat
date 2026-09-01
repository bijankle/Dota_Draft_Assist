@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No environment yet - running Setup first.
    call Setup.bat
    if not exist ".venv\Scripts\python.exe" exit /b 1
)
".venv\Scripts\python.exe" -m draft_assist.ui.app --demo
if errorlevel 1 pause
