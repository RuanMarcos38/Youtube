param(
    [string]$CookiesFile = "",
    [ValidateSet("Auto", "Firefox", "Arquivo")]
    [string]$Modo = "Auto"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ScriptVersion = "2.2"
$TempDir = Join-Path $env:TEMP "ShortsFlow-YouTube-Auth"
$TempCookies = Join-Path $TempDir "youtube-cookies.txt"
$FirefoxProfiles = Join-Path $env:APPDATA "Mozilla\Firefox\Profiles"
$TestVideo = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-YtDlpPath {
    $cmd = Get-Command yt-dlp -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $candidate = Get-ChildItem -Path $wingetRoot -Filter "yt-dlp.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($candidate) {
            return $candidate
        }
    }

    Write-Step "Instalando yt-dlp automaticamente"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "yt-dlp nao foi encontrado e o winget nao esta disponivel."
    }

    & winget install --id yt-dlp.yt-dlp -e --accept-package-agreements --accept-source-agreements --silent | Out-Host
    Start-Sleep -Seconds 2

    if (Test-Path $wingetRoot) {
        $candidate = Get-ChildItem -Path $wingetRoot -Filter "yt-dlp.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command yt-dlp -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    throw "O yt-dlp foi instalado, mas nao foi localizado. Execute novamente o arquivo automatico."
}

function Get-FirefoxPath {
    # IMPORTANT: return the full string directly. Using $candidates[0] when
    # PowerShell collapses a one-item array to a string returns only the first
    # character (for example 'C'), which caused Start-Process to fail.
    $roots = @()
    if ($env:ProgramFiles) { $roots += $env:ProgramFiles }
    if (${env:ProgramFiles(x86)}) { $roots += ${env:ProgramFiles(x86)} }
    if ($env:LOCALAPPDATA) { $roots += $env:LOCALAPPDATA }

    foreach ($root in $roots) {
        $candidate = Join-Path $root "Mozilla Firefox\firefox.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $registryKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
    )
    foreach ($key in $registryKeys) {
        try {
            $item = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
            $path = [string]$item.'(default)'
            if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
                return (Resolve-Path -LiteralPath $path).Path
            }
        } catch {}
    }

    $cmd = Get-Command firefox.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source -PathType Leaf)) {
        return $cmd.Source
    }

    return $null
}

function Ensure-Firefox {
    $firefox = Get-FirefoxPath
    if ($firefox) {
        Write-Host "Firefox localizado: $firefox" -ForegroundColor Green
        return $firefox
    }

    Write-Step "Instalando Firefox automaticamente para evitar o bloqueio DPAPI do Chrome"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Firefox nao foi encontrado e o winget nao esta disponivel."
    }

    & winget install --id Mozilla.Firefox -e --accept-package-agreements --accept-source-agreements --silent | Out-Host
    Start-Sleep -Seconds 3

    $firefox = Get-FirefoxPath
    if (-not $firefox) {
        throw "Firefox foi instalado, mas o executavel nao foi localizado. Execute novamente o arquivo automatico."
    }

    Write-Host "Firefox localizado apos instalacao: $firefox" -ForegroundColor Green
    return $firefox
}

function Prepare-FirefoxSession([string]$FirefoxPath) {
    if (-not $FirefoxPath -or -not (Test-Path -LiteralPath $FirefoxPath -PathType Leaf)) {
        throw "Caminho do Firefox invalido: $FirefoxPath"
    }

    Write-Step "Abrindo o YouTube no Firefox"
    Write-Host "Executavel: $FirefoxPath" -ForegroundColor DarkGray

    try {
        Start-Process -FilePath $FirefoxPath -ArgumentList @("-new-window", "https://www.youtube.com/") -ErrorAction Stop | Out-Null
    } catch {
        throw "Nao foi possivel abrir o Firefox em '$FirefoxPath': $($_.Exception.Message)"
    }

    Write-Host "`nIMPORTANTE: o OAuth verde 'YouTube conectado' da plataforma nao e o mesmo que a sessao de download do yt-dlp." -ForegroundColor Yellow
    Write-Host "No Firefox, confirme que o YouTube mostra sua conta logada." -ForegroundColor White
    Write-Host "Se pedir login, entre normalmente na sua conta do YouTube." -ForegroundColor White
    [void](Read-Host "Quando o YouTube estiver LOGADO no Firefox, pressione ENTER aqui")

    Write-Step "Fechando o Firefox para liberar o banco de cookies"
    Get-Process firefox -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

function Test-NetscapeCookies([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $info = Get-Item -LiteralPath $Path
    if ($info.Length -lt 20 -or $info.Length -gt 2000000) { return $false }

    $lines = Get-Content -LiteralPath $Path -ErrorAction Stop
    if (-not $lines -or $lines.Count -lt 2) { return $false }
    if ([string]$lines[0] -notmatch "Cookie File") { return $false }

    $youtubeLine = $lines | Where-Object { $_ -match "youtube\.com" -and $_ -match "`t" } | Select-Object -First 1
    return [bool]$youtubeLine
}

function Test-LikelyLoggedIn([string]$Path) {
    $text = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
    return ($text -match "(?im)`t(SAPISID|__Secure-3PAPISID|LOGIN_INFO|SID)`t")
}

function Select-CookiesFile {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Selecione o cookies.txt exportado do YouTube"
    $dialog.Filter = "cookies.txt (*.txt)|*.txt|Todos os arquivos (*.*)|*.*"
    $dialog.Multiselect = $false
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Nenhum arquivo foi selecionado."
    }
    return $dialog.FileName
}

function Export-FirefoxCookies([string]$YtDlp) {
    if (-not (Test-Path -LiteralPath $FirefoxProfiles)) {
        return $null
    }

    $profiles = @(Get-ChildItem -LiteralPath $FirefoxProfiles -Directory -ErrorAction SilentlyContinue)
    if ($profiles.Count -eq 0) {
        return $null
    }

    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    Remove-Item -LiteralPath $TempCookies -Force -ErrorAction SilentlyContinue

    Write-Step "Extraindo cookies do Firefox com yt-dlp"
    $output = & $YtDlp --cookies-from-browser firefox --cookies $TempCookies --skip-download --no-warnings --ignore-errors $TestVideo 2>&1 | Out-String

    if (Test-NetscapeCookies $TempCookies) {
        return $TempCookies
    }

    if ($output) {
        Write-Host ($output.Trim()) -ForegroundColor DarkGray
    }
    return $null
}

function Copy-SecretToClipboard([string]$Value) {
    try {
        Set-Clipboard -Value $Value -ErrorAction Stop
    } catch {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.Clipboard]::SetText($Value)
    }
}

