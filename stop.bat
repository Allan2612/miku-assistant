@echo off
setlocal
cd /d "%~dp0"
set "MIKU_ROOT=%~dp0"

echo ====================================================
echo        Deteniendo Miku Assistant
echo ====================================================

echo [*] Cerrando aplicacion de escritorio (app.exe de este proyecto)...
:: Match the exact executable path: other programs named app.exe are left alone
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'app.exe' -and $_.ExecutablePath -like ($env:MIKU_ROOT + 'app\src-tauri\target\*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [*] Cerrando backend de Miku y su worker de RVC...
:: core\__main__.py writes its PID; /T also ends its child rvc_worker
set "CORE_PID="
if exist "cache\core.pid" set /p CORE_PID=<"cache\core.pid"
:: Only if that PID is still our Python: after a reboot or a crash the file is stale, and the PID may now
:: belong to any other program (taskkill /T would close it and its children)
if defined CORE_PID powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter 'ProcessId=%CORE_PID%'; if ($p -and $p.Name -match '^pythonw?\.exe$' -and $p.CommandLine -like '*-m core*') { taskkill /PID %CORE_PID% /T /F | Out-Null }"
if exist "cache\core.pid" del "cache\core.pid"

echo [*] Cerrando trabajadores de RVC huerfanos (si quedara alguno)...
:: Only Python processes: shells whose command line mentions the script must not match
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*core\rvc_worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [*] Miku Assistant se ha detenido.
ping -n 3 127.0.0.1 >nul
exit /b 0
