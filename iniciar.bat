@echo off
setlocal
cd /d "%~dp0"
rem O ambiente virtual mantém as dependências isoladas do restante do computador.
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto :erro
)
rem A instalação só acontece quando o Flask ainda não está disponível.
".venv\Scripts\python.exe" -c "import flask" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :erro
)
rem O navegador abre na mesma porta usada pelo servidor local.
start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :erro
exit /b 0
:erro
echo Nao foi possivel iniciar. Confira o erro acima e a instalacao do Python 3.
pause
exit /b 1
