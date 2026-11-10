# Configuracao portatil local. A senha salva fica em texto legivel, como a chave Gemini.
function Test-MySqlConfiguration {
    param([Parameter(Mandatory=$true)]$Configuration)
    foreach ($campo in @('servidor', 'banco', 'usuario')) {
        if ($Configuration.$campo -isnot [string] -or [string]::IsNullOrWhiteSpace($Configuration.$campo) -or $Configuration.$campo -match '[\r\n\x00]') {
            throw "Configuracao MySQL invalida: $campo."
        }
    }
    $porta = 0
    if (-not [int]::TryParse([string]$Configuration.porta, [ref]$porta) -or $porta -lt 1 -or $porta -gt 65535) {
        throw 'Porta MySQL deve ser um numero entre 1 e 65535.'
    }
    if ($Configuration.senha -isnot [string]) { throw 'Configuracao MySQL sem campo senha valido.' }
}

function Read-MySqlConfiguration {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $texto = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
    if ([string]::IsNullOrWhiteSpace($texto)) { return $null }
    $configuracao = $texto | ConvertFrom-Json -ErrorAction Stop
    Test-MySqlConfiguration -Configuration $configuracao
    return $configuracao
}

function Save-MySqlConfiguration {
    param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)]$Configuration)
    Test-MySqlConfiguration -Configuration $Configuration
    $pasta = Split-Path -Parent $Path
    [void](New-Item -ItemType Directory -Path $pasta -Force -ErrorAction Stop)
    $temporario = Join-Path $pasta ([guid]::NewGuid().ToString() + '.tmp')
    try {
        $Configuration | ConvertTo-Json | Set-Content -LiteralPath $temporario -Encoding UTF8 -ErrorAction Stop
        Move-Item -LiteralPath $temporario -Destination $Path -Force -ErrorAction Stop
    }
    finally {
        if (Test-Path -LiteralPath $temporario) { Remove-Item -LiteralPath $temporario -Force }
    }
}

function Request-MySqlConfiguration {
    param($Previous = $null)
    $padroes = @{ servidor = '127.0.0.1'; porta = '3306'; banco = 'taskflowcards'; usuario = '' }
    $rotulos = @{ servidor = 'Servidor MySQL'; porta = 'Porta MySQL'; banco = 'Nome do banco'; usuario = 'Usuario MySQL' }
    $valores = @{}
    foreach ($campo in @('servidor', 'porta', 'banco', 'usuario')) {
        $padrao = if ($null -ne $Previous) { [string]$Previous.$campo } else { $padroes[$campo] }
        do {
            $entrada = (Read-Host ($rotulos[$campo] + " [$padrao]")).Trim()
            $valor = if ($entrada) { $entrada } else { $padrao }
            $valido = -not [string]::IsNullOrWhiteSpace($valor) -and $valor -notmatch '[\r\n\x00]'
            if ($campo -eq 'porta') {
                $numero = 0
                $valido = [int]::TryParse($valor, [ref]$numero) -and $numero -ge 1 -and $numero -le 65535
            }
            if (-not $valido) { Write-Host 'Valor invalido. Informe novamente.' -ForegroundColor Yellow }
        } while (-not $valido)
        $valores[$campo] = $valor
    }
    $trocarSenha = $true
    if ($null -ne $Previous) {
        do { $opcaoSenha = (Read-Host 'Alterar a senha MySQL? [S/N; Enter = N]').Trim().ToUpperInvariant() } while ($opcaoSenha -notin @('', 'S', 'N'))
        $trocarSenha = $opcaoSenha -eq 'S'
    }
    $valores.senha = if ($trocarSenha) {
        $segura = Read-Host 'Senha MySQL (Enter para senha vazia)' -AsSecureString
        [System.Net.NetworkCredential]::new('', $segura).Password
    } else { $Previous.senha }
    $configuracao = [pscustomobject]$valores
    Test-MySqlConfiguration -Configuration $configuracao
    return $configuracao
}

function Select-MySqlConfiguration {
    param([Parameter(Mandatory=$true)][string]$Path)
    $salva = $null
    try { $salva = Read-MySqlConfiguration -Path $Path }
    catch { Write-Host 'Arquivo MySQL invalido ou inacessivel. Informe a conexao novamente; o arquivo so sera substituido se voce escolher salvar.' -ForegroundColor Yellow }
    if ($null -ne $salva) {
        Write-Host ("Conexao salva: {0}:{1} / {2} / usuario {3}" -f $salva.servidor, $salva.porta, $salva.banco, $salva.usuario)
        do {
            $opcao = (Read-Host 'MySQL: Enter para usar, A para alterar, R para remover a configuracao salva, N para outra conexao somente nesta sessao').Trim().ToUpperInvariant()
        } while ($opcao -notin @('', 'A', 'R', 'N'))
        if ($opcao -eq '') { return $salva }
        if ($opcao -eq 'R') {
            if ((Read-Host 'Remover somente o arquivo salvo, sem apagar o banco ou seus dados? [S/N]') -notmatch '^[Ss]$') { return $salva }
            Remove-Item -LiteralPath $Path -ErrorAction Stop
            Write-Host 'Configuracao removida. Informe a conexao para esta sessao.'
            return Request-MySqlConfiguration
        }
        if ($opcao -eq 'N') { return Request-MySqlConfiguration }
    }
    $nova = Request-MySqlConfiguration -Previous $salva
    Write-Host 'Salvar inclui a senha em texto legivel em config/mysql-config.json. Nao compartilhe esse arquivo.' -ForegroundColor Yellow
    do { $salvar = (Read-Host 'Salvar esta conexao para as proximas inicializacoes? [S/N]').Trim().ToUpperInvariant() } while ($salvar -notin @('S', 'N'))
    if ($salvar -eq 'S') {
        try {
            Save-MySqlConfiguration -Path $Path -Configuration $nova
            Write-Host 'Configuracao MySQL salva.' -ForegroundColor Green
        }
        catch { Write-Host 'Nao foi possivel salvar. A conexao informada sera usada somente nesta sessao.' -ForegroundColor Yellow }
    }
    return $nova
}
