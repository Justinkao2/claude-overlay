@echo off
rem The second half of update.cmd: refresh the packages, the shortcut icon, and prove the
rem app can still start. Split out so that update.cmd -- which `git pull` overwrites while
rem it is running -- has nothing left to read from itself after the pull, and so that this
rem half is always the version that was just DOWNLOADED rather than the one being replaced.
rem It knows where this release looks for Python, which is exactly what has to match.
rem
rem Safe to double-click on its own: that is the right thing to run if an update got as far
rem as pulling the code and then failed on the packages.
cd /d "%~dp0"
setlocal enabledelayedexpansion

rem --- refresh Python packages ------------------------------------------------
rem Into the interpreter the LAUNCHER uses, not whichever one `py -3` happens to pick.
rem "Start Claude Overlay.cmd" runs whichever `pythonw` it finds first; on a machine with
rem two Pythons (a common one: python.org plus the Microsoft Store build) upgrading the
rem wrong one leaves the app running against packages nobody refreshed - and the symptom
rem of that is a launch that silently does nothing.
rem Verify by RUNNING each candidate, not by testing a different file: a Win11 box
rem without Python still has the Store alias stub in %LOCALAPPDATA%\...\WindowsApps\,
rem which `where` finds but which only prints "Python was not found".
rem Every probe goes through `call`: `where` can return a .bat/.cmd shim (pyenv-win and
rem some conda wrappers install one), and running a batch file from a batch file without
rem `call` transfers control and never returns -- which would end this script mid-check.
rem And PATH is not the whole world: setup.cmd installs into
rem %LOCALAPPDATA%\Programs\Python\Python3xx\ and finds it there by scanning. Refreshing
rem packages into "whatever is on PATH" while the launcher runs a Python that is not, is
rem how an update reports success and changes nothing the app will load.
rem ---- BEGIN find-pythonw (kept identical in Diagnose.cmd and update.cmd) ----
set "PYW="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do if not defined PYW (call "%%i" -c "pass" >nul 2>nul && set "PYW=%%i")
if not defined PYW for /f "delims=" %%p in ('dir /b /s /a-d /o-n "%LOCALAPPDATA%\Programs\Python\pythonw.exe" 2^>nul') do if not defined PYW (call "%%p" -c "pass" >nul 2>nul && set "PYW=%%p")
if not defined PYW for /d %%d in ("%ProgramFiles%\Python3*") do if not defined PYW (call "%%d\pythonw.exe" -c "pass" >nul 2>nul && set "PYW=%%d\pythonw.exe")
if not defined PYW for /d %%d in ("%SystemDrive%\Python3*") do if not defined PYW (call "%%d\pythonw.exe" -c "pass" >nul 2>nul && set "PYW=%%d\pythonw.exe")
rem ---- END find-pythonw ----

set "PY="
rem pip's output is invisible under pythonw (no console), so drive pip with the
rem python.exe beside it WHEN that one also runs - same install, same site-packages,
rem readable output. When it doesn't, use pythonw itself anyway: upgrading the right
rem environment matters more than watching it happen, and `if errorlevel 1` below still
rem catches a failure. Only the launcher's own interpreter is ever the right target.
set "SIB="
if defined PYW set "SIB=!PYW:pythonw.exe=python.exe!"
if defined SIB (call "!SIB!" -c "pass" >nul 2>nul && set PY="!SIB!")
if not defined PY if defined PYW set PY="!PYW!"
if not defined PY ( call py -3 -c "pass" >nul 2>nul && set "PY=py -3" )
if not defined PY ( call python -c "pass" >nul 2>nul && set "PY=python" )
if not defined PY for /f "delims=" %%p in ('dir /b /s /a-d /o-n "%LOCALAPPDATA%\Programs\Python\python.exe" 2^>nul') do if not defined PY (call "%%p" -c "pass" >nul 2>nul && set PY="%%p")

if not defined PY (
  echo.
  echo [!] No working Python found, so packages were NOT refreshed.
  echo     The code IS updated - only the packages were skipped.
  echo     Double-click setup.cmd: it installs Python when it is missing
  echo     ^(per-user, no admin^) and then installs the packages too.
) else (
  echo.
  rem requirements.txt is the single source of the version list. Naming packages here as
  rem well is how the two drifted: the file said one thing and every user got another.
  if not exist "%~dp0requirements.txt" (
    echo [X] requirements.txt is missing, so there is nothing to install from.
    echo     Re-download the ZIP and unzip ALL of it over this folder.
    pause & exit /b 1
  )
  echo Refreshing Python packages with !PY! ...
  call %PY% -m pip install --upgrade -r "%~dp0requirements.txt"
  rem An interrupted or proxy-blocked upgrade can leave a package UNINSTALLED - pip
  rem removes the old version before installing the new one. Saying "[OK] Updated" over
  rem the top of that is how an update turns into a launch that does nothing, so the
  rem failure has to stop the script.
  if errorlevel 1 (
    echo.
    echo [X] Refreshing the packages FAILED ^(see the pip output above^).
    echo     Your install may now be incomplete - do not skip this.
    echo     Retry, or run it yourself:
    echo       %PY% -m pip install --upgrade -r requirements.txt
    echo     Then double-click Diagnose.cmd to confirm the app can load.
    pause & exit /b 1
  )
)

rem --- refresh the desktop shortcut icon IF one already exists ---
rem The .lnk is machine-specific (gitignored), so git pull can't touch it. If a "Claude
rem Overlay" shortcut is on the Desktop, re-point it at the current icon. We skip this when
rem there's no shortcut, so an update never creates one the user didn't ask for.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); if (Test-Path (Join-Path $d 'Claude Overlay.lnk')) { & '.\create-shortcut.ps1'; Write-Host '[OK] Desktop shortcut icon refreshed.' }"

rem --- prove the updated install can actually start ---------------------------
rem Checking here is the whole difference between "it broke and I don't know why" and
rem "the update told me". preflight loads the app exactly the way the launcher will.
if defined PY (
  echo.
  echo Checking that the updated app can load...
  call %PY% "%~dp0preflight.py" >nul 2>nul
  if errorlevel 1 (
    echo.
    echo [X] The update left this install unable to start.
    echo     Run Diagnose.cmd for the details ^(and what fixes it^).
    echo.
    call %PY% "%~dp0preflight.py"
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
