param(
    [string]$CookiesFile = "",
    [ValidateSet("Auto", "Firefox", "Arquivo")]
    [string]$Modo = "Auto"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

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

    throw "yt-dlp nao foi encontrado. Instale com: winget install yt-dlp.yt-dlp"
}

function Test-NetscapeCookies([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    $info = Get-Item -LiteralPath $Path
    if ($info.Length -lt 20 -or $info.Length -gt 2000000) {
        return $false
    }

    $lines = Get-Content -LiteralPath $Path -ErrorAction Stop
    if (-not $lines -or $lines.Count -lt 2) {
        return $false
    }

    $first = [string]$lines[0]
    if ($first -notmatch "Cookie File") {
        return $false
    }

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
    if (-not (Test-Path $FirefoxProfiles)) {
        return $null
    }

    $profiles = Get-ChildItem -LiteralPath $FirefoxProfiles -Directory -ErrorAction SilentlyContinue
    if (-not $profiles) {
        return $null
    }

    if (Get-Process firefox -ErrorAction SilentlyContinue) {
        Write-Host "O Firefox esta aberto. Feche todas as janelas do Firefox e pressione ENTER." -ForegroundColor Yellow
        [void](Read-Host)
    }

    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    Remove-Item -LiteralPath $TempCookies -Force -ErrorAction SilentlyContinue

    Write-Step "Tentando exportar os cookies pelo Firefox (metodo recomendado pelo yt-dlp no Windows)"
    $output = & $YtDlp --cookies-from-browser firefox --cookies $TempCookies --skip-download --no-warnings --ignore-errors $TestVideo 2>&1 | Out-String

    if (Test-NetscapeCookies $TempCookies) {
        return $TempCookies
    }

    if ($output -match "decrypt|DPAPI|cookie") {
        Write-Host "A exportacao automatica do Firefox nao ficou valida." -ForegroundColor Yellow
    }
    return $null
}

function Copy-SecretToClipboard([string]$Value) {
    try {
        Set-Clipboard -Value $Value -ErrorAction Stop
        return
    } catch {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.Clipboard]::SetText($Value)
    }
}

try {
    Clear-Host
    Write-Host "===============================================" -ForegroundColor DarkCyan
    Write-Host " ShortsFlow AI - Autenticacao de download YouTube" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor DarkCyan
    Write-Host "Este utilitario NAO altera senhas, OAuth, Chrome ou outros projetos."
    Write-Host "Ele somente prepara um cookies.txt autorizado para YTDLP_COOKIES_B64."

    $ytDlp = Get-YtDlpPath
    Write-Host "yt-dlp: $ytDlp" -ForegroundColor Green

    $selected = $null

    if ($CookiesFile) {
        $selected = (Resolve-Path -LiteralPath $CookiesFile).Path
    } elseif ($Modo -eq "Firefox") {
        $selected = Export-FirefoxCookies $ytDlp
        if (-not $selected) {
            throw "Nao foi possivel obter um cookies.txt valido do Firefox. Confirme que voce esta logado no YouTube pelo Firefox."
        }
    } elseif ($Modo -eq "Arquivo") {
        $selected = Select-CookiesFile
    } else {
        $selected = Export-FirefoxCookies $ytDlp
        if (-not $selected) {
            Write-Host "`nO Chrome atual usa App-Bound Encryption. O erro 'Failed to decrypt with DPAPI' e conhecido e nao e corrigido fechando o Chrome." -ForegroundColor Yellow
            Write-Host "Por seguranca, este script NAO desativa protecoes do Chrome e NAO tenta extrair cookies protegidos diretamente." -ForegroundColor Yellow
            Write-Host "`nNo Chrome, use a extensao recomendada pelo proprio projeto yt-dlp: Get cookies.txt LOCALLY." -ForegroundColor White
            Write-Host "1. Abra o YouTube e confirme que esta logado." -ForegroundColor White
            Write-Host "2. Exporte SOMENTE os cookies de youtube.com no formato Netscape cookies.txt." -ForegroundColor White
            Write-Host "3. Salve como cookies.txt." -ForegroundColor White
            Write-Host "4. Volte a esta janela e selecione o arquivo." -ForegroundColor White
            try {
                Start-Process "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
                Start-Process "https://www.youtube.com/"
            } catch {}
            [void](Read-Host "Pressione ENTER depois de exportar o cookies.txt")
            $selected = Select-CookiesFile
        }
    }

    Write-Step "Validando cookies.txt"
    if (-not (Test-NetscapeCookies $selected)) {
        throw "O arquivo selecionado nao e um cookies.txt Netscape valido do youtube.com. Exporte novamente os cookies do YouTube."
    }

    if (-not (Test-LikelyLoggedIn $selected)) {
        throw "O arquivo parece conter cookies do YouTube, mas nao uma sessao autenticada. Entre no YouTube e exporte novamente."
    }

    $bytes = [System.IO.File]::ReadAllBytes($selected)
    $base64 = [Convert]::ToBase64String($bytes)

    # Validacao final sem exibir o segredo.
    $roundTrip = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($base64))
    if ($roundTrip -notmatch "Cookie File" -or $roundTrip -notmatch "youtube\.com") {
        throw "Falha ao validar o Base64 gerado."
    }

    Copy-SecretToClipboard $base64

    Write-Host "`n[OK] YTDLP_COOKIES_B64 foi gerado e copiado para a area de transferencia." -ForegroundColor Green
    Write-Host "O valor completo NAO foi exibido na tela para proteger sua sessao." -ForegroundColor Green
    Write-Host "`nNo EasyPanel, altere SOMENTE o servico r2rmarketingdigital/shortsia:" -ForegroundColor Cyan
    Write-Host "Ambiente -> YTDLP_COOKIES_B64 -> cole o valor -> Salvar -> Implantar/Force Rebuild" -ForegroundColor White
    Write-Host "Nao apague nem altere as outras variaveis existentes." -ForegroundColor Yellow
    Write-Host "`nDepois, valide em:" -ForegroundColor Cyan
    Write-Host "https://shorts.r2rmarketingdigital.com.br/api/health" -ForegroundColor White
    Write-Host "O campo youtube_download_mode deve mudar de guest para cookies." -ForegroundColor White

    if ($selected -eq $TempCookies) {
        Remove-Item -LiteralPath $TempCookies -Force -ErrorAction SilentlyContinue
    }

    Write-Host "`nIMPORTANTE: trate cookies.txt e o valor Base64 como senha. Nao envie em chat, GitHub ou print." -ForegroundColor Red
    [void](Read-Host "Pressione ENTER para fechar")
    exit 0
} catch {
    Write-Host "`nERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Nenhuma credencial foi alterada." -ForegroundColor Yellow
    [void](Read-Host "Pressione ENTER para fechar")
    exit 1
}
