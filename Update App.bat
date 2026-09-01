@echo off
setlocal
cd /d "%~dp0"
echo === Updating Dota Draft Assist from GitHub ===

where git >nul 2>&1
if errorlevel 1 (
    echo Git is not installed or not on PATH. Either install it from
    echo https://git-scm.com/download/win  ^(default options are fine^),
    echo or update via GitHub Desktop's "Pull origin" button instead.
    pause
    exit /b 1
)

if not exist ".git" (
    echo This folder is not a git checkout ^(probably a ZIP download^), so it
    echo cannot pull updates. One-time fix - in a location you like, run:
    echo   git clone https://github.com/bijankle/Dota_Draft_Assist
    echo then copy your .env, captures\ and data_cache\ folders across and
    echo use the new folder from now on.
    pause
    exit /b 1
)

rem --autostash keeps your local edits (e.g. rules\items.yaml tweaks) safe:
rem they are set aside, the update applies, then they are put back on top.
git pull --rebase --autostash
if errorlevel 1 (
    echo.
    echo Update hit a conflict - most likely you and the repo both changed
    echo the same file. Nothing is lost; ask Claude with the message above.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    echo Refreshing dependencies...
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt -r requirements-windows.txt
)

echo.
echo Up to date.
pause
