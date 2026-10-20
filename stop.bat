@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo        Deteniendo Miku Assistant
echo ====================================================

echo [*] Cerrando aplicacion de escritorio (app.exe)...
taskkill /F /IM app.exe 2>nul

echo [*] Cerrando proceso backend de Miku...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*miku-assistant*' -or $_.CommandLine -like '*-m core*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [*] Cerrando trabajadores de audio RVC...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*rvc_worker*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [*] Miku Assistant se ha detenido completamente (0%% CPU, 0%% RAM, 0%% VRAM).
ping -n 3 127.0.0.1 >nul
exit /b 0
