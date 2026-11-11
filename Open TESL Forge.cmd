@echo off
rem Double-click to open TESL Forge in its own window. Closing that window stops it.
title TESL Forge
start "" "%~dp0.venv\Scripts\pythonw.exe" -X utf8 -m tesl_suite.cli window
