@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo        Iniciando Miku Assistant (Fase 8)
echo ====================================================

set "PYTHONPATH=%~dp0"

:: 1. Iniciar backend silenciosamente con pythonw en segundo plano
echo [*] Iniciando backend de Python en segundo plano...
start "" "%~dp0core\.venv\Scripts\pythonw.exe" -m core

:: 2. Esperar activamente a que el servidor WebSocket enlace el puerto 8765
echo [*] Esperando servidor WebSocket (ws://127.0.0.1:8765)...
for /l %%i in (1,1,20) do (
    netstat -ano | findstr 8765 | findstr LISTENING >nul && goto :ws_ready
    ping -n 2 127.0.0.1 >nul
)
:ws_ready

:: 3. Iniciar aplicacion de escritorio Tauri
echo [*] Iniciando ventana de Miku...
if exist "%~dp0app\src-tauri\target\release\app.exe" (
    start "" "%~dp0app\src-tauri\target\release\app.exe"
) else if exist "%~dp0app\src-tauri\target\debug\app.exe" (
    start "" "%~dp0app\src-tauri\target\debug\app.exe"
) else (
    echo [!] Error: No se encontro app.exe. Compila la app primero.
    pause
    exit /b 1
)

echo [*] Miku Assistant esta listo en segundo plano.
echo [*] Atajo global: Ctrl+Alt+M o di 'Hey Miku'.
exit /b 0
