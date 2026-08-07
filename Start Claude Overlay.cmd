@echo off
rem Launch Claude Overlay with no console window. Portable: finds pythonw/pyw on PATH.
cd /d "%~dp0"
setlocal enabledelayedexpansion

rem Check each candidate by RUNNING IT, then launch the exact binary that answered.
rem pythonw cannot print its own version -- it has no console -- but its exit code
rem still comes back, and that is all a check needs.
rem
rem v1.15.1 checked the python.exe sitting NEXT TO pythonw instead. That is a
rem different file, so the answer could be wrong in both directions: it passed on
rem machines where pythonw was a dead Store alias, and -- far worse -- it failed on
rem machines where python.exe was missing, blocked or non-zero for any reason at all,
rem turning a working install into a "no Python was found" wall. Never judge one
rem binary by another one's behaviour.
rem
rem Every probe goes through `call`, without exception. `where pythonw` can legitimately
rem return a .bat/.cmd shim -- pyenv-win and several conda wrappers install exactly that
rem -- and running a batch file from a batch file WITHOUT `call` transfers control and
rem never comes back. That would end this launcher mid-check: no window, no message,
rem nothing at all, which is the very symptom it exists to prevent.
set "PYW="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined PYW (call "%%i" -c "pass" >nul 2>nul && set "PYW=%%i")

rem A shim has to be started THROUGH cmd. `start "" "some.bat" "arg"` becomes
rem `cmd /K "some.bat" "arg"`, and cmd strips the outer quotes off a command that both
rem starts and ends with one -- so a shim whose path contains a space never runs at all
rem and leaves an idle console window sitting there instead of an overlay. Routing it as
rem `cmd /c call ...` keeps the quotes intact (the command no longer starts with one) and
rem closes the window when the app exits. Plain .exe paths are launched directly, exactly
rem as before, so the common case is untouched.
set "VIA="
if defined PYW if /i "!PYW:~-4!"==".bat" set "VIA=cmd /c call"
if defined PYW if /i "!PYW:~-4!"==".cmd" set "VIA=cmd /c call"
if defined PYW ( start "" !VIA! "!PYW!" "%~dp0claude_overlay.py" & exit /b )

rem Nothing named pythonw answered: try the py launcher's windowed twin, same way.
call pyw -3 -c "pass" >nul 2>nul && ( start "" pyw -3 "%~dp0claude_overlay.py" & exit /b )
call pyw -c "pass" >nul 2>nul && ( start "" pyw "%~dp0claude_overlay.py" & exit /b )

rem Nothing windowed answered. A plain python.exe leaves a console window sitting
rem behind the overlay, which is ugly -- and much better than nothing happening,
rem because now whatever goes wrong is visible instead of silent.
call python -c "pass" >nul 2>nul && ( start "" python "%~dp0claude_overlay.py" & exit /b )

rem Last resort: do what every release before 1.15.1 did and launch the first pythonw
rem on PATH without proving anything about it. A machine this launcher used to start
rem has to keep starting -- a wrong "no Python" wall is worse than the silent failure
rem the check was added to prevent. The one candidate never worth trying blind is the
rem App-execution-alias stub, which is the only case that check really existed for.
set "RAW="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined RAW set "RAW=%%i"
if not "!RAW!"=="!RAW:\WindowsApps\=!" set "RAW="
if defined RAW ( start "" "!RAW!" "%~dp0claude_overlay.py" & exit /b )

echo ============================================================
echo   [X] Could not start Claude Overlay: no Python on PATH ran.
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
echo   Fix: install Python 3.10+ from https://www.python.org/downloads/
echo        ^(tick "Add python.exe to PATH"^), then run setup.cmd.
echo.
echo   Already installed? Double-click Diagnose.cmd for the full report.
echo.
pause
