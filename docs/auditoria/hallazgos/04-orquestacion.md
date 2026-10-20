# Fase 4 · Orquestación y arranque

Avance: `__main__.py` revisado 160/160 · `pipeline.py` revisado 388/388 · `resources.py` 0/104 · `config.py` 0/206 · `config.yaml` revisado 27/27

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

### H-030 · Un error al procesar texto deja la wake word en pausa para siempre

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/pipeline.py:280-334` (comparar con el `try/except/finally` de `:169-262`)
- **Categoría:** error

**Qué pasa:** `handle_text_input` pausa la wake word (`:285`) y solo la reanuda en el camino sin voz (`:331`) o cuando llega `speak_done`. No tiene `try/except`: si `brain.chat`, `tts.synthesize` o un `broadcast` lanzan una excepción (por ejemplo el `RuntimeError` de H-020), la corrutina termina sin reanudar la wake word ni volver a `idle`. Miku deja de responder a "hey Miku" hasta reiniciar, y la interfaz se queda en "pensando". La ruta de voz sí está protegida.

**Propuesta:** envolver el cuerpo en el mismo `try/except` que la ruta de voz, con la reanudación de la wake word en el `except`.

### H-031 · Los avisos de temporizador se pisan con la conversación y pueden despertar a la wake word

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/pipeline.py:118-141`, `:77`
- **Categoría:** error

**Qué pasa:** `announce_timer` no toma el `_pipeline_lock`, no pausa la wake word, no marca `_is_speaking` ni programa el watchdog. Si un temporizador vence mientras el usuario habla o Miku responde, se envían dos `speak` a la vez, y la voz de Miku por los altavoces puede activar la propia wake word. Además, el watchdog estima la duración por caracteres (`0,15 s × caracteres + 6 s`); si el audio de RVC dura más, la wake word se reanuda con Miku aún hablando.

**Propuesta:** que `announce_timer` espere al `_pipeline_lock` y use el mismo bloque de "hablar" que el resto (pausar la wake word, `_is_speaking`, watchdog).

### H-032 · Detalles de `pipeline.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/pipeline.py:231-254`, `:312-334`, `:347-388`, `:257`, `:276-278`, `:187`
- **Categoría:** mantenibilidad

**Qué pasa:**

- El bloque de "hablar" (expresión, subtítulo, `speak`, watchdog, o degradación) está copiado cuatro veces: voz, texto, temporizador y saludo.
- `__main__.py:129` dice que el saludo es "once-per-day", pero `check_startup_greeting` saluda en **cada** arranque del backend (el import `date` no se usa). Además precarga RVC en la GPU para hablar (refuerza H-028).
- Los errores se registran sin traza (`logger.error("...%s", e)`, `:257`; `logger.debug` en `:388`), lo que hace muy difícil depurar.
- Si el pipeline está ocupado, el texto que escribe el usuario se descarta en silencio (`:276-278`).
- `initial_timeout=5.5` está fijo en el código.

**Propuesta:** extraer un método `_speak(text, emotion)`, guardar la fecha del último saludo en `cache/`, y usar `logger.exception`.

### Notas para siguientes pasos

- Fase 10: el filtro de `stop.bat` (`CommandLine -like '*miku-assistant*'`) coincide también con el propio PowerShell que lo ejecuta y con el `cmd.exe` que corre `stop.bat` (su línea de comandos contiene la ruta del proyecto), y con VS Code si tiene abierta la carpeta. Verificar si el script se mata a sí mismo antes de llegar al paso del worker de RVC.
