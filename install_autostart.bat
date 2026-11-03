@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo   Configurar Arranque con Windows - Miku Assistant
echo ====================================================

set "TARGET_BAT=%~dp0start.bat"
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MikuAssistant.lnk"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET_BAT%'; $s.WorkingDirectory = '%~dp0'; $s.Arguments = '--tray'; $s.Description = 'Miku Assistant Desktop AI'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [*] Acceso directo de inicio creado exitosamente en:
    echo     "%SHORTCUT_PATH%"
    echo [*] Miku Assistant arrancara automaticamente al iniciar sesion en Windows.
) else (
    echo [!] Error al crear el acceso directo de inicio.
)

pause
exit /b 0
