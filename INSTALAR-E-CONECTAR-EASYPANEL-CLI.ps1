param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$PanelUrl = "https://ke4n49.easypanel.host"
$Profile = "production"

function Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Find-EasyPanelCli {
    foreach ($name in @("easypanel.exe","easypanel","ep.exe","ep")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) { return $cmd.Source }
    }

    $paths = @()
    if ($env:USERPROFILE) {
        $paths += (Join-Path $env:USERPROFILE ".local\bin\easypanel.exe")
        $paths += (Join-Path $env:USERPROFILE "bin\easypanel.exe")
    }
    if ($env:LOCALAPPDATA) {
        $paths += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\easypanel.exe")
    }

    foreach ($path in $paths) {
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    return $null
}

function Find-Bash {
    $cmd = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }

    $paths = @()
    if ($env:ProgramFiles) {
        $paths += (Join-Path $env:ProgramFiles "Git\bin\bash.exe")
    }
    if (${env:ProgramFiles(x86)}) {
        $paths += (Join-Path ${env:ProgramFiles(x86)} "Git\bin\bash.exe")
    }

    foreach ($path in $paths) {
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    return $null
}

function Ensure-GitBash {
    $bash = Find-Bash
    if ($bash) { return $bash }

    Step "Instalando Git for Windows para executar o instalador oficial do EasyPanel CLI"
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Git Bash nao foi encontrado e o winget nao esta disponivel."
    }

    & winget.exe install --id Git.Git -e --accept-package-agreements --accept-source-agreements --silent | Out-Host
    Start-Sleep -Seconds 5

    $bash = Find-Bash
    if (-not $bash) {
        throw "Git foi instalado, mas bash.exe ainda nao foi localizado. Feche esta janela, abra novamente e execute o arquivo outra vez."
    }
    return $bash
}

function Install-EasyPanelCli {
    $cli = Find-EasyPanelCli
    if ($cli) { return $cli }

    $bash = Ensure-GitBash
    Step "Instalando o EasyPanel CLI pelo instalador oficial"
    & $bash -lc "curl -fsSL https://get.easypanel.io/cli | sh" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "O instalador oficial do EasyPanel CLI retornou erro."
    }

    Start-Sleep -Seconds 2
    $cli = Find-EasyPanelCli
    if (-not $cli -and $env:USERPROFILE) {
        $candidateRoot = Join-Path $env:USERPROFILE ".local"
        if (Test-Path $candidateRoot) {
            $found = Get-ChildItem -Path $candidateRoot -Filter "easypanel.exe" -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
            if ($found) { $cli = $found }
        }
    }

    if (-not $cli) {
        throw "O EasyPanel CLI foi instalado, mas nao foi localizado automaticamente. Abra um novo PowerShell e execute easypanel version."
    }
    return $cli
}

try {
    Clear-Host
    Write-Host "========================================================" -ForegroundColor DarkCyan
    Write-Host " ShortsFlow AI - Instalar/Conectar EasyPanel CLI" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor DarkCyan

    $cli = Install-EasyPanelCli
    Write-Host "EasyPanel CLI: $cli" -ForegroundColor Green

    Step "Verificando perfis conectados"
    $current = (& $cli server current 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $current) {
        Write-Host "Servidor atual: $current" -ForegroundColor Green
        & $cli server check $current | Out-Host
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n[OK] EasyPanel CLI instalado e conectado." -ForegroundColor Green
            [void](Read-Host "Pressione ENTER para fechar")
            exit 0
        }
    }

    Write-Host "`nO CLI esta instalado, mas ainda falta conectar o servidor." -ForegroundColor Yellow
    Write-Host "Abra no EasyPanel: Settings -> Server -> Users" -ForegroundColor White
    Write-Host "Clique em Generate API Key para o seu usuario." -ForegroundColor White
    Write-Host "Depois clique em Connect -> CLI." -ForegroundColor White
    try { Start-Process $PanelUrl | Out-Null } catch {}

    Write-Host "`nQuando estiver com a API Key pronta, volte aqui." -ForegroundColor Cyan
    [void](Read-Host "Pressione ENTER para iniciar a conexao")

    Write-Host "`nA proxima etapa vai pedir a API Key sem exibi-la na tela." -ForegroundColor Yellow
    & $cli server add $Profile $PanelUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Nao foi possivel conectar o EasyPanel CLI ao servidor."
    }

    & $cli server check $Profile | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "O perfil foi criado, mas a validacao do servidor falhou."
    }

    Write-Host "`n========================================================" -ForegroundColor Green
    Write-Host " [OK] EASYPANEL CLI INSTALADO E CONECTADO" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "Agora execute novamente o pacote de correcao final do ShortsFlow." -ForegroundColor White
    [void](Read-Host "Pressione ENTER para fechar")
    exit 0
}
catch {
    Write-Host "`nERRO: $($_.Exception.Message)" -ForegroundColor Red
    [void](Read-Host "Pressione ENTER para fechar")
    exit 1
}
