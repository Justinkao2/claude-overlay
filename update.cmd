@echo off
rem Update Claude Overlay to the latest version (git pull + refresh packages).
cd /d "%~dp0"
setlocal enabledelayedexpansion
echo ============================================================
echo   Claude Overlay - update
echo ============================================================
echo.

rem --- needs git + a clone to pull into ---
where git >nul 2>nul
if errorlevel 1 (
  echo [X] git not found. You probably installed via the ZIP download.
  echo     Re-download the latest ZIP from the green "Code" button at
  echo       https://github.com/shengyanlin/claude-overlay
  echo     and unzip ALL of it over this folder, replacing every file.
  echo     The app is a folder of modules, not a single script - replacing
  echo     only claude_overlay.py leaves it unable to start.
  pause & exit /b 1
)
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo [X] This folder isn't a git clone, so there's nothing to pull.
  echo     Re-download the latest ZIP from
  echo       https://github.com/shengyanlin/claude-overlay
  echo     and unzip ALL of it over this folder, replacing every file.
  pause & exit /b 1
)

echo Pulling the latest code...
git pull
if errorlevel 1 (
  echo [X] git pull failed ^(see above^). If you edited files locally, stash or
  echo     revert them first, then re-run update.cmd.
  pause & exit /b 1
)

rem --- refresh Python packages ------------------------------------------------
rem Into the interpreter the LAUNCHER uses, not whichever one `py -3` happens to pick.
rem "Start Claude Overlay.cmd" runs `pythonw` from PATH; on a machine with two Pythons
rem (a common one: python.org plus the Microsoft Store build) upgrading the wrong one
rem leaves the app running against packages nobody refreshed - and the symptom of that
rem is a launch that silently does nothing.
rem Verify with --version rather than `where`: a Win11 box without Python still has the
rem Store alias stub %LOCALAPPDATA%\...\WindowsApps\python.exe, which `where` finds but
rem which only prints "Python was not found".
set "PYW="
set "PY="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined PYW set "PYW=%%i"
if defined PYW (
  set "PY=!PYW:pythonw.exe=python.exe!"
  "!PY!" --version >nul 2>nul || set "PY="
)
if not defined PY ( py -3 --version >nul 2>nul && set "PY=py -3" )
if not defined PY ( python --version >nul 2>nul && set "PY=python" )

if not defined PY (
  echo.
  echo [!] No working Python found, so packages were NOT refreshed.
  echo     Install Python 3.10+ from https://www.python.org/downloads/ then run setup.cmd.
) else (
  echo.
  echo Refreshing Python packages with !PY! ...
  %PY% -m pip install --upgrade claude-agent-sdk pillow keyboard
  rem An interrupted or proxy-blocked upgrade can leave a package UNINSTALLED - pip
  rem removes the old version before installing the new one. Saying "[OK] Updated" over
  rem the top of that is how an update turns into a launch that does nothing, so the
  rem failure has to stop the script.
  if errorlevel 1 (
    echo.
    echo [X] Refreshing the packages FAILED ^(see the pip output above^).
    echo     Your install may now be incomplete - do not skip this.
    echo     Retry, or run it yourself:
    echo       %PY% -m pip install --upgrade claude-agent-sdk pillow keyboard
    echo     Then double-click Diagnose.cmd to confirm the app can load.
    pause & exit /b 1
  )
)

rem --- refresh the desktop shortcut icon IF one already exists ---
rem The .lnk is machine-specific (gitignored), so git pull can't touch it. If a "Claude
rem Overlay" shortcut is on the Desktop, re-point it at the current icon. We skip this when
rem there's no shortcut, so update.cmd never creates one the user didn't ask for.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); if (Test-Path (Join-Path $d 'Claude Overlay.lnk')) { & '.\create-shortcut.ps1'; Write-Host '[OK] Desktop shortcut icon refreshed.' }"

rem --- prove the updated install can actually start ---------------------------
rem Checking here is the whole difference between "it broke and I don't know why" and
rem "the update told me". preflight loads the app exactly the way the launcher will.
if defined PY (
  echo.
  echo Checking that the updated app can load...
  %PY% "%~dp0preflight.py" >nul 2>nul
  if errorlevel 1 (
    echo.
    echo [X] The update left this install unable to start.
    echo     Run Diagnose.cmd for the details ^(and what fixes it^).
    echo.
    %PY% "%~dp0preflight.py"
    pause & exit /b 1
  )
  echo [OK] The app loads.
)

echo.
echo ============================================================
echo   [OK] Updated. IMPORTANT: close the running overlay and
echo   re-open it ^("Start Claude Overlay.cmd"^) for the changes
echo   to take effect - it does not reload while running.
echo ============================================================
pause
