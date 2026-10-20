@echo off
setlocal

echo ====================================================
echo   Desactivar Arranque con Windows - Miku Assistant
echo ====================================================

set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MikuAssistant.lnk"

if exist "%SHORTCUT_PATH%" (
    del /f /q "%SHORTCUT_PATH%"
    echo [*] Acceso directo eliminado correctamente.
    echo [*] Miku Assistant ya NO arrancara automaticamente con Windows.
) else (
    echo [*] El acceso directo no estaba instalado. Nada que hacer.
)

pause
exit /b 0
