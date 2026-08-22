param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$Target = "r2rmarketingdigital/shortsia"
$HealthUrl = "https://shorts.r2rmarketingdigital.com.br/api/health"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Find-EasyPanelCli {
    foreach ($name in @("easypanel.exe", "easypanel", "ep.exe", "ep")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            return $cmd.Source
        }
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\easypanel.exe"),
        (Join-Path $env:USERPROFILE ".local\bin\easypanel.exe"),
        (Join-Path $env:USERPROFILE "bin\easypanel.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}

function Find-EnvString($Node) {
    if ($null -eq $Node -or $Node -is [string]) {
        return $null
    }

    if ($Node -is [System.Collections.IEnumerable] -and -not ($Node -is [pscustomobject])) {
        foreach ($item in $Node) {
            $found = Find-EnvString $item
            if ($found) { return $found }
        }
        return $null
    }

    foreach ($property in $Node.PSObject.Properties) {
        if ($property.Name -eq "env" -and $property.Value -is [string]) {
            $value = [string]$property.Value
            if ($value -match "(?m)^(APP_NAME|ENVIRONMENT|OPENAI_API_KEY|YOUTUBE_API_KEY)=") {
                return $value
            }
        }
        $found = Find-EnvString $property.Value
        if ($found) { return $found }
    }
    return $null
}

function Assert-ClipboardCookie {
    $value = (Get-Clipboard -Raw -ErrorAction Stop).Trim()
    if (-not $value) {
        throw "A area de transferencia esta vazia. Gere o YTDLP_COOKIES_B64 primeiro."
    }

    $compact = $value -replace "\s", ""
    try {
        $raw = [Convert]::FromBase64String($compact)
        $text = [Text.Encoding]::UTF8.GetString($raw)
    } catch {
        throw "O conteudo atual da area de transferencia nao e Base64 valido."
    }

    if ($text -notmatch "Cookie File" -or $text -notmatch "youtube\.com") {
        throw "O Base64 da area de transferencia nao representa um cookies.txt do YouTube."
    }
    return $compact
}

try {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor DarkCyan
    Write-Host " ShortsFlow AI - Aplicar YTDLP no EasyPanel" -ForegroundColor Cyan
    Write-Host " ALVO UNICO: r2rmarketingdigital/shortsia" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor DarkCyan

    Write-Step "Validando o YTDLP_COOKIES_B64 da area de transferencia"
    $cookieBase64 = Assert-ClipboardCookie
    Write-Host "[OK] Cookie valido detectado. O segredo nao sera exibido." -ForegroundColor Green

    Write-Step "Localizando o EasyPanel CLI"
    $cli = Find-EasyPanelCli
    if (-not $cli) {
        throw (
            "EasyPanel CLI nao foi encontrado. No EasyPanel abra Settings -> Server -> Users -> Connect -> CLI, " +
            "execute o comando mostrado uma vez e depois rode este arquivo novamente."
        )
    }
    Write-Host "EasyPanel CLI: $cli" -ForegroundColor Green

    $profile = (& $cli server current 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $profile) {
        throw "O EasyPanel CLI existe, mas nenhum servidor esta conectado. Use Connect -> CLI no painel e execute novamente."
    }
    Write-Host "Servidor atual: $profile" -ForegroundColor Green

    $check = & $cli server check $profile 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "A conexao do EasyPanel CLI nao esta valida. Refaça Connect -> CLI e execute novamente."
    }

    & $cli server refresh $profile 2>&1 | Out-Null

    Write-Step "Lendo as variaveis atuais do shortsia sem altera-las"
    $inspectRaw = & $cli --show-secrets app inspect $Target --format json 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel inspecionar $Target. Nenhuma alteracao foi feita."
    }

    try {
        $inspect = $inspectRaw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "O EasyPanel respondeu, mas o inspect nao veio em JSON valido. Nenhuma alteracao foi feita."
    }

    $currentEnv = Find-EnvString $inspect
    if (-not $currentEnv) {
        throw "Nao consegui localizar o ambiente atual do shortsia. Por seguranca, nenhuma variavel foi sobrescrita."
    }

    $preserved = @($currentEnv -split "`r?`n" | Where-Object { $_ -notmatch '^\s*YTDLP_COOKIES_B64\s*=' })
    $newEnv = (($preserved + "YTDLP_COOKIES_B64=$cookieBase64") -join "`n").Trim()

    $tempJson = Join-Path $env:TEMP "shortsflow-easypanel-env.json"
    $payload = @{ env = $newEnv } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($tempJson, $payload, (New-Object Text.UTF8Encoding($false)))

    Write-Step "Atualizando SOMENTE YTDLP_COOKIES_B64 no shortsia"
    $update = & $cli app update-env $Target --input "@$tempJson" --format json 2>&1 | Out-String
    Remove-Item -LiteralPath $tempJson -Force -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) {
        throw "O EasyPanel recusou a atualizacao do ambiente: $($update.Trim())"
    }
    Write-Host "[OK] Variavel inserida preservando as demais configuracoes." -ForegroundColor Green

    Write-Step "Reimplantando somente o shortsia"
    $deploy = & $cli --timeout 10m app deploy $Target --format json 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "A variavel foi salva, mas o deploy falhou: $($deploy.Trim())"
    }

    Write-Step "Validando o backend publico"
    $ready = $false
    for ($i = 1; $i -le 90; $i++) {
        try {
            $health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 10
            $checks = $health.checks
            $mode = [string]$health.youtube_download_mode
            $auth = [bool]$checks.youtube_download_auth_configured
            $downloadReady = $auth
            if ($null -ne $checks.youtube_download_ready) {
                $downloadReady = [bool]$checks.youtube_download_ready
            }

            Write-Host "Tentativa $i/90 - modo=$mode auth=$auth ready=$downloadReady"
            if ($auth -and $downloadReady -and $mode -in @("cookies", "cookies+proxy")) {
                $ready = $true
                break
            }
        } catch {
            Write-Host "Tentativa $i/90 - aguardando healthcheck..."
        }
        Start-Sleep -Seconds 5
    }

    if (-not $ready) {
        throw "O deploy terminou, mas o healthcheck ainda nao confirmou o modo cookies."
    }

    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host " [OK] YTDLP_COOKIES_B64 CONFIGURADO" -ForegroundColor Green
    Write-Host " [OK] SHORTSIA REIMPLANTADO" -ForegroundColor Green
    Write-Host " [OK] YOUTUBE_DOWNLOAD_MODE = COOKIES" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "Agora crie um NOVO processamento de 10 Shorts." -ForegroundColor White
    Write-Host "Nenhum outro projeto ou servico foi alterado." -ForegroundColor Yellow
    [void](Read-Host "Pressione ENTER para fechar")
    exit 0
} catch {
    Write-Host "`nERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "O procedimento foi limitado ao servico r2rmarketingdigital/shortsia." -ForegroundColor Yellow
    [void](Read-Host "Pressione ENTER para fechar")
    exit 1
}
