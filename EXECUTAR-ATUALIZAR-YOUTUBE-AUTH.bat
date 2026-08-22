@echo off
setlocal
title ShortsFlow - Renovar Download YouTube
color 0B
cd /d "%~dp0"

echo ==========================================================
echo  ShortsFlow AI - RENOVAR DOWNLOAD YOUTUBE
echo  Atualiza direto pelo painel administrador
echo ==========================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ATUALIZAR-YOUTUBE-AUTH-PAINEL.ps1"
exit /b %ERRORLEVEL%
