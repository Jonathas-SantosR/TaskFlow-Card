@echo off
setlocal
cd /d "%~dp0"
rem Reutiliza o mesmo ambiente preparado pelo inicializador da aplicação.
if not exist ".venv\Scripts\python.exe" (
    echo Execute iniciar.bat primeiro para preparar o ambiente.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest -v test_web.py
pause
