$ErrorActionPreference = "Stop"
$executavel = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Set-Location -LiteralPath $PSScriptRoot

. (Join-Path $PSScriptRoot 'MYSQL_CONFIGURACAO.ps1')
$configuracaoMySql = Select-MySqlConfiguration -Path (Join-Path $PSScriptRoot 'config\mysql-config.json')
$codigoInicial = Read-Host "Código do primeiro professor (deixe vazio se já existe)" -AsSecureString
$credencialInicial = [System.Net.NetworkCredential]::new("", $codigoInicial)

$env:TASKFLOW_MYSQL_HOST = $configuracaoMySql.servidor
$env:TASKFLOW_MYSQL_PORT = [string]$configuracaoMySql.porta
$env:TASKFLOW_MYSQL_DATABASE = $configuracaoMySql.banco
$env:TASKFLOW_MYSQL_USER = $configuracaoMySql.usuario
$env:TASKFLOW_MYSQL_PASSWORD = $configuracaoMySql.senha
if ($credencialInicial.Password) {
    $env:TASKFLOW_SETUP_CODE = $credencialInicial.Password
}

. (Join-Path $PSScriptRoot 'GEMINI_CREDENCIAL.ps1')
$arquivoGemini = Join-Path $PSScriptRoot 'config\gemini-key.txt'
$geminiSegura = $null
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
try {
    $geminiSegura = Read-GeminiCredential -Path $arquivoGemini
}
catch {
    Write-Host 'Nao foi possivel ler config/gemini-key.txt. Confira o arquivo ou cadastre a chave novamente.' -ForegroundColor Yellow
}
if ($geminiSegura) {
    Write-Host 'Chave Gemini encontrada em config/gemini-key.txt.' -ForegroundColor Green
    do {
        $opcaoGemini = (Read-Host 'Gemini: Enter para usar a chave salva, A para alterar, R para remover, N para nao usar nesta sessao').Trim().ToUpperInvariant()
    } while ($opcaoGemini -notin @('', 'A', 'R', 'N'))
    if ($opcaoGemini -eq 'R') {
        if ((Read-Host 'Remover a chave salva? [S/N]') -match '^[Ss]$') {
            Remove-Item -LiteralPath $arquivoGemini -ErrorAction Stop
            $geminiSegura = $null
            Write-Host 'Arquivo da chave removido. Isso nao revoga a chave no Google.'
        }
    }
    elseif ($opcaoGemini -eq 'N') { $geminiSegura = $null }
}
else {
    Write-Host 'Nenhuma chave Gemini salva no arquivo do projeto.'
    $opcaoGemini = if ((Read-Host 'Deseja informar e salvar a chave em config/gemini-key.txt? [S/N]') -match '^[Ss]$') { 'A' } else { 'N' }
}
if ($opcaoGemini -eq 'A') {
    $novaChaveGemini = Read-Host 'Nova chave do Google AI Studio (Enter cancela)' -AsSecureString
    if ($novaChaveGemini.Length -gt 0) {
        try {
            Save-GeminiCredential -Path $arquivoGemini -Secret $novaChaveGemini
            $geminiSegura = Read-GeminiCredential -Path $arquivoGemini
            Write-Host 'Chave salva em config/gemini-key.txt. Voce pode editar esse arquivo no Bloco de Notas.' -ForegroundColor Green
        }
        catch { Write-Host 'Nao foi possivel salvar a nova chave. A configuracao anterior foi mantida.' -ForegroundColor Yellow }
    }
}
if ($geminiSegura) {
    $credencialGemini = [System.Net.NetworkCredential]::new("", $geminiSegura)
    $env:GEMINI_API_KEY = $credencialGemini.Password
    $env:GEMINI_MODEL = "gemini-3.5-flash-lite"
}

try {
    Write-Host ""
    Write-Host "Servidor pronto para iniciar." -ForegroundColor Green
    Write-Host "O navegador não será aberto automaticamente." -ForegroundColor Cyan
    & $executavel -m backend.app
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
