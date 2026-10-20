# Fase 6 · Voz de salida y GPU

Avance: `tts.py` revisado 103/103 · `rvc.py` revisado 209/209 · `rvc_worker.py` revisado 392/392 · `rmvpe.py` revisado como código de terceros (cabecera, carga, inferencia y decodificación, líneas 1-40 y 300-432; las capas de red 41-299 se comparan con el original en la fase 7) · **fase completa**

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
- Si el backend muere de golpe (`stop.bat` con `Stop-Process -Force`, o un fallo), Windows **no** mata al hijo. Revisado en `rvc_worker.py:319-323`: el worker sale solo al leer EOF en stdin, así que solo queda huérfano si el backend muere **en mitad de una conversión** (sale al terminarla). Riesgo bajo.

**Propuesta:** redirigir el stderr del worker a `cache/rvc_worker.log`, comprobar la respuesta de `load`, y esperar con `await proc.wait()` (con timeout y `kill()` de respaldo).

### H-040 · La caché de voz crece sin límite y las "frases fijas" nunca se precargan

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tts.py:35-39`, `:81-85`, `:94-103`
- **Categoría:** recursos / docs

**Qué pasa:** cada respuesta distinta de Gemini se guarda como un `.mp3` en `cache/voice/` para siempre (hoy hay 94 archivos, 3,1 MB). Como casi todas las respuestas son distintas, la caché crece sin aportar nada. La escritura no es atómica: si el proceso muere a mitad, queda un `.mp3` truncado que se reproducirá siempre. Además `prepopulate_cache` no se llama desde ningún sitio, así que las frases fijas de `persona.md` no se precargan (lo contrario de lo que dice el roadmap, fase 3). Y como la caché guarda la voz base, RVC vuelve a convertir en la GPU incluso las frases repetidas.

**Propuesta:** cachear solo las frases fijas (y, si se quiere, su versión ya convertida por RVC), escribir en un archivo temporal y renombrar, y llamar a `prepopulate_cache` al arrancar.

### H-041 · Detalles de `rvc_worker.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/rvc_worker.py:90`, `:121`, `:226-237`, `:116`
- **Categoría:** error / recursos

**Qué pasa:**

- La primera vez, `HubertModel.from_pretrained("lengyue233/content-vec-best")` descarga unos cientos de MB de Hugging Face dentro del `warmup`. Eso supera de sobra el timeout de 35 s de `rvc.py` y dispara el desfase de H-038 en la primera instalación. Además necesita internet en ese primer uso, sin aviso.
- `load_state_dict(..., strict=False)` ignora en silencio pesos que falten o no encajen: con un `.pth` de otra versión de RVC, la voz sale mal sin ningún error.
- La recuperación del índice FAISS recorre cada frame y cada vecino en Python con `index.reconstruct(k)` (8 llamadas por frame): con respuestas largas es lento. El RVC original precarga todos los vectores en un array y lo hace vectorizado.
- Lo que está bien: `torch.load` sin `weights_only` es seguro aquí porque la versión instalada (torch 2.15) usa `weights_only=True` por defecto; aun así conviene escribirlo explícito para no depender de la versión. El stdout real se reserva para el protocolo (`:306-307`) y cualquier excepción devuelve una respuesta, lo que ayuda a no desfasarse.
- El venv usa una versión *nightly* de PyTorch (`2.15.0.dev20260907+cu126`): se revisa en la fase 10.

**Propuesta:** descargar ContentVec durante la instalación (`setup.md`) o con un timeout mayor solo para la primera carga; `strict=True` (o registrar las claves que falten); vectorizar la consulta FAISS como en RVC.

### H-042 · `rmvpe.py` es una copia del original de RVC con restos de depuración

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/rmvpe.py:1`, `:334`, `:365-432`
- **Categoría:** mantenibilidad

**Qué pasa:** el archivo es el `rmvpe.py` del proyecto RVC (comentarios en chino, ruta del autor original en `:421`). Importa `pdb` y `traceback` sin usarlos, y tiene bloques de depuración comentados. `torch.load` (`:334`) depende del valor por defecto de la versión de torch para ser seguro (ver H-041). No hay cabecera de licencia ni referencia al origen.

**Propuesta:** añadir una cabecera con el origen y la licencia (RVC es MIT), quitar `pdb`/`traceback` y el código comentado, y pasar `weights_only=True` explícito. Incluirlo en la comparación con el original de la fase 7.

### Resumen de la fase 6

5 hallazgos (1 medio, 4 bajos). El aislamiento de la GPU está bien planteado: `torch` no entra en el proceso principal, el worker sale solo al cerrarse su stdin y los `.pth` se cargan con `weights_only`. El fallo importante es el desfase del protocolo tras un timeout (H-038), que la primera descarga de ContentVec (H-041) hace bastante probable.

### Notas para siguientes pasos
