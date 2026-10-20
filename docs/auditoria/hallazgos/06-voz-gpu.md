# Fase 6 · Voz de salida y GPU

Avance: `tts.py` revisado 103/103 · `rvc.py` revisado 209/209 · `rvc_worker.py` 0/392 · `rmvpe.py` 0/432

**Regla principal verificada:** ningún módulo del proceso principal (`core/*.py` salvo `rvc_worker.py` y `rmvpe.py`, y `core/tools/`) importa `torch` (`grep -rn "import torch"`). Falta confirmarlo en ejecución (fase 0: el proceso `pythonw -m core` no debe aparecer en `nvidia-smi`).

### H-038 · Tras un timeout con el worker de RVC, las respuestas quedan desfasadas y Miku dice la frase anterior

- **Severidad:** Media
- **Estado:** confirmado por lectura (falta reproducirlo)
- **Ubicación:** `core/rvc.py:99`, `:107-109`
- **Categoría:** error

**Qué pasa:** el protocolo con el worker es "una línea enviada, una línea leída", sin identificador de petición. Si `readline()` agota el tiempo (35 s en `warmup`, 25 s en `convert`), `_send_command` devuelve `None` pero **no mata el worker**, que sigue trabajando y escribe su respuesta más tarde. La siguiente orden lee esa respuesta vieja como si fuera la suya, y todas las posteriores quedan desplazadas una posición.

**Cómo se reproduce:** la primera carga de CUDA + modelo + índice tarda más de 35 s (disco lento, primer arranque) → `warmup` agota el tiempo → el siguiente `convert` lee el `{"status": "ok"}` del warmup, sin audio, y cae a la voz base → el `convert` siguiente lee el audio del **anterior**: Miku pronuncia la respuesta de la pregunta previa, con el subtítulo de la actual.

**Propuesta:** en cualquier timeout o error de protocolo, `terminate_worker()` (el siguiente uso lo relanza). Mejor aún, añadir un `id` a cada petición y descartar respuestas que no coincidan.

### H-039 · Detalles de `rvc.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/rvc.py:74`, `:166-170`, `:197-208`
- **Categoría:** mantenibilidad / error

**Qué pasa:**

- El stderr del worker va a `DEVNULL`: todos sus logs y trazas de error se pierden. Si RVC falla (modelo corrupto, CUDA sin memoria), solo se ve "RVC conversion failed: Unknown error".
- En `convert`, si el worker no estaba corriendo, la respuesta de `load` se ignora: si la carga falla, se intenta convertir igual y se espera otro timeout.
- `terminate_worker` llama a `terminate()` sin esperar a que el proceso termine ni cerrar sus *pipes*; asyncio puede avisar de *transports* sin cerrar.
- Si el backend muere de golpe (`stop.bat` con `Stop-Process -Force`, o un fallo), Windows **no** mata al hijo: el worker y su VRAM quedan vivos salvo que el propio worker salga al detectar el cierre de stdin (se revisa en `rvc_worker.py`).

**Propuesta:** redirigir el stderr del worker a `cache/rvc_worker.log`, comprobar la respuesta de `load`, y esperar con `await proc.wait()` (con timeout y `kill()` de respaldo).

### H-040 · La caché de voz crece sin límite y las "frases fijas" nunca se precargan

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tts.py:35-39`, `:81-85`, `:94-103`
- **Categoría:** recursos / docs

**Qué pasa:** cada respuesta distinta de Gemini se guarda como un `.mp3` en `cache/voice/` para siempre (hoy hay 94 archivos, 3,1 MB). Como casi todas las respuestas son distintas, la caché crece sin aportar nada. La escritura no es atómica: si el proceso muere a mitad, queda un `.mp3` truncado que se reproducirá siempre. Además `prepopulate_cache` no se llama desde ningún sitio, así que las frases fijas de `persona.md` no se precargan (lo contrario de lo que dice el roadmap, fase 3). Y como la caché guarda la voz base, RVC vuelve a convertir en la GPU incluso las frases repetidas.

**Propuesta:** cachear solo las frases fijas (y, si se quiere, su versión ya convertida por RVC), escribir en un archivo temporal y renombrar, y llamar a `prepopulate_cache` al arrancar.

### Notas para siguientes pasos
