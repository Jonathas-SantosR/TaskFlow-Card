$ErrorActionPreference = "Stop"
$executavel = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$aplicacao = Join-Path $PSScriptRoot "app.py"

$hostInformado = Read-Host "Servidor MySQL [127.0.0.1]"
$portaInformada = Read-Host "Porta MySQL [3306]"
$bancoInformado = Read-Host "Nome do banco [taskflowcards]"
$usuarioInformado = Read-Host "Usuário MySQL"
$senhaSegura = Read-Host "Senha MySQL" -AsSecureString
$credencial = [System.Net.NetworkCredential]::new("", $senhaSegura)
$codigoInicial = Read-Host "Código do primeiro professor (deixe vazio se já existe)" -AsSecureString
$credencialInicial = [System.Net.NetworkCredential]::new("", $codigoInicial)

$env:TASKFLOW_MYSQL_HOST = if ($hostInformado) { $hostInformado } else { "127.0.0.1" }
$env:TASKFLOW_MYSQL_PORT = if ($portaInformada) { $portaInformada } else { "3306" }
$env:TASKFLOW_MYSQL_DATABASE = if ($bancoInformado) { $bancoInformado } else { "taskflowcards" }
$env:TASKFLOW_MYSQL_USER = $usuarioInformado
$env:TASKFLOW_MYSQL_PASSWORD = $credencial.Password
if ($credencialInicial.Password) {
    $env:TASKFLOW_SETUP_CODE = $credencialInicial.Password
}

$usarGemini = Read-Host "Deseja usar o Google Gemini? [S/N]"
if ($usarGemini -match '^[Ss]$') {
    $geminiSegura = Read-Host "Chave do Google AI Studio" -AsSecureString
    $credencialGemini = [System.Net.NetworkCredential]::new("", $geminiSegura)
    $env:GEMINI_API_KEY = $credencialGemini.Password
    $env:GEMINI_MODEL = "gemini-3.5-flash-lite"
}

try {
    Write-Host ""
    Write-Host "Servidor pronto para iniciar." -ForegroundColor Green
    Write-Host "O navegador não será aberto automaticamente." -ForegroundColor Cyan
    & $executavel $aplicacao
}
finally {
    Remove-Item Env:TASKFLOW_MYSQL_HOST -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_DATABASE -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_USER -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_MYSQL_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:TASKFLOW_SETUP_CODE -ErrorAction SilentlyContinue
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:GEMINI_MODEL -ErrorAction SilentlyContinue
}
