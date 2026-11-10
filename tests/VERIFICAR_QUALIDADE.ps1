$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $raizProjeto
$pythonTeste = Join-Path $raizProjeto '.venv/Scripts/python.exe'
& (Join-Path $PSScriptRoot 'TESTAR_CONFIGURACAO_MYSQL.ps1')
& $pythonTeste -m ruff check backend banco_de_dados tests
if ($LASTEXITCODE -ne 0) { throw 'Corrija os problemas de analise de codigo.' }
& $pythonTeste -m ruff format --check backend banco_de_dados tests
if ($LASTEXITCODE -ne 0) { throw 'Execute ruff format para padronizar os arquivos.' }
& $pythonTeste -B -m unittest discover -v
if ($LASTEXITCODE -ne 0) { throw 'Os testes encontraram falhas.' }
