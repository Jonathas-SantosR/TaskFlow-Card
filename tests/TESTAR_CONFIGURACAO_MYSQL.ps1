$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'MYSQL_CONFIGURACAO.ps1')
$pastaTeste = Join-Path ([IO.Path]::GetTempPath()) ('taskflow-config-' + [guid]::NewGuid())
$arquivoTeste = Join-Path $pastaTeste 'mysql-config.json'
function Assert-Config($Condicao, $Mensagem) { if (-not $Condicao) { throw $Mensagem } }
function Read-Host {
    param([string]$Prompt, [switch]$AsSecureString)
    if ($script:respostas.Count -eq 0) { throw 'Pergunta inesperada no teste.' }
    $resposta = $script:respostas.Dequeue()
    if ($AsSecureString) { return ConvertTo-SecureString $resposta -AsPlainText -Force }
    return $resposta
}
function Set-Answers([string[]]$Values) {
    $script:respostas = [Collections.Generic.Queue[string]]::new()
    foreach ($v in $Values) { $script:respostas.Enqueue($v) }
}
try {
    Assert-Config ($null -eq (Read-MySqlConfiguration $arquivoTeste)) 'Arquivo ausente deve retornar vazio.'
    $original = [pscustomobject]@{ servidor='127.0.0.1'; porta=3306; banco='teste'; usuario='usuario'; senha='Aspas" e $simbolos; \ segredo' }
    Save-MySqlConfiguration $arquivoTeste $original
    Assert-Config ((Read-MySqlConfiguration $arquivoTeste).senha -ceq $original.senha) 'Senha alterada no JSON.'
    Set-Answers @('')
    $usada = Select-MySqlConfiguration $arquivoTeste
    Assert-Config ($usada.banco -eq 'teste') 'Enter deve reutilizar.'
    Set-Answers @('N', '', 'abc', '70000', '3307', 'temporario', 'outro', 'senha-temporaria')
    $temporaria = Select-MySqlConfiguration $arquivoTeste
    Assert-Config ($temporaria.porta -eq '3307' -and $temporaria.banco -eq 'temporario') 'Validacao de entrada falhou.'
    Assert-Config ((Read-MySqlConfiguration $arquivoTeste).banco -eq 'teste') 'Sessao temporaria sobrescreveu o arquivo.'
    Set-Answers @('A', '', '', 'alterado', '', 'N', 'S')
    $alterada = Select-MySqlConfiguration $arquivoTeste
    Assert-Config ((Read-MySqlConfiguration $arquivoTeste).banco -eq 'alterado') 'Alteracao nao persistiu.'
    Assert-Config ($alterada.senha -ceq $original.senha) 'Alteracao parcial deve manter a senha.'
    $invalida = [pscustomobject]@{ servidor='x'; porta=0; banco='x'; usuario='x'; senha='' }
    $recusada = $false
    try { Save-MySqlConfiguration $arquivoTeste $invalida } catch { $recusada = $true }
    Assert-Config $recusada 'Configuracao invalida deve ser recusada.'
    Assert-Config ((Read-MySqlConfiguration $arquivoTeste).banco -eq 'alterado') 'Falha destruiu configuracao anterior.'
    Set-Answers @('R', 'N')
    $mantida = Select-MySqlConfiguration $arquivoTeste
    Assert-Config (Test-Path -LiteralPath $arquivoTeste) 'Cancelar remocao deve preservar.'
    Set-Answers @('R', 'S', '', '', '', 'sessao', 'senha-sessao')
    $removida = Select-MySqlConfiguration $arquivoTeste
    Assert-Config (-not (Test-Path -LiteralPath $arquivoTeste)) 'Remocao nao excluiu configuracao.'
    [IO.File]::WriteAllText($arquivoTeste, '{json invalido')
    Set-Answers @('', '', '', 'novo', 'senha-nova', 'N')
    $recuperada = Select-MySqlConfiguration $arquivoTeste
    Assert-Config ($recuperada.usuario -eq 'novo') 'Arquivo invalido deve permitir nova entrada.'
    Assert-Config (([IO.File]::ReadAllText($arquivoTeste)) -eq '{json invalido') 'Nao salvar deve preservar arquivo existente.'
    Write-Host 'Configuracao MySQL: todos os cenarios aprovados.'
}
finally {
    # Somente arquivos conhecidos de teste; nenhuma conexao com o banco e feita.
    if (Test-Path -LiteralPath $arquivoTeste) { Remove-Item -LiteralPath $arquivoTeste }
    if (Test-Path -LiteralPath $pastaTeste) { Remove-Item -LiteralPath $pastaTeste }
}
