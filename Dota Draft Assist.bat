@echo off
setlocal
cd /d "%~dp0"
title Dota Draft Assist

rem One launcher. First run installs everything; later runs just start the
rem app. Updating the app, refreshing data, tuning recognition and choosing a
rem capture source are all menu items inside the application itself.

rem THE FILE THAT MAKES A FOLDER A VIRTUAL ENVIRONMENT IS pyvenv.cfg,
rem not pythonw.exe. This guard tested for the interpreter, which is
rem merely a copy that happens to sit in Scripts\ -- so a .venv whose
rem pyvenv.cfg had gone sailed straight past setup, launched the broken
rem exe, and produced "failed to locate pyvenv.cfg: The system cannot
rem find the file specified." in a dialog with no traceback behind it.
rem The launcher could never repair it and failed identically every
rem time, which is what "i cant open dota draft assist at all" was.
if not exist ".venv\Scripts\pythonw.exe" goto :firstrun
if exist ".venv\pyvenv.cfg" goto :launch

echo Repairing the Python environment...
echo .venv\pyvenv.cfg is missing, which is what Windows means by
echo "failed to locate pyvenv.cfg". Rebuilding it in place - your
echo settings, your key and the downloaded artwork are not touched.
echo.
goto :setup

:firstrun
echo First run - setting up. This takes a few minutes and happens once.
echo.

:setup
rem PYTHON IS THE ONE PREREQUISITE, AND "IS IT ON PATH" IS NOT THE
rem QUESTION. Two things that ARE on PATH are not a usable Python: the
rem Microsoft Store APP EXECUTION ALIAS, which ships enabled on Windows
rem and is a stub that opens the Store rather than running anything, and
rem an older Python somebody installed years ago. Both got past a bare
rem `where`, and both then failed inside `python -m venv` or half way
rem through pip, where the error names neither cause. So every candidate
rem is made to RUN and report its own version, and the floor is checked
rem here rather than left to a wheel to complain about later.
set "PYCMD="
set "PYTRIED="
call :findpython
if not defined PYCMD call :offerpython
if not defined PYCMD goto :nopython

rem EVERY STEP FROM HERE IS WRITTEN DOWN. A user answered Y to the pip
rem prompt, a step failed, and the message was gone before it could be
rem read - because the last act of this file is `start` followed by
rem `exit`, so cmd.exe closes the console the moment the app appears.
rem On the path where everything WORKED. The guards were fine; there
rem was simply no record. `setup_log.py` tees each step to the console
rem AND to debug\startup\<date>\, keeps the last three runs, and on a
rem failure puts the whole log on the clipboard.
%PYCMD% "tools\setup_log.py" start

echo Creating the Python environment...
%PYCMD% "tools\setup_log.py" run "create the environment" -- %PYCMD% -m venv .venv || goto :failed
echo.

