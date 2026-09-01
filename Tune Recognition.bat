@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No environment yet - running Setup first.
    call Setup.bat
    if not exist ".venv\Scripts\python.exe" exit /b 1
)
echo Training the recogniser on synthetic draft screens - a few minutes.
echo Rerun this after "Update Data.bat" downloads new portraits or after
echo labeling harvested crops.
echo.
".venv\Scripts\python.exe" -m draft_assist.proving.tune
pause
