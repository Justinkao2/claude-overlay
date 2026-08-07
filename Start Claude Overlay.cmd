@echo off
rem Launch Claude Overlay with no console window. Portable: finds a Python that runs.
cd /d "%~dp0"
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------------------------
rem Find a Python by RUNNING candidates -- never by inspecting a different file, and
rem never by assuming PATH is the whole world.
rem
rem v1.15.1 checked the python.exe sitting NEXT TO pythonw. That is a different binary,
rem so the answer could be wrong in both directions, and it turned working installs into
rem a "no Python was found" wall.
rem
rem v1.15.2 fixed that but still only looked at PATH. setup.cmd does not: it installs
rem Python into %LOCALAPPDATA%\Programs\Python\Python3xx\ and then locates it by SCANNING
rem that folder, precisely because the PATH inside its own window is stale. So "setup.cmd
rem printed [OK] The app loads." and "PATH has a Python" are two different claims, and a
rem machine can satisfy the first while failing the second forever -- setup succeeds, the
rem launcher walls, and nothing on screen connects the two. Whatever setup.cmd is willing
rem to install into, this launcher has to be willing to look in.
rem
rem Every probe goes through `call`, without exception. `where pythonw` can legitimately
rem return a .bat/.cmd shim -- pyenv-win and several conda wrappers install exactly that
rem -- and running a batch file from a batch file WITHOUT `call` transfers control and
rem never comes back. That would end this launcher mid-check: no window, no message,
rem nothing at all, which is the very symptom it exists to prevent.
rem ---------------------------------------------------------------------------------

rem ---- BEGIN find-pythonw (kept identical in Diagnose.cmd and update.cmd) ----
set "PYW="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined PYW (call "%%i" -c "pass" >nul 2>nul && set "PYW=%%i")
if not defined PYW for /f "delims=" %%p in ('dir /b /s /a-d /o-n "%LOCALAPPDATA%\Programs\Python\pythonw.exe" 2^>nul') do if not defined PYW (call "%%p" -c "pass" >nul 2>nul && set "PYW=%%p")
if not defined PYW for /d %%d in ("%ProgramFiles%\Python3*") do if not defined PYW (call "%%d\pythonw.exe" -c "pass" >nul 2>nul && set "PYW=%%d\pythonw.exe")
if not defined PYW for /d %%d in ("%SystemDrive%\Python3*") do if not defined PYW (call "%%d\pythonw.exe" -c "pass" >nul 2>nul && set "PYW=%%d\pythonw.exe")
rem ---- END find-pythonw ----

if defined PYW goto launch

rem Nothing named pythonw answered: try the py launcher's windowed twin, same way.
call pyw -3 -c "pass" >nul 2>nul && ( start "" pyw -3 "%~dp0claude_overlay.py" & exit /b )
call pyw -c "pass" >nul 2>nul && ( start "" pyw "%~dp0claude_overlay.py" & exit /b )

rem Nothing windowed answered. A plain python.exe leaves a console window sitting
rem behind the overlay, which is ugly -- and much better than nothing happening,
rem because now whatever goes wrong is visible instead of silent.
call python -c "pass" >nul 2>nul && ( start "" python "%~dp0claude_overlay.py" & exit /b )
if not defined PYW for /f "delims=" %%p in ('dir /b /s /a-d /o-n "%LOCALAPPDATA%\Programs\Python\python.exe" 2^>nul') do if not defined PYW (call "%%p" -c "pass" >nul 2>nul && set "PYW=%%p")
if defined PYW goto launch

rem Last resort: do what every release before 1.15.1 did and launch the first pythonw
rem on PATH without proving anything about it. A machine this launcher used to start
rem has to keep starting -- a wrong "no Python" wall is worse than the silent failure
rem the check was added to prevent. The one candidate never worth trying blind is the
rem App-execution-alias stub, which is the only case that check really existed for.
set "RAW="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined RAW set "RAW=%%i"
if not "!RAW!"=="!RAW:\WindowsApps\=!" set "RAW="
if defined RAW ( start "" "!RAW!" "%~dp0claude_overlay.py" & exit /b )
goto nopython

:launch
rem A shim has to be started THROUGH cmd. `start "" "some.bat" "arg"` becomes
rem `cmd /K "some.bat" "arg"`, and cmd strips the outer quotes off a command that both
rem starts and ends with one -- so a shim whose path contains a space never runs at all
rem and leaves an idle console window sitting there instead of an overlay. Routing it as
rem `cmd /c call ...` keeps the quotes intact (the command no longer starts with one) and
rem closes the window when the app exits. Plain .exe paths are launched directly, exactly
rem as before, so the common case is untouched.
set "VIA="
if /i "!PYW:~-4!"==".bat" set "VIA=cmd /c call"
if /i "!PYW:~-4!"==".cmd" set "VIA=cmd /c call"
start "" !VIA! "!PYW!" "%~dp0claude_overlay.py"
exit /b

:nopython
echo ============================================================
echo   [X] Could not start Claude Overlay: no Python would run.
echo ============================================================
echo.
echo   What this machine actually has ^(please send this^):
echo.
echo   where pythonw
where pythonw 2>nul || echo     ^(nothing found^)
echo   where python
where python 2>nul || echo     ^(nothing found^)
echo   where py
where py 2>nul || echo     ^(nothing found^)
echo.
rem Also report the folders setup.cmd installs into, which is the one thing the PATH
rem listing above cannot tell you: "no Python on PATH" and "no Python on this PC" are
rem different problems with different fixes, and only this line separates them.
echo   Python found OFF PATH ^(the folders setup.cmd installs into^)
set "OFFP=%TEMP%\_ov_offpath.txt"
( dir /b /s /a-d "%LOCALAPPDATA%\Programs\Python\python*.exe" & dir /b /ad "%ProgramFiles%\Python3*" & dir /b /ad "%SystemDrive%\Python3*" ) > "%OFFP%" 2>nul
for %%f in ("%OFFP%") do if %%~zf==0 echo     ^(nothing found^)
type "%OFFP%" 2>nul
del "%OFFP%" >nul 2>nul
echo.
echo   If every path above is under \WindowsApps\, this PC has no Python at all:
echo   those are Windows placeholders, not an install. Running one only prints
echo   "Python was not found..." and stops.
echo.
echo   Fix: double-click setup.cmd. It installs Python for you when it is missing
echo        ^(per-user, no admin needed^) and finishes the rest in the same run.
echo        Manual alternative: https://www.python.org/downloads/
echo        ^(tick "Add python.exe to PATH"^), then run setup.cmd.
echo.
pause
