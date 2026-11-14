@echo off
rem Sets up Timbre (first run only) and starts the studio with the demo engine.
setlocal
cd /d "%~dp0"
set LOG=%~dp0setup-log.txt

if exist ".venv\Scripts\python.exe" goto start

echo Setting up Timbre. This takes a minute or two the first time...
echo ==== setup %date% %time% ==== > "%LOG%"

set PY=
where py >nul 2>&1 && set PY=py -3
if not defined PY (
  python --version >nul 2>&1 && set PY=python
)
if not defined PY (
  echo Python was not found. Install Python 3.10-3.12 from python.org, then run this again.
  echo PYTHON NOT FOUND >> "%LOG%"
  pause
  exit /b 1
)

%PY% --version >> "%LOG%" 2>&1
%PY% -m venv .venv >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Couldn't create the virtual environment. See setup-log.txt
  echo VENV FAILED >> "%LOG%"
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pip install fastapi "uvicorn[standard]" python-multipart numpy scipy pytest httpx >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Package install failed. See setup-log.txt
  echo PIP FAILED >> "%LOG%"
  pause
  exit /b 1
)
echo SETUP OK >> "%LOG%"

:start
echo.
echo Starting Timbre (demo engine) at http://127.0.0.1:7860
echo Keep this window open while you use Timbre. Close it to stop the studio.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:7860"
".venv\Scripts\python.exe" cli.py --engine demo serve
pause
