@echo off
setlocal
cd /d "%~dp0"
set "MIKU_ROOT=%~dp0"

echo ====================================================
echo        Deteniendo Miku Assistant
echo ====================================================

echo [*] Cerrando Miku Assistant (miku.exe de este proyecto)...
:: Match the exact executable path: other programs with that name are left alone (app.exe: builds before 3-nov)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('miku.exe','app.exe') -and $_.ExecutablePath -like ($env:MIKU_ROOT + 'app\src-tauri\target\*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
:: The backend sees miku.exe gone and shuts down by itself (mic, RVC worker): give it a moment
ping -n 5 127.0.0.1 >nul

echo [*] Cerrando backend de Miku si sigue vivo...
:: Started by hand, or stuck: core\__main__.py wrote its PID. No /T: the apps Miku opened for you (Spotify,
:: Opera...) are its children too and must stay open; its RVC worker exits when the pipe closes
set "CORE_PID="
if exist "cache\core.pid" set /p CORE_PID=<"cache\core.pid"
:: Only if that PID is still our Python: after a reboot or a crash the file is stale, and the PID may now
:: belong to any other program
if defined CORE_PID powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter 'ProcessId=%CORE_PID%'; if ($p -and $p.Name -match '^pythonw?\.exe$' -and $p.CommandLine -like '*-m core*') { taskkill /PID %CORE_PID% /F | Out-Null }"
if exist "cache\core.pid" del "cache\core.pid"

echo [*] Cerrando trabajadores de RVC huerfanos (si quedara alguno)...
:: Only Python processes: shells whose command line mentions the script must not match
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*core\rvc_worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [*] Miku Assistant se ha detenido.
ping -n 3 127.0.0.1 >nul
exit /b 0
