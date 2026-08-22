@echo off
setlocal
title ShortsFlow AI - YouTube Auth Automatico
color 0B

echo ======================================================
echo  ShortsFlow AI - YouTube Auth Automatico
echo  Baixando SEMPRE a versao mais recente do GitHub
echo ======================================================
echo.

set "SCRIPT=%TEMP%\ShortsFlow-CONFIGURAR-YOUTUBE-AUTH.ps1"
set "URL=https://raw.githubusercontent.com/RuanMarcos38/Youtube/main/CONFIGURAR-YOUTUBE-AUTH.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%SCRIPT%' -ErrorAction Stop; exit 0 } catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
  echo.
  echo ERRO: nao foi possivel baixar o script atualizado do GitHub.
  pause
  exit /b 1
)

echo Script atualizado baixado com sucesso.
echo Iniciando configuracao...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Modo Auto
set "RC=%ERRORLEVEL%"

del /q "%SCRIPT%" >nul 2>&1
exit /b %RC%
