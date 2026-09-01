@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No environment yet - running Setup first.
    call Setup.bat
    if not exist ".venv\Scripts\python.exe" exit /b 1
)
echo === Pulling match statistics (OpenDota + Stratz) ===
".venv\Scripts\python.exe" tools\pull_data.py || goto :fail
echo.
echo === Downloading hero portraits and building the hash library ===
".venv\Scripts\python.exe" tools\build_library.py || goto :fail
echo.
echo Data update complete. Run this roughly once a day / after patches.
pause
exit /b 0

:fail
echo.
echo Update failed - read the error above. A SchemaError means an API
echo changed shape; the raw responses are in data_cache\raw\ for inspection.
pause
exit /b 1
