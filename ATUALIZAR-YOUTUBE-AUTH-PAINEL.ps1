param(
    [string]$BaseUrl = "https://shorts.r2rmarketingdigital.com.br",
    [string]$AdminEmail = "admin@r2rmarketingdigital.com.br",
    [string]$ProxyUrl = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$TestVideo = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
$TempDir = Join-Path $env:TEMP "ShortsFlow-YouTube-Auth"
$CookieFile = Join-Path $TempDir "youtube-cookies.txt"

function Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Find-YtDlp {
    $cmd = Get-Command yt-dlp.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $found = Get-ChildItem $wingetRoot -Filter "yt-dlp.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($found) { return $found }
    }

    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "yt-dlp não foi encontrado e o winget não está disponível."
    }
    Step "Instalando yt-dlp"
    & winget.exe install --id yt-dlp.yt-dlp -e --accept-package-agreements --accept-source-agreements --silent | Out-Host
    Start-Sleep -Seconds 2
    if (Test-Path $wingetRoot) {
        $found = Get-ChildItem $wingetRoot -Filter "yt-dlp.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($found) { return $found }
    }
    throw "yt-dlp foi instalado, mas não foi localizado. Execute novamente."
}

function Find-Firefox {
    $paths = @()
    if ($env:ProgramFiles) { $paths += (Join-Path $env:ProgramFiles "Mozilla Firefox\firefox.exe") }
    if (${env:ProgramFiles(x86)}) { $paths += (Join-Path ${env:ProgramFiles(x86)} "Mozilla Firefox\firefox.exe") }
    if ($env:LOCALAPPDATA) { $paths += (Join-Path $env:LOCALAPPDATA "Mozilla Firefox\firefox.exe") }
    foreach ($path in $paths) {
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) { return (Resolve-Path -LiteralPath $path).Path }
    }
    $cmd = Get-Command firefox.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    return $null
}

function Ensure-Firefox {
    $firefox = Find-Firefox
    if ($firefox) { return $firefox }
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Firefox não foi localizado e o winget não está disponível."
    }
    Step "Instalando Firefox"
    & winget.exe install --id Mozilla.Firefox -e --accept-package-agreements --accept-source-agreements --silent | Out-Host
    Start-Sleep -Seconds 4
    $firefox = Find-Firefox
    if (-not $firefox) { throw "Firefox foi instalado, mas não foi localizado. Reinicie o Windows e tente novamente." }
    return $firefox
}

function SecureToPlain([Security.SecureString]$Secure) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-ApiErrorText($Exception) {
    try {
        $response = $Exception.Response
        if ($null -eq $response) { return $Exception.Message }
        $stream = $response.GetResponseStream()
        if ($null -eq $stream) { return $Exception.Message }
        $reader = New-Object IO.StreamReader($stream)
        $raw = $reader.ReadToEnd()
        $reader.Close()
        if ($raw) {
            try {
                $json = $raw | ConvertFrom-Json
                if ($json.detail) { return [string]$json.detail }
            } catch {}
            return $raw
        }
    } catch {}
    return $Exception.Message
}

