@echo off
rem Installs PyTorch (CPU) and the XTTS voice model package into Timbre's environment.
setlocal
cd /d "%~dp0"
set LOG=%~dp0model-install-log.txt

if not exist ".venv\Scripts\python.exe" (
  echo Run run-demo.bat once first to set up Timbre.
  pause
  exit /b 1
)

echo Installing the voice model packages. This downloads about 1 GB and can take 10+ minutes...
echo ==== model install %date% %time% ==== > "%LOG%"
".venv\Scripts\python.exe" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu >> "%LOG%" 2>&1
if errorlevel 1 (
  echo PyTorch install failed. See model-install-log.txt
  echo TORCH FAILED >> "%LOG%"
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install coqui-tts >> "%LOG%" 2>&1
if errorlevel 1 (
  echo coqui-tts install failed. See model-install-log.txt
  echo COQUI FAILED >> "%LOG%"
  pause
  exit /b 1
)
echo MODEL INSTALL OK >> "%LOG%"
echo Done. Start the real studio with run-timbre.bat
pause
