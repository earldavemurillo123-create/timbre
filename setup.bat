@echo off
rem Timbre setup for Windows: creates a Python 3.12 environment in .venv and
rem installs everything from requirements.txt. Safe to run again.
rem   setup.bat        CPU (works on any PC)
rem   setup.bat cuda   NVIDIA GPU (much faster)
setlocal
cd /d "%~dp0"
set LOG=%~dp0setup-log.txt
echo ==== setup %date% %time% ==== > "%LOG%"

echo.
echo  Timbre setup
echo  ------------
echo  This downloads about 1 GB of packages and takes 5-15 minutes.
echo.

rem ---------------------------------------------------------------- Python 3.12
call :has312 && goto have312
echo Python 3.12 wasn't found. Trying to install it with the Python install manager...
where py >nul 2>&1 && py install 3.12
call :has312 && goto have312
echo.
echo Timbre needs Python 3.12. Install it from:
echo   https://www.python.org/downloads/release/python-31210/
echo Tick "Add python.exe to PATH" and "Install py launcher", then run setup.bat again.
echo PYTHON 3.12 NOT FOUND >> "%LOG%"
pause
exit /b 1

:have312
py -3.12 -c "import sys; print('Using Python', sys.version.split()[0])"

rem ---------------------------------------------------------------- environment
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" || (
    echo.
    echo The existing .venv folder uses a different Python version.
    echo Rename or delete the .venv folder, then run setup.bat again.
    echo WRONG VENV >> "%LOG%"
    pause
    exit /b 1
  )
) else (
  echo Creating the environment in .venv ...
  py -3.12 -m venv .venv >> "%LOG%" 2>&1 || goto fail
)
set PY=.venv\Scripts\python.exe

rem ---------------------------------------------------------------- packages
echo Installing packages (progress is written to setup-log.txt) ...
"%PY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
if /i "%~1"=="cuda" (
  echo Installing PyTorch with NVIDIA CUDA support ...
  "%PY%" -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 >> "%LOG%" 2>&1 || goto fail
)
"%PY%" -m pip install -r requirements.txt >> "%LOG%" 2>&1 || goto fail

rem ---------------------------------------------------------------- check
echo Checking the install ...
"%PY%" -c "import torch, TTS.api, fastapi; print('torch', torch.__version__, '| GPU:', torch.cuda.is_available())" >> "%LOG%" 2>&1 || goto fail
"%PY%" -c "import torch; print('Ready. PyTorch', torch.__version__, '| NVIDIA GPU:', 'yes' if torch.cuda.is_available() else 'no (runs on CPU)')"
echo SETUP OK >> "%LOG%"
echo.
echo Done. Start Timbre with run-timbre.bat (or run-demo.bat to try it without the model).
pause
exit /b 0

:fail
echo.
echo Setup failed. The last lines of setup-log.txt say what went wrong.
echo SETUP FAILED >> "%LOG%"
pause
exit /b 1

:has312
py -3.12 -c "print('ok312')" 2>nul | findstr "ok312" >nul
exit /b %errorlevel%
