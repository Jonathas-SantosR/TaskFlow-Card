# Arquivo de texto portatil. SecureString serve apenas para a entrada no terminal.
function Read-GeminiCredential {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $conteudo = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($conteudo)) { return $null }
        return ConvertTo-SecureString -String $conteudo.Trim() -AsPlainText -Force -ErrorAction Stop
    }
    return $null
}

function Save-GeminiCredential {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][System.Security.SecureString]$Secret
    )
    $texto = ([System.Net.NetworkCredential]::new('', $Secret).Password).Trim()
    if ([string]::IsNullOrWhiteSpace($texto) -or $texto -match '\s') { throw 'Informe uma chave sem espacos ou quebras de linha.' }
    $pasta = Split-Path -Parent $Path
    [void](New-Item -ItemType Directory -Path $pasta -Force -ErrorAction Stop)
    $temporario = Join-Path $pasta ([System.Guid]::NewGuid().ToString() + '.tmp')
    try {
        Set-Content -LiteralPath $temporario -Value $texto -Encoding UTF8 -ErrorAction Stop
        Move-Item -LiteralPath $temporario -Destination $Path -Force -ErrorAction Stop
    }
    finally {
        if (Test-Path -LiteralPath $temporario) { Remove-Item -LiteralPath $temporario -Force }
    }
}
