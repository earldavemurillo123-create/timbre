@echo off
rem Starts Timbre with the real XTTS-v2 voice model.
rem The first start downloads the model (~1.8 GB) and asks you to accept its
rem non-commercial license (Coqui Public Model License) in this window.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run-demo.bat first, then install-voice-model.bat.
  pause
  exit /b 1
)
echo Starting Timbre (XTTS-v2) at http://127.0.0.1:7860
echo Loading the model takes a while. The browser opens when it's ready; refresh if it shows an error.
echo.
start "" cmd /c "timeout /t 60 >nul & start http://127.0.0.1:7860"
".venv\Scripts\python.exe" cli.py serve
pause
