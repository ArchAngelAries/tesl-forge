@echo off
rem TESL Forge launcher: runs the core with the suite's own Python environment.
"%~dp0.venv\Scripts\python.exe" -X utf8 -m tesl_suite.cli %*
