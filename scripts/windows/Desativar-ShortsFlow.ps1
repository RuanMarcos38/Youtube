$ErrorActionPreference = 'Stop'
$taskStartup = Join-Path ([Environment]::GetFolderPath('Startup')) 'ShortsFlow-Automatico.vbs'
if (Test-Path -LiteralPath $taskStartup) { Remove-Item -LiteralPath $taskStartup }
Write-Host 'Inicio automatico desativado. Para revogar a conexao atual, use Configuracoes > Desativar conexao residencial no ShortsFlow.'
