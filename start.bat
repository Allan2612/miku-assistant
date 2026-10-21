@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo        Iniciando Miku Assistant
echo ====================================================

set "PYTHONPATH=%~dp0"

:: 0. Already running? (H-054) A second backend cannot bind the port and adds a second tray icon
netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul && (
    echo [!] Miku ya esta en marcha ^(el puerto 8765 esta ocupado^). Usa stop.bat primero.
    pause
    exit /b 1
)

:: 1. Iniciar backend silenciosamente con pythonw en segundo plano
echo [*] Iniciando backend de Python en segundo plano...
start "" "%~dp0core\.venv\Scripts\pythonw.exe" -m core

:: 2. Esperar activamente a que el servidor WebSocket enlace el puerto 8765
echo [*] Esperando servidor WebSocket (ws://127.0.0.1:8765)...
for /l %%i in (1,1,20) do (
    netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul && goto :ws_ready
    ping -n 2 127.0.0.1 >nul
)
echo [!] El backend no abrio el puerto 8765 en 20 s. Revisa cache\core.log.
pause
exit /b 1
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
