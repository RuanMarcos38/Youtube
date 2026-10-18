$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$taskDestination = Join-Path $env:LOCALAPPDATA 'ShortsFlow-Automatico'
$taskPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Python nao encontrado. Mantenha o Codex instalado e execute novamente.' }
$taskForm = New-Object Windows.Forms.Form
$taskForm.Text = 'ShortsFlow - Ativar conexao automatica'
$taskForm.Size = New-Object Drawing.Size(630,290)
$taskForm.StartPosition = 'CenterScreen'
$taskLabel = New-Object Windows.Forms.Label
$taskLabel.Text = 'No painel, abra /conexao-automatica e autorize este computador. Cole abaixo o codigo. Ele sera protegido pelo Windows e usado ao entrar na sua conta.'
$taskLabel.SetBounds(20,20,570,60)
$taskInput = New-Object Windows.Forms.TextBox
$taskInput.UseSystemPasswordChar = $true
$taskInput.SetBounds(20,90,570,28)
$taskButton = New-Object Windows.Forms.Button
$taskButton.Text = 'Ativar inicio automatico'
$taskButton.SetBounds(180,140,250,36)
$taskStatus = New-Object Windows.Forms.Label
$taskStatus.SetBounds(20,185,570,50)
$taskForm.Controls.AddRange(@($taskLabel,$taskInput,$taskButton,$taskStatus))
$taskButton.Add_Click({
    try {
        $taskCode = $taskInput.Text.Trim()
        if ($taskCode -notmatch '^[A-Za-z0-9_-]{43}$') { $taskStatus.Text = 'Cole um codigo completo de conexao automatica.'; return }
        New-Item -ItemType Directory -Path $taskDestination -Force | Out-Null
        # Restrict the install directory to this Windows user and SYSTEM.
        $taskAcl = New-Object Security.AccessControl.DirectorySecurity
        $taskAcl.SetAccessRuleProtection($true,$false)
        $taskSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
        foreach ($taskIdentity in @($taskSid, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
            $taskRule = New-Object Security.AccessControl.FileSystemAccessRule($taskIdentity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
            $taskAcl.AddAccessRule($taskRule)
        }
        Set-Acl -LiteralPath $taskDestination -AclObject $taskAcl
        foreach ($taskFile in @('residential_client.py','Start-ShortsFlow.ps1','Desativar-ShortsFlow.ps1')) {
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot $taskFile) -Destination $taskDestination -Force
        }
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot '_deps') -Destination $taskDestination -Recurse -Force
        $taskSecure = ConvertTo-SecureString $taskCode -AsPlainText -Force
        $taskSecure | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $taskDestination 'authorization.dpapi') -Encoding ascii
        $taskSecure.Dispose()
        $taskCode = $null
        $taskInput.Clear()
        @{python=$taskPython} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskDestination 'runtime.json') -Encoding utf8
        $taskRunner = Join-Path $taskDestination 'Start-ShortsFlow.ps1'
        $taskStartup = Join-Path ([Environment]::GetFolderPath('Startup')) 'ShortsFlow-Automatico.vbs'
        $taskLaunch = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $taskRunner + '"'
        $taskVbs = 'CreateObject("WScript.Shell").Run "' + $taskLaunch.Replace('"','""') + '", 0, False'
        Set-Content -LiteralPath $taskStartup -Value $taskVbs -Encoding unicode
        Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $taskStartup + '"') -WindowStyle Hidden
        $taskStatus.Text = 'Ativado. O cliente inicia em segundo plano ao entrar no Windows e reconecta apos quedas de internet.'
        $taskButton.Enabled = $false
    } catch {
        $taskStatus.Text = 'Nao foi possivel concluir. Verifique a permissao de gravacao na Inicializacao do Windows.'
    }
})
$taskForm.AcceptButton = $taskButton
[void]$taskForm.ShowDialog()