rem PIP IS A PREREQUISITE TOO, AND IT TURNED A REAL USER AROUND. This was
rem one line -- `pip install --upgrade pip >nul` -- with three faults in
rem it. The redirect hid it, so minutes of downloading read as a frozen
rem window. There was no `|| goto :failed`, so an upgrade that failed
rem carried on SILENTLY with the old pip and died on the NEXT line, where
rem the message names neither pip nor the upgrade. And nobody was ever
rem asked. What that user saw was an error they did not read, "Press any
rem key to continue", and the window shutting: "it said press any key to
rem continue and then closed his window".
rem
rem AN OLD PIP IS THE COMMONEST WAY THIS STEP FAILS. It cannot read the
rem package files today's releases ship as, so it falls back to BUILDING
rem them from source, which then wants a C++ compiler nobody has -- and
rem the error that reaches the screen is about Visual C++ rather than
rem about pip.
rem IF PIP IS IN THE FOLDER THERE IS NOTHING TO ASK. This prompt exists
rem because the upgrade is a DOWNLOAD - and a copy unzipped from a
rem release already has pip in `wheels\`, so asking about it, and on a
rem miss pushing the user onto pypi.org, made this the one step that
rem reached for the internet inside a bundle whose whole point is that
rem it does not have to. Offline it is instant and cannot fail for any
rem reason worth a question, so it just happens.
set "PIPDONE="
if exist "wheels\pip-*.whl" (
    echo Updating pip from this folder - no download needed...
    %PYCMD% "tools\setup_log.py" run "update pip from the folder" -- ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels --upgrade pip && set "PIPDONE=1"
)
if defined PIPDONE echo.
if defined PIPDONE goto :deps

echo Setup needs an up-to-date pip. That is the installer Python uses to
echo fetch the packages this app needs, and an old one cannot read the
echo files today's packages ship as - it is the commonest reason setup
echo fails here.
echo.
echo This only changes the copy of pip inside this app's own folder.
echo Nothing else on your PC is touched.
echo.
choice /c YN /n /m "Update pip now? [Y]es or [N]o: "
echo.
if errorlevel 2 goto :pipkept
%PYCMD% "tools\setup_log.py" note "offered to update pip: answered YES"
echo Updating pip...
rem AND NOT `2>nul`. Hiding this one line is what left the last failure
rem unexplained: the offline attempt failed silently, the online one
rem took over, and nothing anywhere said the first had been tried.
%PYCMD% "tools\setup_log.py" run "update pip from pypi.org" -- ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :pipfailed
goto :deps

:pipkept
%PYCMD% "tools\setup_log.py" note "offered to update pip: answered NO"
echo Leaving pip as it is. If the next step fails, run this file again
echo and answer Y.
echo.
goto :deps

:pipfailed
echo.
echo pip could not be updated. That is almost always no internet, or a
echo network blocking pypi.org - the update is downloaded from there.
echo.
echo Setup can carry on with the pip you have, and it may well work.
echo.
choice /c YN /n /m "Carry on anyway? [Y]es or [N]o: "
echo.
rem THE JUMP COMES FIRST, because a command between `choice` and its
rem own `if errorlevel` overwrites the answer being tested - so
rem logging the refusal here would have read setup_log's exit code
rem instead of the keypress, and a user who said STOP would have
rem carried on regardless.
if errorlevel 2 goto :pipstop
rem THIS IS THE PATH THAT LOST THE LAST REPORT. Carrying on is usually
rem right and the app then starts, which closes the console - so the
rem failure leaves no trace at all unless it is written down here.
%PYCMD% "tools\setup_log.py" note "pip upgrade failed: chose to CARRY ON"

:deps
rem THE PACKAGES LIVE IN THIS FOLDER IF THEY CAN. About 190 MB of them,
rem downloaded once and kept in `wheels\` - so a repaired .venv costs
rem nothing, a second install is instant, and a copy of this folder
rem carries them to another PC with no download at all. A copy
rem unzipped from a release built by `tools/make_release.py` has
rem them ALREADY, for three Python versions, so this line is the
rem whole install. See
rem `tools/stock_wheels.py` for why they are NOT in the repository.
set "FROMFOLDER="
if exist "wheels\*.whl" (
    echo Installing the app's packages from this folder - no download...
    echo.
    %PYCMD% "tools\setup_log.py" run "install the packages from the folder" -- ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt -r requirements-windows.txt && set "FROMFOLDER=1"
)
if defined FROMFOLDER goto :installed

echo Downloading the app's packages - this takes a few minutes, and only
echo happens once: they are kept in this folder afterwards.
echo.
rem `pip download` FIRST, so the cache is stocked by the same bytes that
rem get installed rather than by a second trip. If it fails the install
rem below still reaches pypi.org, because `--find-links` without
rem `--no-index` means "prefer the folder", not "refuse the network".
%PYCMD% "tools\setup_log.py" run "download the packages" -- ".venv\Scripts\python.exe" -m pip download -r requirements.txt -r requirements-windows.txt --dest wheels
%PYCMD% "tools\setup_log.py" run "install the packages" -- ".venv\Scripts\python.exe" -m pip install --find-links wheels -r requirements.txt -r requirements-windows.txt || goto :failed

:installed

rem THE KEY IS THE APP'S JOB, not this script's. This used to copy
rem .env.example over and open it in Notepad, which meant a new user was
rem asked for a Stratz key twice: once by a text editor, before the app
rem had even opened, and again by the first-run wizard inside it. The
rem wizard is the better of the two -- it checks the key against Stratz
rem before accepting it, and takes the rank brackets in the same pass --
rem so this script now does nothing but build the environment and start
rem the app. The wizard writes .env itself when it needs to.

%PYCMD% "tools\setup_log.py" finish
echo.
echo Setup complete. Starting the application...
echo It will ask for a free Stratz API key and which ranks to use.
echo From now on open "Start Dota Draft Assist" in this folder instead of
echo this file - it opens the app without this black window flashing up.
echo.

rem THIS WINDOW IS THE ONE THAT FLASHES, AND NOTHING IN HERE CAN STOP IT.
rem cmd.exe creates a console for a batch file before its first line runs,
rem so by the time anything below could hide it, it is already on screen -
rem and on the installed path this script echoes nothing at all, which is
rem why it reads as a small blank box rather than as a script working.
rem The app writes "Start Dota Draft Assist.lnk" beside this file at every
rem start; that one runs pythonw.exe directly and has no console to show.
rem See `appicon.folder_link`. This launcher stays because it is what
rem BUILDS the environment that shortcut points into.
goto :launch

:findpython
rem Try the PY LAUNCHER first. It is a real program rather than an alias,
rem so it can never be the Store stub, and `-3` asks it for the newest
rem Python 3 it knows about whatever else is on PATH.
rem Redirect the Windows way, to nul. The Unix null device is not a path
rem cmd.exe knows, so it printed "The system cannot find the path
rem specified." before the setup had done anything -- which made a first
rem run look broken on exactly the machines this launcher exists for.
where py >nul 2>&1 && call :trypython py -3
if defined PYCMD exit /b 0
where python >nul 2>&1 && call :trypython python
if defined PYCMD exit /b 0
rem AN INSTALL THAT HAPPENS NOW IS INVISIBLE TO THIS WINDOW. A process is
rem given its PATH when it starts, so winget can install Python perfectly
rem and this script still cannot see it -- and telling somebody to run
rem the thing again, seconds after it said it had installed Python for
rem them, reads as the install having failed. These are where the
rem official installers put it, so the same run can carry on.
for %%D in ("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe"
            "%ProgramFiles%\Python313\python.exe"
            "%ProgramFiles%\Python312\python.exe"
            "%ProgramFiles%\Python311\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python311\python.exe") do (
    if not defined PYCMD if exist %%D call :trypython %%D
)
exit /b 0

:trypython
rem A CANDIDATE HAS TO RUN AND SAY WHAT IT IS. The Store alias answers
rem nothing useful and exits non-zero; an old Python answers and fails
rem the floor. Either way PYCMD is left unset and the next one is tried.
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYCMD=%*"
exit /b 0

:offerpython
rem WINGET IS MICROSOFT'S OWN AND IS ALREADY ON WINDOWS 10 AND 11, so on
rem most machines this is the whole install. NOTHING IS INSTALLED WITHOUT
rem BEING ASKED: the answer is one keypress, and N falls through to the
rem download link below rather than to nothing.
where winget >nul 2>&1 || exit /b 0
echo Python 3.11 or newer is required and was not found on this PC.
echo.
echo It can be installed for you now using winget, which is Microsoft's
echo own installer and is already part of Windows. Nothing outside the
echo Python install itself is changed.
echo.
choice /c YN /n /m "Install Python now? [Y]es or [N]o: "
if errorlevel 2 exit /b 0
set "PYTRIED=1"
echo.
echo Installing Python - this takes a couple of minutes...
winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements
echo.
call :findpython
exit /b 0

:nopython
echo.
echo Python 3.11 or newer is required and this PC has not got it.
echo.
if defined PYTRIED (
    echo Python was just installed, but THIS WINDOW cannot see it yet: a
    echo program is given its PATH when it starts, so it never picks up
    echo something installed while it is already running.
    echo.
    echo CLOSE THIS WINDOW AND RUN THIS FILE AGAIN. That is all that is
    echo left to do.
) else (
    echo Install it from:
    echo.
    echo     https://www.python.org/downloads/
    echo.
    echo On the installer's FIRST page tick "Add python.exe to PATH" --
    echo without it this window cannot find Python afterwards. Then run
    echo this file again.
)
echo.
pause
exit /b 1

:launch
start "" ".venv\Scripts\pythonw.exe" -m draft_assist.ui.app %*
exit /b 0

:pipstop
%PYCMD% "tools\setup_log.py" note "pip upgrade failed: chose to STOP"
goto :failed

:failed
if defined PYCMD %PYCMD% "tools\setup_log.py" finish --failed "setup"
rem THE LAST THING PRINTED IS THE THING TO DO. A user hit this, read
rem none of it, pressed a key and reported that the window had closed on
rem him -- so the advice sits directly above the prompt rather than at
rem the top of a page of text he has already scrolled past.
echo.
echo ------------------------------------------------------------------
echo Setup did not finish. The error is in the text above this line.
echo.
echo Two causes cover nearly all of it:
echo.
echo   * No internet, or a network blocking pypi.org - everything is
echo     downloaded from there and there is no offline route.
echo   * An old pip, which cannot read today's package files. Run this
echo     file again and answer Y when it offers to update pip.
echo.
echo The whole log is saved, and on your clipboard - paste it straight
echo into a message if you are reporting this.
echo.
echo Nothing outside this folder has been changed. RUN THIS FILE AGAIN
echo once the above is sorted - it picks up where it left off.
echo ------------------------------------------------------------------
echo.
pause
exit /b 1
