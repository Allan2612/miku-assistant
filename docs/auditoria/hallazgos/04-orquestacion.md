# Fase 4 · Orquestación y arranque

Avance: `__main__.py` revisado 160/160 · `pipeline.py` 0/388 · `resources.py` 0/104 · `config.py` 0/206 · `config.yaml` revisado 27/27

### H-028 · Whisper y el worker de RVC se cargan al arrancar el PC, no al activar a Miku

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/__main__.py:125-127`
- **Categoría:** recursos

**Qué pasa:** al arrancar el backend se lanzan `stt.warmup()` y `rvc.warmup()`. Eso carga Whisper en RAM y arranca el subproceso de RVC con PyTorch y CUDA en la GPU, aunque nadie haya llamado a Miku. Con el arranque automático de Windows (`install_autostart.bat`), **cada inicio de sesión** ocupa RAM y VRAM durante los primeros `unload_after_minutes` (10 min en `config.yaml`). La arquitectura pide lo contrario: precargar en el momento de la activación, mientras el usuario habla, y 0 MB de VRAM en reposo.

**Propuesta:** quitar estas dos líneas y confiar en la precarga al activar (paso 2 del flujo). Si la primera respuesta resulta lenta, precargar solo Whisper (CPU) al arrancar.

### H-029 · Detalles de `__main__.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/__main__.py:30-33`, `:89`, `:125-130`, `:48`, `:137-141`
- **Categoría:** mantenibilidad / recursos

**Qué pasa:**

- `cache/core.log` se abre en modo `a` sin rotación: crece sin límite mientras el asistente esté instalado. Además usa rutas relativas al directorio actual (funciona solo porque `start.bat` hace `cd`).
- El host y el puerto (`127.0.0.1:8765`) están fijos en el código en lugar de en `config.yaml`.
- Las tres tareas de `create_task` no guardan referencia: sus excepciones solo se ven como "Task exception was never retrieved".
- El log dice "Phase 7 Running", pero el proyecto va por la fase 8.
- El bucle principal despierta cada segundo para nada; basta `await stop_event.wait()`.
- En Windows no se instalan manejadores de señales, así que el bloque `finally` (que termina el worker de RVC) solo se ejecuta con Ctrl+C. `stop.bat` mata el proceso con `Stop-Process -Force`, sin limpieza (se revisa en las fases 6 y 10).

**Propuesta:** `RotatingFileHandler` con ruta absoluta, host y puerto en la config, y guardar las tareas en un set.

### Notas para siguientes pasos

- Fase 10: el filtro de `stop.bat` (`CommandLine -like '*miku-assistant*'`) coincide también con el propio PowerShell que lo ejecuta y con el `cmd.exe` que corre `stop.bat` (su línea de comandos contiene la ruta del proyecto), y con VS Code si tiene abierta la carpeta. Verificar si el script se mata a sí mismo antes de llegar al paso del worker de RVC.
