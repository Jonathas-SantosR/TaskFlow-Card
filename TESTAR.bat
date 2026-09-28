@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INICIAR.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -m unittest -v
pause
endlocal
