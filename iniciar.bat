@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".\.venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual ^(.venv^) nao encontrado em %~dp0
    pause
    exit /b 1
)

.\.venv\Scripts\python.exe -c "import os; os.system(''); print('\n  \033[38;2;80;200;255m┌────────────────────────────────────────────────────────┐\033[0m\n  \033[38;2;80;200;255m│\033[0m  \033[1;97mOmniPlaylist 2.0 (React Studio UI)\033[0m                  \033[38;2;80;200;255m│\033[0m\n  \033[38;2;80;200;255m├────────────────────────────────────────────────────────┤\033[0m\n  \033[38;2;80;200;255m│\033[0m  \033[90m• Status:\033[0m  \033[38;2;110;230;140m● Rodando localmente\033[0m                       \033[38;2;80;200;255m│\033[0m\n  \033[38;2;80;200;255m│\033[0m  \033[90m• URL:\033[0m     \033[1;97mhttp://localhost:8000\033[0m                     \033[38;2;80;200;255m│\033[0m\n  \033[38;2;80;200;255m│\033[0m  \033[90m• Dica:\033[0m    Pressione \033[97mCtrl+C\033[0m para encerrar             \033[38;2;80;200;255m│\033[0m\n  \033[38;2;80;200;255m└────────────────────────────────────────────────────────┘\033[0m\n')"

.\.venv\Scripts\python.exe main.py

echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul