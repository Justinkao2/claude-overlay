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
set "PYW="
set "PY="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined PYW set "PYW=%%i"
if defined PYW (
  set "PY=!PYW:pythonw.exe=python.exe!"
  rem Verify with --version: a Win11 box without Python still has the Microsoft Store
  rem alias stub that `where` happily finds but that runs nothing.
  "!PY!" --version >nul 2>nul || set "PY="
)
if not defined PY ( py -3 --version >nul 2>nul && set "PY=py -3" )
if not defined PY ( python --version >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [X] No working Python was found on this machine.
  echo     That alone explains the crash: install Python 3.10+ from
  echo       https://www.python.org/downloads/
  echo     ^(tick "Add python.exe to PATH"^), then run setup.cmd.
  echo.
  pause & exit /b 1
)

set "REPORT=%TEMP%\claude-overlay-report.txt"
%PY% "%~dp0preflight.py" > "%REPORT%" 2>&1
type "%REPORT%"

rem Best-effort clipboard copy so the report can just be pasted into a message.
type "%REPORT%" | clip >nul 2>nul && echo (This report has been copied to your clipboard.)
echo.
echo Saved to: %REPORT%
echo.
pause