try {
    Clear-Host
    Write-Host "======================================================" -ForegroundColor DarkCyan
    Write-Host " ShortsFlow AI - YouTube Auth v$ScriptVersion" -ForegroundColor Cyan
    Write-Host " FIREFOX / cookies.txt - NAO USA CHROME" -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor DarkCyan
    Write-Host "Este utilitario NAO altera senhas, OAuth, Chrome ou outros projetos."
    Write-Host "Ele gera YTDLP_COOKIES_B64 localmente e copia o valor para a area de transferencia."

    $ytDlp = Get-YtDlpPath
    Write-Host "yt-dlp: $ytDlp" -ForegroundColor Green

    $selected = $null
    if ($CookiesFile) {
        $selected = (Resolve-Path -LiteralPath $CookiesFile).Path
    } elseif ($Modo -eq "Arquivo") {
        $selected = Select-CookiesFile
    } else {
        $firefox = Ensure-Firefox
        Prepare-FirefoxSession $firefox
        $selected = Export-FirefoxCookies $ytDlp
        if (-not $selected) {
            throw "Nao foi possivel obter cookies validos do Firefox. Confirme que o YouTube ficou logado no Firefox e execute novamente."
        }
    }

    Write-Step "Validando cookies.txt"
    if (-not (Test-NetscapeCookies $selected)) {
        throw "O arquivo selecionado nao e um cookies.txt Netscape valido do youtube.com."
    }
    if (-not (Test-LikelyLoggedIn $selected)) {
        throw "Os cookies existem, mas nao foi detectada uma sessao autenticada do YouTube."
    }

    $bytes = [System.IO.File]::ReadAllBytes($selected)
    $base64 = [Convert]::ToBase64String($bytes)
    $roundTrip = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($base64))
    if ($roundTrip -notmatch "Cookie File" -or $roundTrip -notmatch "youtube\.com") {
        throw "Falha ao validar o Base64 gerado."
    }

    Copy-SecretToClipboard $base64

    Write-Host "`n======================================================" -ForegroundColor Green
    Write-Host " [OK] YTDLP_COOKIES_B64 GERADO COM SUCESSO" -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor Green
    Write-Host "O codigo ja esta COPIADO na area de transferencia." -ForegroundColor White
    Write-Host "Tamanho do codigo: $($base64.Length) caracteres." -ForegroundColor DarkGray
    Write-Host "`nEasyPanel: r2rmarketingdigital -> shortsia -> Ambiente -> YTDLP_COOKIES_B64" -ForegroundColor Cyan
    Write-Host "Cole com CTRL+V, salve e execute Force Rebuild/Implantar." -ForegroundColor White
    Write-Host "Nao apague nem altere nenhuma outra variavel." -ForegroundColor Yellow

    if ($selected -eq $TempCookies) {
        Remove-Item -LiteralPath $TempCookies -Force -ErrorAction SilentlyContinue
    }

    Write-Host "`nIMPORTANTE: nao envie o codigo Base64 em chat, GitHub ou print." -ForegroundColor Red
    [void](Read-Host "Pressione ENTER para fechar")
    exit 0
} catch {
    Write-Host "`nERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Nenhuma credencial foi alterada." -ForegroundColor Yellow
    [void](Read-Host "Pressione ENTER para fechar")
    exit 1
}