try {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor DarkCyan
    Write-Host " ShortsFlow AI - RENOVAR DOWNLOAD YOUTUBE" -ForegroundColor Cyan
    Write-Host " Sem EasyPanel: atualiza direto pelo painel administrador" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor DarkCyan

    $yt = Find-YtDlp
    $firefox = Ensure-Firefox
    Write-Host "yt-dlp: $yt" -ForegroundColor Green
    Write-Host "Firefox: $firefox" -ForegroundColor Green

    Step "Abrindo o YouTube no Firefox"
    Start-Process -FilePath $firefox -ArgumentList @("-new-window", "https://www.youtube.com/") -ErrorAction Stop | Out-Null
    Write-Host "Confirme que o YouTube está LOGADO no Firefox." -ForegroundColor Yellow
    [void](Read-Host "Quando estiver logado, pressione ENTER aqui")

    Step "Fechando Firefox e extraindo a sessão"
    Get-Process firefox -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    Remove-Item -LiteralPath $CookieFile -Force -ErrorAction SilentlyContinue

    $result = & $yt --cookies-from-browser firefox --cookies $CookieFile --skip-download --no-warnings --ignore-errors $TestVideo 2>&1 | Out-String
    if (-not (Test-Path -LiteralPath $CookieFile -PathType Leaf)) {
        if ($result) { Write-Host $result.Trim() -ForegroundColor DarkGray }
        throw "Não foi possível extrair os cookies do Firefox. Confirme o login no YouTube e tente novamente."
    }

    $cookieText = Get-Content -LiteralPath $CookieFile -Raw -ErrorAction Stop
    if ($cookieText -notmatch "Cookie File" -or $cookieText -notmatch "youtube\.com") {
        throw "O arquivo extraído não contém uma sessão válida do YouTube."
    }
    $base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($CookieFile))
    Remove-Item -LiteralPath $CookieFile -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Sessão do Firefox gerada. O segredo não será exibido." -ForegroundColor Green

    Step "Autenticando no painel administrador ShortsFlow"
    $securePassword = Read-Host "Senha do administrador ($AdminEmail)" -AsSecureString
    $adminPassword = SecureToPlain $securePassword
    if ([string]::IsNullOrWhiteSpace($adminPassword)) { throw "Senha do administrador não informada." }

    $loginBody = @{ email = $AdminEmail; password = $adminPassword } | ConvertTo-Json -Compress
    try {
        $login = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd('/') + "/api/auth/login") -Method Post -ContentType "application/json" -Body $loginBody -SessionVariable shortsSession -TimeoutSec 30
    } catch {
        throw "Falha no login do administrador: $(Get-ApiErrorText $_.Exception)"
    } finally {
        $adminPassword = $null
        $securePassword = $null
    }
    if ($login.role -ne "superadmin") { throw "A conta informada não possui perfil superadmin." }
    Write-Host "[OK] Administrador autenticado." -ForegroundColor Green

    Step "Atualizando cookies no backend sem redeploy"
    $updatePayload = @{ cookies_b64 = $base64 }
    if (-not [string]::IsNullOrWhiteSpace($ProxyUrl)) { $updatePayload.proxy_url = $ProxyUrl.Trim() }
    $updateBody = $updatePayload | ConvertTo-Json -Compress
    try {
        $null = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd('/') + "/api/admin/download-auth") -Method Put -WebSession $shortsSession -ContentType "application/json" -Body $updateBody -TimeoutSec 60
    } catch {
        throw "Falha ao salvar a sessão no ShortsFlow: $(Get-ApiErrorText $_.Exception)"
    }
    $base64 = $null
    Write-Host "[OK] Cookies atualizados no painel." -ForegroundColor Green

    Step "Testando a sessão diretamente a partir da VPS"
    try {
        $check = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd('/') + "/api/admin/download-auth/test") -Method Post -WebSession $shortsSession -ContentType "application/json" -Body "{}" -TimeoutSec 90
    } catch {
        $detail = Get-ApiErrorText $_.Exception
        Write-Host "" 
        Write-Host "[ATENÇÃO] Os cookies foram atualizados, mas o YouTube ainda recusou o IP da VPS." -ForegroundColor Yellow
        Write-Host $detail -ForegroundColor Red
        Write-Host "Abra Administrador > Download YouTube e configure um proxy residencial/estático; depois clique em Testar download." -ForegroundColor Yellow
        [void](Read-Host "Pressione ENTER para fechar")
        exit 2
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host " [OK] DOWNLOAD DO YOUTUBE VALIDADO NA VPS" -ForegroundColor Green
    Write-Host " [OK] MODO: $($check.mode)" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "Agora novos jobs podem ser criados no ShortsFlow." -ForegroundColor White
    [void](Read-Host "Pressione ENTER para fechar")
    exit 0
}
catch {
    Write-Host ""
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Nenhuma outra credencial/projeto foi alterado." -ForegroundColor Yellow
    [void](Read-Host "Pressione ENTER para fechar")
    exit 1
}
