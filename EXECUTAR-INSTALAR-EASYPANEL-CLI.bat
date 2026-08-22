@echo off
setlocal
title ShortsFlow - Instalar/Conectar EasyPanel CLI
color 0B
cd /d "%~dp0"

if not exist "%~dp0INSTALAR-E-CONECTAR-EASYPANEL-CLI.ps1" (
  echo ERRO: INSTALAR-E-CONECTAR-EASYPANEL-CLI.ps1 nao encontrado.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALAR-E-CONECTAR-EASYPANEL-CLI.ps1"
exit /b %ERRORLEVEL%
