@echo off
rem Starts the Timbre studio with the XTTS-v2 voice model.
rem The first start downloads the model (~1.8 GB) and asks you to accept its license
rem (Coqui Public Model License, non-commercial) in this window: type y and press Enter.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Timbre isn't set up yet. Run setup.bat first.
  pause
  exit /b 1
)
rem Skip the license prompt if you've already accepted it on this computer.
if exist "data\xtts-license-accepted.txt" set COQUI_TOS_AGREED=1
set PYTHONIOENCODING=utf-8

echo Starting Timbre at http://127.0.0.1:7860
echo Loading the model takes a minute (several on the first start).
echo Your browser opens by itself when the studio is ready. Keep this window open.
echo.

rem Open the browser once the server answers.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 360;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:7860/api/status -TimeoutSec 3 | Out-Null; Start-Process 'http://127.0.0.1:7860'; break}catch{Start-Sleep 5}}"

".venv\Scripts\python.exe" cli.py serve
pause
