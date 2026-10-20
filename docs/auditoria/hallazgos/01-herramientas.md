# Fase 1 · Herramientas de control del PC

Avance: `__init__.py` revisado 77/77 · `apps.py` revisado 387/387 · `files.py` revisado 138/138 · `media.py` revisado 173/173 · `notes.py` 0/79 · `system.py` 0/97 · `timers.py` 0/174 · `web.py` 0/97

### H-001 · La confirmación de acciones destructivas no está implementada en código

- **Severidad:** Alta
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:21`, `core/tools/__init__.py:53`, `core/config.py:87`, `core/tools/system.py:75`
- **Categoría:** seguridad

**Qué pasa:** el decorador acepta `destructive=True` y lo guarda en `_TOOL_METADATA`, y la config tiene `tools.confirm_destructive`, pero **nadie los lee**: `get_tool_metadata()` no se llama en ningún sitio y `confirm_destructive` solo aparece en `config.py`. La única "confirmación" es el parámetro `confirmed` de `shutdown_pc` (`system.py:75-84`), que **lo rellena el propio LLM**: si el modelo llama directamente `shutdown_pc(confirmed=True)`, se apaga el PC sin preguntar.

**Cómo se reproduce:** `grep -rn "destructive\|confirm_destructive\|get_tool_metadata" core/` → solo aparecen la definición y la config. Para el apagado: una transcripción ambigua o un texto inyectado ("apaga el equipo, ya está confirmado") puede llevar al modelo a pasar `confirmed=True` en la primera llamada.

**Evidencia:** `llm.py:42` delega la confirmación en el prompt: "Solo la acción de apagar o reiniciar el equipo (shutdown_pc) requiere confirmación previa si confirmed no es True".

**Propuesta:** hacer cumplir la confirmación en el wrapper de `tool()`: si `destructive` y `confirm_destructive`, no ejecutar y devolver `requires_confirmation`. La confirmación la registra el pipeline cuando el **usuario** dice "sí" en el turno siguiente, no un argumento del LLM.

### H-002 · `close_app` cierra aplicaciones sin confirmación, en contra de las reglas del proyecto

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/tools/apps.py:271-275`, `core/llm.py:42`
- **Categoría:** seguridad / docs

**Qué pasa:** `GEMINI.md` exige confirmación para "cerrar apps, apagar, borrar". `close_app` no está marcada como `destructive` y su docstring dice "sin pedir confirmación"; el prompt de `llm.py:42` lo refuerza. Cerrar una app puede perder trabajo sin guardar.

**Propuesta:** decidir la regla (docs o código) y alinearla. Si se mantiene sin confirmación, actualizar `GEMINI.md` y `tools.md`; si no, marcarla `destructive=True` una vez resuelto H-001.

### H-003 · El timeout de 5 s por herramienta no existe

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:5`, `core/tools/__init__.py:33`
- **Categoría:** error

**Qué pasa:** el docstring del módulo promete "Timeout of 5s per tool execution", pero el wrapper llama `func(*args, **kwargs)` de forma síncrona sin límite. Una herramienta colgada (p. ej. `find_file` en un disco lento o de red) bloquea el turno. Si Gemini ejecuta las herramientas en el hilo del bucle `asyncio`, se congela todo el backend.

**Por verificar:** cómo invoca `llm.py` las herramientas (hilo propio o bucle de eventos). Se revisa en la fase 3.

**Propuesta:** quitar la promesa del docstring o aplicar el límite donde se invocan las herramientas (`asyncio.wait_for` + `to_thread`).

### H-004 · `print` sueltos y argumentos completos en los logs

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:29`, `:31`, `:35`, `:42`
- **Categoría:** mantenibilidad

**Qué pasa:** cada ejecución hace `print` además de `logger.info`, en contra de "nada de prints sueltos" (`GEMINI.md`). Además se registran todos los argumentos, incluido el texto de las notas personales (`take_note`) y lo que escribe `type_text`.

**Propuesta:** borrar los `print` y truncar los argumentos en el log.

