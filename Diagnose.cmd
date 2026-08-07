@echo off
rem Print one readable report explaining why Claude Overlay won't start, and put a copy
rem on the clipboard so it can be pasted straight into a message.
rem
rem This exists because the overlay runs under pythonw, which has no console: when it
rem fails to launch you see nothing at all. Double-click this, send the output.
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo   Claude Overlay - diagnose
echo ============================================================
echo.

rem --- Resolve the SAME interpreter the launcher uses ---------------------------
rem "Start Claude Overlay.cmd" runs `pythonw` from PATH, so that is the Python whose
rem packages matter. Reporting on any other one is how "but I installed it!" happens.
rem Candidates are checked by RUNNING them, in the launcher's own order. pythonw has
rem no console so it cannot print a version, but its exit code comes back -- and a
rem redirected `>` still reaches the file, which is why the report below works even
rem when pythonw is the only interpreter this machine has.
rem Every probe goes through `call`: `where` can return a .bat/.cmd shim (pyenv-win and
rem some conda wrappers install one), and running a batch file from a batch file without
rem `call` transfers control and never returns -- which would end this script mid-check.
set "PY="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined PY (call "%%i" -c "pass" >nul 2>nul && set PY="%%i")
if not defined PY ( call pyw -3 -c "pass" >nul 2>nul && set "PY=pyw -3" )
if not defined PY ( call python -c "pass" >nul 2>nul && set "PY=python" )
if not defined PY ( call py -3 -c "pass" >nul 2>nul && set "PY=py -3" )
if not defined PY (
  echo [X] Nothing on PATH would run Python. That alone explains the failure.
  echo.
  echo     This is what the machine actually has:
  echo     where pythonw
  where pythonw 2>nul || echo         ^(nothing found^)
  echo     where python
  where python 2>nul || echo         ^(nothing found^)
  echo     where py
  where py 2>nul || echo         ^(nothing found^)
  echo.
  echo     Install Python 3.10+ from https://www.python.org/downloads/
  echo     ^(tick "Add python.exe to PATH"^), then run setup.cmd.
  echo.
  pause & exit /b 1
)
echo Interpreter the launcher resolves to: !PY!
echo.

set "REPORT=%TEMP%\claude-overlay-report.txt"
call !PY! "%~dp0preflight.py" > "%REPORT%" 2>&1
type "%REPORT%"

rem Best-effort clipboard copy so the report can just be pasted into a message.
type "%REPORT%" | clip >nul 2>nul && echo (This report has been copied to your clipboard.)
echo.
echo Saved to: %REPORT%
echo.
pause
