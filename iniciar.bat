@echo off
setlocal enabledelayedexpansion

:: Configura UTF-8 e título
chcp 65001 >nul 2>&1
title OmniPlaylist 2.0
cd /d "%~dp0"

:: Configuração de cores ANSI
set "ESC=	"
:: Obtém o caractere Escape real para compatibilidade
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

set "RESET=%ESC%[0m"
set "BOLD=%ESC%[1m"
set "CYAN=%ESC%[38;2;80;200;255m"
set "GRAY=%ESC%[90m"
set "GREEN=%ESC%[38;2;110;230;140m"
set "WHITE=%ESC%[97m"

cls
echo.
echo  %CYAN%┌────────────────────────────────────────────────────────┐%RESET%
echo  %CYAN%│%RESET%  %BOLD%%WHITE%OmniPlaylist 2.0%RESET%                                    %CYAN%│%RESET%
echo  %CYAN%├────────────────────────────────────────────────────────┤%RESET%
echo  %CYAN%│%RESET%  %GRAY%• Status:%RESET%  %GREEN%● Rodando localmente%RESET%                       %CYAN%│%RESET%
echo  %CYAN%│%RESET%  %GRAY%• URL:%RESET%     %BOLD%%WHITE%http://localhost:8000%RESET%                     %CYAN%│%RESET%
echo  %CYAN%│%RESET%  %GRAY%• Dica:%RESET%    Pressione %WHITE%Ctrl+C%RESET% para encerrar             %CYAN%│%RESET%
echo  %CYAN%└────────────────────────────────────────────────────────┘%RESET%
echo.

:: Executa a aplicação
if exist ".\.venv\Scripts\python.exe" (
    .\.venv\Scripts\python.exe main.py
) else (
    echo  %ESC%[31m[ERRO] Ambiente virtual (.venv) não encontrado.%RESET%
    echo.
)

echo.
echo  %GRAY%Pressione qualquer tecla para fechar esta janela...%RESET%
pause >nul