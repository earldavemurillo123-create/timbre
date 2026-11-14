@echo off
rem Starts the Timbre studio with the demo engine: no model, no download.
rem Takes are a placeholder hum, which is handy for trying the interface.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Timbre isn't set up yet. Run setup.bat first.
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
echo Starting Timbre (demo engine) at http://127.0.0.1:7860
echo Keep this window open while you use Timbre. Close it to stop the studio.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:7860"
".venv\Scripts\python.exe" cli.py --engine demo serve
pause
