@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=py"

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  "%PYTHON_EXE%" -3 -m venv .venv 2>nul || "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 goto erro
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_MYSQL.ps1"
if errorlevel 1 goto erro
goto fim

:erro
echo.
echo Nao foi possivel iniciar. Confira o Python e a configuracao do MySQL.
pause

:fim
endlocal
