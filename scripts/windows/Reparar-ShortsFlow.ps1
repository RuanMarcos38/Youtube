$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$taskDestination = Join-Path $env:LOCALAPPDATA 'ShortsFlow-Automatico'
$taskForm = New-Object Windows.Forms.Form
$taskForm.Text = 'ShortsFlow - Reparar conexao automatica'
$taskForm.Size = New-Object Drawing.Size(660,260)
$taskForm.StartPosition = 'CenterScreen'
$taskLabel = New-Object Windows.Forms.Label
$taskLabel.SetBounds(20,20,600,55)
$taskLabel.Text = 'Este reparo corrige a leitura da autorizacao ja salva, sem alterar o codigo, as contas ou a inicializacao registrada.'
$taskButton = New-Object Windows.Forms.Button
$taskButton.Text = 'Reparar e verificar conexao'
$taskButton.SetBounds(170,85,290,38)
$taskStatus = New-Object Windows.Forms.Label
$taskStatus.SetBounds(20,140,600,65)
$taskStatus.Text = 'Pronto para reparar. Nao e necessario colar codigo novamente.'
$taskForm.Controls.AddRange(@($taskLabel,$taskButton,$taskStatus))
$taskTimer = New-Object Windows.Forms.Timer
$taskTimer.Interval = 1000
$script:taskStarted = $null
$taskButton.Add_Click({
    try {
        $taskCredential = Join-Path $taskDestination 'authorization.dpapi'
        if (-not (Test-Path -LiteralPath $taskCredential)) { throw 'Autorizacao nao encontrada. Execute o instalador primeiro.' }
        $taskSecure = (Get-Content -LiteralPath $taskCredential -Raw).Trim() | ConvertTo-SecureString
        $taskSecure.Dispose()
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Start-ShortsFlow.ps1') -Destination (Join-Path $taskDestination 'Start-ShortsFlow.ps1') -Force
        $script:taskStarted = Get-Date
        Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $taskDestination 'Start-ShortsFlow.ps1') + '"') -WindowStyle Hidden
        $taskButton.Enabled = $false
        $taskStatus.Text = 'Correcao aplicada. Aguardando confirmacao da conexao...'
        $taskTimer.Start()
    } catch {
        $taskStatus.Text = 'Reparo nao aplicado. Tipo da falha: ' + $_.Exception.GetType().Name + '. Nenhum codigo foi alterado.'
        $taskStatus.ForeColor = [Drawing.Color]::Red
    }
})
$taskTimer.Add_Tick({
    try {
        $taskLog = Join-Path $taskDestination 'connection.log'
        if (Test-Path -LiteralPath $taskLog) {
            $taskLogFile = Get-Item -LiteralPath $taskLog
            if ($taskLogFile.LastWriteTime -ge $script:taskStarted) {
                $taskText = Get-Content -LiteralPath $taskLog -Raw
                if ($taskText -match 'residencial ativa') {
                    $taskTimer.Stop()
                    $taskStatus.ForeColor = [Drawing.Color]::Green
                    $taskStatus.Text = 'CONECTADO. O cliente esta funcionando em segundo plano. A inicializacao automatica existente foi preservada.'
                    return
                }
                if ($taskText -match 'Autorizacao recusada') {
                    $taskTimer.Stop()
                    $taskStatus.ForeColor = [Drawing.Color]::Red
                    $taskStatus.Text = 'A leitura foi corrigida, mas o servidor recusou o codigo salvo. Gere um codigo na pagina /conexao-automatica e execute o instalador corrigido.'
                    return
                }
                if ($taskText -match 'Falha ao iniciar|Cliente encerrado') {
                    $taskTimer.Stop()
                    $taskStatus.ForeColor = [Drawing.Color]::Red
                    $taskStatus.Text = 'O cliente encerrou antes de conectar. Codigo de diagnostico: ' + (($taskText -split "`r?`n" | Where-Object {$_ -match 'Codigo:|Falha ao iniciar'}) -join ' ')
                    return
                }
            }
        }
        if (((Get-Date) - $script:taskStarted).TotalSeconds -gt 45) {
            $taskTimer.Stop()
            $taskStatus.Text = 'A correcao foi aplicada. A conexao ainda nao foi confirmada; o cliente continuara tentando automaticamente.'
        }
    } catch {
        $taskTimer.Stop()
        $taskStatus.Text = 'Nao foi possivel ler o estado. Verifique a conexao no painel do ShortsFlow.'
    }
})
$taskForm.Add_FormClosing({ $taskTimer.Stop() })
$taskForm.AcceptButton = $taskButton
[void]$taskForm.ShowDialog()
