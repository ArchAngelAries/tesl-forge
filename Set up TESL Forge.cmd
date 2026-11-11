@echo off
rem TESL Forge first-time setup: makes its own Python environment (.venv) in this folder and installs what it needs.
rem Needs Python 3.10 or newer from python.org (tick "Add python.exe to PATH" when installing). Run once; run again to repair.
title TESL Forge setup
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto failed
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto failed
echo.
echo TESL Forge is ready. Open it with "Open TESL Forge.cmd".
pause
exit /b 0
:failed
echo Setup did not finish. Check your internet connection and try again.
pause
exit /b 1
