$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskMutex = New-Object System.Threading.Mutex($false, 'Local\ShortsFlow-Automatico')
if (-not $taskMutex.WaitOne(0)) { exit 0 }
try {
    $taskCredential = Join-Path $taskRoot 'authorization.dpapi'
    if (-not (Test-Path -LiteralPath $taskCredential)) { exit 2 }
    $taskSecure = (Get-Content -LiteralPath $taskCredential -Raw).Trim() | ConvertTo-SecureString
    $taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecure)
    try { $taskCode = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer) }
    $taskConfig = Get-Content -LiteralPath (Join-Path $taskRoot 'runtime.json') -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $taskConfig.python)) { throw 'Python indisponivel. Execute o instalador novamente.' }
    $taskStart = New-Object Diagnostics.ProcessStartInfo
    $taskStart.FileName = $taskConfig.python
    $taskStart.Arguments = '-u -B "' + (Join-Path $taskRoot 'residential_client.py') + '" --code-stdin --reconnect'
    $taskStart.WorkingDirectory = $taskRoot
    $taskStart.UseShellExecute = $false
    $taskStart.CreateNoWindow = $true
    $taskStart.RedirectStandardInput = $true
    $taskStart.RedirectStandardOutput = $true
    $taskStart.RedirectStandardError = $true
    $taskProcess = New-Object Diagnostics.Process
    $taskProcess.StartInfo = $taskStart
    [void]$taskProcess.Start()
    $taskProcess.StandardInput.WriteLine($taskCode)
    $taskProcess.StandardInput.Close()
    $taskCode = $null
    $taskSecure.Dispose()
    # Drain both pipes asynchronously. Only fixed client status messages are retained.
    $taskErrorRead = $taskProcess.StandardError.ReadToEndAsync()
    $taskLog = Join-Path $taskRoot 'connection.log'
    Set-Content -LiteralPath $taskLog -Value ('Iniciado em ' + (Get-Date -Format s)) -Encoding utf8
    while (-not $taskProcess.StandardOutput.EndOfStream) {
        $taskLine = $taskProcess.StandardOutput.ReadLine()
        if ($taskLine -match 'residencial ativa|Tentando reconectar|Autorizacao recusada') {
            if ((Get-Item -LiteralPath $taskLog).Length -gt 65536) { Clear-Content -LiteralPath $taskLog }
            Add-Content -LiteralPath $taskLog -Value ((Get-Date -Format s) + ' ' + $taskLine) -Encoding utf8
        }
    }
    $taskProcess.WaitForExit()
    Add-Content -LiteralPath $taskLog -Value ('Cliente encerrado. Codigo: ' + $taskProcess.ExitCode) -Encoding utf8
    exit $taskProcess.ExitCode
} catch {
    # Never serialize exception details or decrypted credentials to a log.
    Set-Content -LiteralPath (Join-Path $taskRoot 'connection.log') -Value 'Falha ao iniciar. Execute o instalador para verificar a autorizacao.' -Encoding utf8
    exit 1
} finally {
    $taskMutex.ReleaseMutex()
    $taskMutex.Dispose()
}
