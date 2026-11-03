; Miku Assistant - NSIS hooks for the Tauri installer.

!macro NSIS_HOOK_POSTUNINSTALL
  ; Python and the libraries Miku downloaded on her first start (~5 GB): nothing else uses them.
  ; The user's data (%APPDATA%\Miku Assistant: settings, memory, reminders) stays, for a reinstall or an update.
  RMDir /r "$LOCALAPPDATA\Miku Assistant\runtime"
!macroend
