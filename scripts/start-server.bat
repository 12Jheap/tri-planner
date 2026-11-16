@echo off
rem Starts tri-planner as a home server, reachable from other devices on your network.
rem Point Windows Task Scheduler at this file (trigger: At startup). See docs\server.md.
cd /d "%~dp0\.."
if not exist out mkdir out
".venv\Scripts\tri-plan.exe" web --host 0.0.0.0 --no-browser >> out\server.log 2>&1
