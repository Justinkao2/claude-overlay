@echo off
rem Launch Claude Overlay with no console window. Portable: finds pythonw/pyw on PATH.
cd /d "%~dp0"
setlocal enabledelayedexpansion

rem Prefer the same `pythonw` this launcher has always used -- but VERIFY it is a real
rem interpreter first. Windows 11 ships an "App execution alias" stub at
rem %LOCALAPPDATA%\Microsoft\WindowsApps\pythonw.exe that `where` finds even when Python
rem is NOT installed; launching that opens the Microsoft Store (or does nothing at all)
rem and the overlay never appears. With no console there is nothing to read, so it looks
rem exactly like a crash -- and unlike a crash INSIDE the app, the app's own crash
rem reporter can't help, because no Python ever ran.
rem pythonw can't be version-checked itself (it has no console to print to), so check the
rem python.exe sitting next to it. Verifying rather than reordering is deliberate: a setup
rem that works today keeps using exactly the interpreter it always did.
set "PYW="
for /f "usebackq delims=" %%i in (`where pythonw 2^>nul`) do (
  if not defined PYW (
    set "CAND=%%i"
    set "SIB=!CAND:pythonw.exe=python.exe!"
    "!SIB!" --version >nul 2>nul && set "PYW=!CAND!"
  )
)
if defined PYW ( start "" "!PYW!" "%~dp0claude_overlay.py" & exit /b )

rem Nothing usable named pythonw: fall back to the py launcher's windowed twin.
py -3 --version >nul 2>nul && ( start "" pyw -3 "%~dp0claude_overlay.py" & exit /b )
where pyw >nul 2>nul && ( start "" pyw "%~dp0claude_overlay.py" & exit /b )

echo ============================================================
echo   [X] No working Python was found, so the overlay cannot start.
echo ============================================================
echo.
echo   `pythonw` is either missing, or it is the Microsoft Store
echo   placeholder rather than a real install.
echo.
echo   Fix: install Python 3.10+ from https://www.python.org/downloads/
echo        ^(tick "Add python.exe to PATH"^), then run setup.cmd.
echo.
echo   Already installed it? Double-click Diagnose.cmd for a report
echo   showing exactly which Python this machine resolves.
echo.
pause
