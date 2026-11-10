param([switch]$Navegador)
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $raizProjeto
$pythonTeste = Join-Path $raizProjeto '.venv/Scripts/python.exe'
Write-Host 'Use uma instancia MySQL de testes. Serao criados e removidos somente bancos taskflow_teste_<id>.'
$env:TASKFLOW_TEST_MYSQL_HOST = Read-Host 'Servidor de testes (ex.: 127.0.0.1)'
$env:TASKFLOW_TEST_MYSQL_PORT = Read-Host 'Porta de testes (ex.: 3306)'
$env:TASKFLOW_TEST_MYSQL_USER = Read-Host 'Usuario com permissao para criar e remover bancos de teste'
$segredoTeste = Read-Host 'Senha MySQL' -AsSecureString
$env:TASKFLOW_TEST_MYSQL_PASSWORD = [System.Net.NetworkCredential]::new('', $segredoTeste).Password
$env:TASKFLOW_TEST_MYSQL = '1'
try {
    if ($Navegador) {
        $env:TASKFLOW_TEST_BROWSER = '1'
        & $pythonTeste -B -m unittest -v tests.test_navegador
    } else {
        & $pythonTeste -B -m unittest -v tests.test_integracao_mysql
    }
    if ($LASTEXITCODE -ne 0) { throw 'A validacao encontrou falhas.' }
} finally {
    foreach ($nomeVariavel in @('TASKFLOW_TEST_MYSQL_HOST','TASKFLOW_TEST_MYSQL_PORT',
        'TASKFLOW_TEST_MYSQL_USER','TASKFLOW_TEST_MYSQL_PASSWORD','TASKFLOW_TEST_MYSQL',
        'TASKFLOW_TEST_BROWSER')) {
        Remove-Item -LiteralPath ('Env:' + $nomeVariavel) -ErrorAction SilentlyContinue
    }
}