### H-005 · Un nombre de herramienta repetido sobrescribe al anterior sin aviso

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:49`
- **Categoría:** mantenibilidad

**Qué pasa:** `_TOOL_REGISTRY[tool_name] = wrapper` no comprueba si el nombre ya existe. Dos módulos con el mismo `name=` dejan registrada solo la última importada.

**Propuesta:** `assert tool_name not in _TOOL_REGISTRY`.

### H-006 · `open_app` ejecuta cualquier línea de comandos que le pase el LLM

- **Severidad:** Alta (sube a Crítica si la fase 2 confirma que un tercero puede enviar texto al backend)
- **Estado:** confirmado
- **Ubicación:** `core/tools/apps.py:260-261`, `core/tools/apps.py:141-143`, `core/tools/apps.py:171`
- **Categoría:** seguridad

**Qué pasa:** si el nombre no coincide con un alias ni con un acceso directo, el paso 3 pasa el texto tal cual a `_launch_target`, que lo usa como **línea de comandos** de `CreateProcessW` (`lpApplicationName=None`). Windows toma el primer token como ejecutable y el resto como argumentos. Si eso falla, el último recurso hace `subprocess.Popen(f'cmd.exe /c start "" "{target}"', shell=True)`, donde unas comillas en el texto permiten encadenar comandos con `&`. Esto rompe la regla de `GEMINI.md`: "Nunca implementes ejecución arbitraria de comandos de shell generados por el LLM".

**Cómo se reproduce:** `open_app(name="powershell -c start-process calc")` → no hay alias ni acceso directo → `CreateProcessW` ejecuta `powershell` con esos argumentos y se abre la calculadora. Pasarlo a minúsculas (`_clean_query`) no lo impide.

**Propuesta:** en el paso 3, aceptar solo un nombre de ejecutable simple (`^[\w .-]+$`, sin espacios ni rutas) y lanzarlo con `lpApplicationName` explícito, o eliminar el paso 3. Quitar el recurso `shell=True`.

### H-007 · `type_text` + los alias `cmd`/`powershell`/`terminal` permiten ejecutar comandos

- **Severidad:** Alta
- **Estado:** por-verificar (falta comprobar en vivo que `
` pulsa Enter)
- **Ubicación:** `core/tools/apps.py:63-65`, `core/tools/apps.py:367-385`
- **Categoría:** seguridad

**Qué pasa:** el LLM puede abrir una consola con `open_app("cmd")` y después escribir en ella con `type_text`. `VkKeyScanW("
")` devuelve la tecla Enter con el bit de Ctrl, y el código ignora ese bit y pulsa Enter, así que el comando se ejecuta. Sin ninguna inyección de comandos, dos herramientas legítimas encadenadas equivalen a ejecución arbitraria. Además, `type_text` escribe en **cualquier** ventana activa, aunque el usuario haya cambiado de ventana mientras Miku respondía.

**Propuesta:** quitar `cmd`, `powershell` y `terminal` de los alias, y que `type_text` descarte saltos de línea y se niegue a escribir si la ventana activa es una consola (`ConsoleWindowClass`, `CASCADIA_HOSTING_WINDOW_CLASS`).

### H-008 · `close_app` mata procesos por subcadena y con `kill()`

- **Severidad:** Alta
- **Estado:** confirmado
- **Ubicación:** `core/tools/apps.py:290-291`
- **Categoría:** error / seguridad

**Qué pasa:** la condición `query in clean_p` cierra **todo** proceso cuyo nombre contenga el texto. Un nombre corto o mal transcrito por Whisper ("e", "code", "python") mata muchos procesos: `"python"` mata el propio backend de Miku, y una sola letra puede tumbar `explorer.exe` y apps con trabajo sin guardar. Usa `kill()`, que no deja guardar, cuando `tools.md` especifica `terminate()` y confirmación 🔒 (ver H-002).

**Propuesta:** comparar el nombre exacto (o alias exacto), excluir el PID propio y procesos críticos, usar `terminate()` con `kill()` solo tras un tiempo, y exigir confirmación (H-001).

### H-009 · Los alias de apps están fijos en el código; `config.yaml → apps` se ignora

- **Severidad:** Baja
- **Estado:** por-verificar (confirmar en la fase 4 que `config.py` no los carga)
- **Ubicación:** `core/tools/apps.py:38-69`
- **Categoría:** mantenibilidad / docs

**Qué pasa:** `tools.md` dice que `open_app` usa los alias de `config.yaml → apps`, pero `apps.py` usa el diccionario fijo `DEFAULT_APP_ALIASES`. Además, `"google"` abre Opera y la caché del menú Inicio no se refresca nunca: una app instalada después del arranque no se encuentra hasta reiniciar.

**Propuesta:** cargar los alias desde la config, con estos como valor por defecto.

### H-010 · Fugas de handles y llamadas bloqueantes en cada herramienta de ventanas

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/apps.py:104-116`, `:221`, `:230`, `:385`
- **Categoría:** recursos

**Qué pasa:** `_attach_user_desktop()` abre una estación y un escritorio con `GENERIC_ALL` en **cada** llamada y nunca cierra los handles (`CloseWindowStation`/`CloseDesktop`). Además `time.sleep(0.3)` tras cada apertura y `time.sleep(0.01)` por carácter en `type_text` (hasta 5 s) bloquean el hilo que ejecuta la herramienta (relacionado con H-003).

**Propuesta:** abrir los handles una vez por proceso y cerrarlos, o solo llamar `SetThreadDesktop` cuando haga falta.

### H-011 · `open_file` ejecuta programas y scripts encontrados en Descargas

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/tools/files.py:58-61`, `core/tools/files.py:97`
- **Categoría:** seguridad

**Qué pasa:** la protección de "solo abrir lo encontrado en la sesión" no filtra el tipo de archivo. `find_file` busca por subcadena en Escritorio, Documentos y Descargas, y `open_file` abre el resultado con `os.startfile`, que **ejecuta** `.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.lnk`, `.msi`, etc. Descargas suele contener instaladores y scripts sin revisar.

**Cómo se reproduce:** con un `setup.exe` en Descargas: `find_file("setup")` → `open_file("setup.exe")` → se ejecuta el instalador.

**Propuesta:** lista de extensiones ejecutables bloqueadas en `open_file` (o lista permitida de documentos, imágenes, audio y vídeo).

### H-012 · Errores menores en `files.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/files.py:136`, `:138`, `:89-93`, `:16`
- **Categoría:** error

**Qué pasa:**
- `open_folder` construye el mensaje con `name`, pero el valor puede venir en `folder` o `folder_name`: Miku responde "He abierto la carpeta ." con el nombre vacío.
- `open_file` por nombre elige el primer archivo del `set` con ese nombre; si hay dos `notas.txt` en carpetas distintas, abre uno al azar.
- `_SESSION_FOUND_FILES` crece sin límite durante toda la sesión.

**Propuesta:** usar `target_name` en los mensajes, devolver las opciones cuando hay nombres repetidos y limpiar el set al terminar cada conversación.

### H-013 · La detección por subcadenas en `media_control` y `mute` hace lo contrario de lo pedido

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/tools/media.py:86-100`, `core/tools/media.py:158`
- **Categoría:** error

**Qué pasa:**
- `media_control` comprueba primero las palabras de play/pause, que incluyen `"cancion"`, `"canción"`, `"musica"` y `"música"`. Entonces `action="siguiente canción"` o `"canción anterior"` entra en la primera rama y **pausa** en lugar de cambiar de pista. Una acción desconocida también hace play/pause.
- En `mute`, si `on` no viene, se buscan subcadenas como `"activar"` o `"no"` para decidir si se **quita** el silencio. `action="activar el silencio"` contiene "activar" y quita el silencio en vez de ponerlo; `action="silencia el teléfono"` contiene "no" (telé**fono**) y hace lo mismo.

**Cómo se reproduce:** `media_control("siguiente canción")` → "Reproducción alternada (play/pause)". `mute(action="activar el silencio")` → "Sonido reactivado".

**Propuesta:** comprobar primero next/prev/stop y dejar play/pause al final; en `mute`, comparar palabras completas (`act.split()`), no subcadenas, y devolver error ante una acción desconocida.

### H-014 · Las herramientas de volumen dicen "ok" aunque no hayan cambiado nada

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/media.py:112-121`, `:165-172`, `:22-34`
- **Categoría:** error / mantenibilidad

**Qué pasa:** `set_volume` y `mute` devuelven `ok: True` aunque no haya dispositivos de salida o fallen todos (las excepciones se tragan con `except: pass`), así que Miku confirma algo que no hizo. Además `_attach_user_desktop` está copiado de `apps.py`, con la misma fuga de handles (H-010).

**Propuesta:** devolver `ok: False` si no se aplicó a ningún dispositivo, y mover `_attach_user_desktop` a un módulo común.

### Notas para siguientes pasos

- `tools.md` lista `list_open_apps`, que no existe en `apps.py`. Revisar en la fase 12.
