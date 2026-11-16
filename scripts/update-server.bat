@echo off
rem Gets the latest tri-planner and its dependencies. Restart the server afterwards
rem (Task Scheduler: End, then Run; or restart the computer).
cd /d "%~dp0\.."
git pull || goto :failed
".venv\Scripts\python.exe" -m pip install -e ".[fit,web,garmin]" || goto :failed
echo.
echo Updated. Now restart the server: Task Scheduler - tri-planner - End, then Run.
pause
exit /b 0
:failed
echo.
echo Something went wrong above. Nothing else was changed.
pause
exit /b 1
