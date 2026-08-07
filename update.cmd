@echo off
rem Update Claude Overlay to the latest version (git pull, then update-finish.cmd).
rem
rem This script runs itself from a COPY in %TEMP%, and that is not paranoia. `git pull`
rem below replaces this very file, and cmd.exe reads the script it is executing from disk
rem by BYTE OFFSET as it goes -- so after the pull it carries on at that offset inside
rem whatever now lives there. It came out right the two times it was observed, because the
rem line numbers happened to line up; a one-line edit is enough to make it resume in the
rem middle of a different command, and nothing would say so. Running from %TEMP% puts the
rem executing bytes somewhere git cannot touch.
rem
rem Everything below is inside ONE parenthesised block on purpose: cmd parses a block to
rem its closing paren BEFORE running any of it, so the hand-off and the exit are already in
rem memory and are not re-read from a file that may have changed underneath.
rem
rem The folder is passed as "%~dp0." and not "%~dp0": %~dp0 always ends in a backslash, and
rem a quoted argument ending in \" is the classic Windows quote-escape trap.
setlocal enabledelayedexpansion
if /i not "%~1"=="--from-temp" (
  copy /y "%~f0" "%TEMP%\_ov_update.cmd" >nul
  if errorlevel 1 (
    echo [X] Could not stage the updater in "%TEMP%". Is the disk full?
    pause
    exit /b 1
  )
  cmd /c call "%TEMP%\_ov_update.cmd" --from-temp "%~dp0."
  set "RC=!errorlevel!"
  del "%TEMP%\_ov_update.cmd" >nul 2>nul
  exit /b !RC!
)

rem ---------------------------------------------------------------------------------
rem From here on we ARE the copy in %TEMP%, and %2 is the folder to update.
rem ---------------------------------------------------------------------------------
cd /d "%~2"
if errorlevel 1 ( echo [X] Cannot enter "%~2". & pause & exit /b 1 )
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

rem --- hand the rest to the code we JUST downloaded ----------------------------
rem Deliberately the freshly pulled update-finish.cmd rather than a copy of whatever
rem shipped with the version being replaced: the post-pull half has to match the code it
rem is about to check, and it is the half that knows where this release looks for Python.
if not exist "update-finish.cmd" (
  echo.
  echo [!] The code updated, but update-finish.cmd is not in this folder, so the
  echo     packages were NOT refreshed. Double-click setup.cmd to finish.
  pause & exit /b 1
)
call "update-finish.cmd"
exit /b %errorlevel%
