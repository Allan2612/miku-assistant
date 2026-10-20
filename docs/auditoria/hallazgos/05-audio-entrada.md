# Fase 5 · Audio de entrada

Avance: `audio_in.py` revisado 185/185 · `stt.py` revisado 145/145 · `wakeword.py` revisado 240/240 · **fase completa**

Lo que está bien: el micrófono de la grabación se cierra siempre en un `finally` (`audio_in.py:169-177`), también si la tarea se cancela; Whisper corre en CPU con `int8` y se carga y descarga bajo un `asyncio.Lock` (`stt.py:65-72`); la wake word no abre el micrófono si está desactivada (`wakeword.py:91-93`).

### H-034 · La detección de voz es por energía, no silero-vad: con ruido o música graba siempre hasta el máximo

- **Severidad:** Media
- **Estado:** por-verificar (falta la prueba en vivo con música de fondo)
- **Ubicación:** `core/audio_in.py:100-164`, `docs/architecture.md:30`
- **Categoría:** error / docs

**Qué pasa:** la arquitectura especifica **silero-vad**, pero `audio_in.py` decide inicio y fin de voz solo por el volumen (RMS) del audio, con umbrales muy bajos (`0,0013–0,015`) fijos en el código. El "silencio" se calibra con los primeros 200 ms. Si hay música, un ventilador fuerte o una llamada de fondo, el volumen nunca baja del umbral: Miku graba hasta `max_record_seconds` (10 s) en cada activación y le pasa a Whisper ese ruido.

**Cómo verificar:** con música sonando, activar a Miku, decir una frase corta y mirar en `cache/core.log` si la grabación termina por silencio o por tiempo.

**Propuesta:** usar el VAD que ya trae faster-whisper (silero, ya instalado como dependencia) o `silero-vad` para el fin de frase, como dice la arquitectura; como mínimo, mover los umbrales a `config.yaml`.

### H-035 · El `initial_prompt` de Whisper está lleno de órdenes y puede hacer que "oiga" comandos en el ruido

- **Severidad:** Media
- **Estado:** por-verificar
- **Ubicación:** `core/stt.py:92-97`
- **Categoría:** seguridad / error

**Qué pasa:** el texto de contexto que se le da a Whisper es una lista de órdenes ("Abre el bloc de notas, abre Google Chrome, sube el volumen, baja el volumen…"). Whisper es conocido por "alucinar" el texto del prompt cuando el audio es ruido o casi silencio. Junto con H-034 (graba ruido) y el atajo local (H-023, H-024, que ejecuta sin preguntar), un ruido podría acabar como "sube el volumen" o "cierra…" ejecutado al instante. `vad_filter=True` reduce el riesgo, pero no lo elimina.

**Cómo verificar:** pasar a `_transcribe_sync` 3 s de ruido blanco suave y de silencio, 20 veces, y contar cuántas transcripciones devuelven frases del prompt.

**Propuesta:** dejar en el prompt solo vocabulario (nombres propios: "Miku", "Spotify", "Opera GX") sin frases imperativas, y descartar transcripciones con `no_speech_prob` alto.

### H-036 · Detalles de `stt.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/stt.py:88`, `:92-97`, `:56-61`
- **Categoría:** mantenibilidad

**Qué pasa:** el idioma `"es"` y el prompt están fijos en el código aunque `config.yaml` tiene `language`. La primera carga descarga el modelo de Hugging Face; sin internet en el primer uso, la carga falla y el error solo se ve en el log.

**Propuesta:** leer `language` de la config.

### H-037 · Detalles de `wakeword.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/wakeword.py:80-87`, `:117-121`, `:161`, `:191`, `:202-203`, `:68`
- **Categoría:** error / recursos

**Qué pasa:**

- Si falta `hey_miku.onnx`, se usa `hey_jarvis` en silencio (solo un `warning` en el log): Miku responde a "hey Jarvis" y no a su nombre, y el usuario no sabe por qué.
- `vad_threshold` se lee de la config (`config.py:194`), pero aquí se pasa fijo `vad_threshold=0.0`.
- El filtro de silencio (`rms < 6` sobre audio de 16 bits) es casi cero: el modelo se ejecuta unas 12 veces por segundo casi siempre. Hay que medir en la fase 0 si se cumple el "< 2 % de CPU" del docstring.
- El callback pone `_paused = True` antes de llamar a `on_wake`; si la activación se ignora (`pipeline.py:159-161`), nadie reanuda la wake word hasta el siguiente `speak_done`.
- Los errores de predicción se registran en nivel `debug`: si el modelo falla, la wake word deja de funcionar sin rastro en el log normal. Si el micrófono se desconecta, el stream muere y no se reabre.
- La ruta del modelo es relativa al directorio actual.

**Propuesta:** avisar en la interfaz cuando se usa el modelo de respaldo, usar `vad_threshold` de la config y registrar los errores de predicción como `warning` (con límite de frecuencia).

### Resumen de la fase 5

4 hallazgos (2 medios por verificar, 2 bajos). El riesgo principal no está en el código en sí, sino en la combinación: VAD por energía que graba ruido (H-034) → prompt que sugiere órdenes (H-035) → atajo local que ejecuta sin preguntar (H-023/H-024). Merece una prueba en vivo en la fase 0.
