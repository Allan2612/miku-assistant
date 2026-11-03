@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo        Iniciando Miku Assistant
echo ====================================================

:: 0. Already running? (H-054) A second backend cannot bind the port and adds a second tray icon
netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul && (
    echo [!] Miku ya esta en marcha ^(el puerto 8765 esta ocupado^). Usa stop.bat primero.
    pause
    exit /b 1
)

:: 1. miku.exe starts the backend itself, as its child: Task Manager groups both under "Miku Assistant", and the
::    backend shuts down by itself when miku.exe closes
echo [*] Iniciando Miku Assistant...
if exist "%~dp0app\src-tauri\target\release\miku.exe" (
    start "" "%~dp0app\src-tauri\target\release\miku.exe" %*
) else if exist "%~dp0app\src-tauri\target\debug\miku.exe" (
    start "" "%~dp0app\src-tauri\target\debug\miku.exe" %*
) else (
    echo [!] Error: No se encontro miku.exe. Compila la app primero.
    pause
    exit /b 1
)

:: 2. Wait for the backend's WebSocket server (the first start loads Whisper and RVC)
echo [*] Esperando al backend (ws://127.0.0.1:8765)...
for /l %%i in (1,1,30) do (
    netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul && goto :ws_ready
    ping -n 2 127.0.0.1 >nul
)
echo [!] El backend no abrio el puerto 8765 en 30 s. Revisa cache\core.log.
pause
exit /b 1
:ws_ready

echo [*] Miku Assistant esta listo en segundo plano.
echo [*] Atajo global: Ctrl+Alt+M o di 'Hey Miku'.
exit /b 0
