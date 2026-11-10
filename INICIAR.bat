@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto validar_ambiente
py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if not errorlevel 1 goto criar_com_py
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if errorlevel 1 goto python_ausente
python -m venv .venv
if errorlevel 1 goto erro
goto validar_ambiente

:criar_com_py
py -3 -m venv .venv
if errorlevel 1 goto erro

:validar_ambiente
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3,11))"
if errorlevel 1 (
  echo O ambiente .venv nao e valido nesta maquina. Renomeie essa pasta e inicie novamente.
  goto erro
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro

rem O servidor usa um console proprio. Este lote termina antes de Ctrl+C,
rem evitando a confirmacao de encerramento do CMD durante o jogo.
start "TaskFlowCards - servidor" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_MYSQL.ps1"
goto fim

:erro
echo.
echo Nao foi possivel iniciar. Confira o Python e a configuracao do MySQL.
pause
goto fim

:python_ausente
echo Instale Python 3.11 ou superior e habilite o comando python ou py.
pause

:fim
endlocal
