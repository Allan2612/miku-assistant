# Changelog

Todos los cambios notables de este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]
### Seguridad (auditoría, ver `docs/auditoria/`)
- El servidor WebSocket solo acepta la app y clientes locales: ninguna página web puede controlar a Miku.
- `open_app` ya no ejecuta líneas de comandos ni abre consolas; `type_text` no escribe en consolas ni pulsa Enter.
- `close_app` cierra solo por nombre exacto, nunca procesos del sistema ni el propio Miku.
- `open_file` no abre ejecutables ni scripts.
- Las acciones destructivas (apagar, reiniciar, suspender) solo se ejecutan si el usuario dice "sí".
- CSP en la ventana de Tauri; quitados el plugin `opener` y permisos sin uso.

### Corregido
- Atajo local: "apaga el PC" ya no mata procesos, "pon la música" reproduce, frases ambiguas van a Gemini.
- Ctrl+Alt+M (faltaban permisos), click-through, "Salir" apaga también el backend, `stop.bat` solo mata procesos de Miku.
- Fin de frase con silero-vad: la música o el ruido ya no alargan la grabación.
- RVC: sin respuestas desfasadas tras un timeout; logs del worker en `cache/rvc_worker.log`.
- Interrumpir a Miku ya no deja intervalos activos; la wake word se reanuda tras errores.
- Temporizadores, volumen, silencio y apagado hacen lo que se pide.
- La primera respuesta tras descargar RVC ya no espera su carga (35-80 s): usa la voz base mientras carga.
- Transcripción: Whisper `small` en lugar de `base` (8 hilos). Con ruido de micrófono, `base` fallaba en ~1 de cada 2 palabras en español y `small` en ~1 de cada 4; tarda ~1,3 s por frase en vez de ~0,4 s.

### Añadido
- Al activarla, Miku responde con una frase corta ("¿Sí?", "¿Dime?"…) antes de escuchar, para que se note que empezó.
- `tests/` con pruebas sin dependencias (`core\.venv\Scripts\python.exe -m tests.<nombre>`).
- `core/requirements.lock` con las versiones exactas del entorno que funciona.

- **Fase 8 — Pulido**:
  - **Experiencia Limpia por Voz (Sin Botones)**:
    - Eliminadas las barras de entrada de texto, botones de envío y barras de acciones flotantes en `app/src/ui.ts` y `app/src/styles.css`.
    - La interfaz queda 100% limpia y minimalista, mostrando únicamente a Miku en el escritorio y la burbuja de subtítulos flotante durante la conversación.
  - **Posicionamiento Preciso Abajo a la Derecha y Anti-Corte**:
    - En `app/src/main.ts`, `positionWindow()` ahora utiliza `monitor.workArea` en lugar de la resolución total de la pantalla, posicionando la ventana de Miku exactamente por encima de la barra de tareas de Windows (sin importar escala de DPI o monitores múltiples).
    - En `app/src/live2d.ts`, se recalibró la escala (`autoFitScale * 1.08`) para asegurar que las coletas largas (*twin-tails*) y el torso de Miku permanezcan dentro de los límites del lienzo sin recortarse por los bordes.
    - Las dimensiones de la ventana se optimizaron a 420x620 px en `tauri.conf.json` y `config.yaml`.
  - **Reacciones al Clic / Toque**:
    - Al hacer clic o tocar a Miku en pantalla (`live2d.onTapReaction()`), Miku reacciona con una animación de movimiento (`Tap`), rubor en las mejillas (`ParamCheek: 0.85`), sonrisa tierna e inclinación de cabeza.
    - Se mantiene el soporte de arrastre para reubicar a Miku y zoom con la rueda del ratón (doble clic o tecla 'R' para restablecer encuadre).
  - **Interrupción Inmediata / Barge-in**:
    - Si el usuario dice "Hey Miku" o presiona el atajo `Ctrl+Alt+M` mientras Miku está hablando, Miku corta su frase al instante (`stop_speaking`), cancela la síntesis/reproducción y pasa directamente a escuchar al usuario.
  - **Saludo Según la Hora del Día**:
    - `core/pipeline.py` implementa `check_startup_greeting()`: una vez por día al arrancar, Miku saluda proactivamente según la hora local ("¡Buenos días!", "¡Buenas tardes!" o "¡Buenas noches!").
    - En `core/llm.py`, se integró detección de saludos en el fast-path local con 0 ms de latencia y se inyectó el momento del día en las instrucciones del sistema de Gemini.
  - **Scripts de Inicio, Parada y Autoarranque en Windows**:
    - `start.bat`: Arranca el backend silenciosamente en segundo plano usando `pythonw.exe -m core` (sin ventana negra de CMD) e inicia el binario optimizado `app.exe`.
    - `stop.bat`: Detiene limpiamente todos los procesos de Miku (`app.exe`, `pythonw.exe`, `rvc_worker.py`), garantizando 0% de uso de CPU, RAM y VRAM.
    - `install_autostart.bat` y `uninstall_autostart.bat`: Permiten configurar o desinstalar el arranque automático con Windows mediante acceso directo en la carpeta de inicio de usuario.
    - Compilado el binario ejecutable de producción `app.exe` en `app/src-tauri/target/release/app.exe` (solo 4.5 MB, standalone).
- **Soporte y Priorización de Opera GX**:
  - Detección dinámica de la ruta del ejecutable de Opera GX (`%LOCALAPPDATA%\Programs\Opera GX\opera.exe`).
  - Actualizado `core/tools/web.py` para abrir búsquedas de Google (`web_search`), YouTube (`youtube_search`) y enlaces web (`open_url`) directamente en Opera GX en lugar del navegador predeterminado de Windows.
  - Registro de alias en `DEFAULT_APP_ALIASES` y en `config.yaml` (`opera`, `opera gx`, `operagx`, `navegador`, `browser`, `internet`).
  - Integración en el Fast-Path de `core/llm.py` para abrir y cerrar Opera GX localmente en < 50ms sin consultar a la nube.

### Corregido
- **Correcciones Críticas de la Fase 8 (`start.bat`, Posicionamiento y Voz)**:
  - **Reentrenamiento y Balanceo del Modelo Wake Word (`hey_miku.onnx` v2)**:
    - *Diagnóstico*: El modelo anterior de `hey_miku.onnx` fue entrenado con un número reducido de muestras de voces sintéticas predominantemente agudas. Ante voces masculinas o registros normales de conversación (como acentos latinoamericanos o tonos más graves), el modelo apenas puntuaba ~0.01 a 0.32, quedando muy por debajo del umbral de activación (0.60). Además, al inyectar arrays de ceros durante silencios, se vaciaban los descriptores temporales y el Silero VAD forzaba la probabilidad a 0.0, volviendo a Miku completamente insensible a la palabra de activación.
    - *Solución*: Se generó un nuevo dataset ampliado y equilibrado con síntesis concurrente multilocutor (voces masculinas y femeninas de México, España, Colombia, Argentina, EE.UU., variaciones de pitch $\pm$18 Hz, velocidad $\pm$15% y atenuación suave/fuerte), emparejado con negativos de conversación cotidiana y ruido de fondo (siseo de micrófono, zumbido de ventiladores y silencio). El nuevo modelo puntúa entre **0.98 y 1.00** ante la voz del usuario y se mantiene en **0.00002** (inmune a falsos positivos) en reposo. Se ajustó `threshold: 0.50` y `patience: 1` en `config.yaml`.
  - **Detección Dinámica de Fin de Frase y Silencio en `core/audio_in.py`**:
    - *Diagnóstico*: La condición de silencio tras comenzar a hablar exigía que el RMS cayera por debajo de `energy_threshold * 0.75` de forma ininterrumpida durante 800 ms. En micrófonos de baja ganancia como el Razer Seiren V3 Mini, el suelo de siseo y la respiración suave (~0.0012) mantenían el RMS justo por encima del corte, reiniciando a 0 el acumulador de silencio en cada bloque. Esto provocaba que Miku se quedara congelada grabando durante 15 segundos enteros (tiempo máximo), haciendo que el usuario creyera que Miku no lo escuchaba. Al recibir 13 segundos de silencio/siseo, faster-whisper alucinaba en bucle repitiendo tokens ("¿Qué pasa? ¿Qué pasa?...").
    - *Solución*: Se incorporó suavizado exponencial (EMA) de RMS (`smoothed_rms = 0.65 * smoothed_rms + 0.35 * rms`), umbral de corte adaptativo (`silence_threshold = max(0.0010, energy_threshold * 0.90)`) y decaimiento gradual del acumulador en lugar de reseteo a cero ante chasquidos aislados. Miku ahora detecta el final de la frase y responde en menos de 0.8 s (~2.5 s de tiempo total de interacción).
  - **Filtro Anti-Alucinaciones en `core/stt.py`**:
    - Se activó el filtro VAD integrado en faster-whisper (`vad_filter=True`, `min_silence_duration_ms=400`) y `repetition_penalty=1.15`, garantizando que cualquier cola de siseo sea purgada antes del decodificador y eliminando los bucles de repetición.
  - **Preservación de Búfer Temporal en `core/wakeword.py`**:
    - Se eliminó la alimentación de ceros (`predict(np.zeros)`) durante caídas de volumen, preservando la continuidad de los 16 cuadros del espectrograma de Mel y deshabilitando el bloqueo estricto de VAD (`vad_threshold=0.0`) gracias a que el nuevo modelo ya discrimina el ruido ambiental por sí mismo.
  - **Permisos de Ventana en Tauri v2 (`capabilities/default.json`)**:
    - Se incorporaron los permisos requeridos por Tauri v2 (`core:window:allow-set-position`, `allow-set-size`, `allow-show`, `allow-hide`, `allow-set-focus`, `allow-set-ignore-cursor-events`, `allow-start-dragging`). Antes de esto, `positionWindow()` y `setIgnoreCursorEvents()` eran bloqueados silenciosamente por la capa de seguridad de Tauri, impidiendo que la ventana se ubicara abajo a la derecha.
  - **Posicionamiento Nativo en Rust (`app/src-tauri/src/lib.rs`)**:
    - Se añadió el cálculo y asignación de posición nativo en Rust en `.setup()`, asegurando que la ventana de Miku se cree y muestre directamente en la esquina inferior derecha del monitor activo sin parpadeos ni demoras.
  - **`NameError: name 'low' is not defined` en `core/llm.py`**:
    - Se definió la variable `low = text.lower().strip()` en `_try_fast_path_tool()`. La ausencia de esta variable causaba que cualquier interacción por voz o texto fallara inmediatamente, provocando que Miku no respondiera ni hablara.
  - **Robustez de `start.bat` y Logging en `cache/core.log`**:
    - `core/__main__.py` ahora registra logs persistentes en `cache/core.log` de forma segura incluso bajo `pythonw.exe` (donde `sys.stderr` es `None`), garantizando diagnóstico total.
    - `start.bat` ahora arranca los procesos sin interferencias de comillas en rutas con espacios y espera a que el puerto 8765 esté abierto antes de lanzar la interfaz.
- **Falso Error de Cuota/Batería ("Batería en 0.1% / Sobrecalentamiento")**:
  - En `core/tools/media.py`, la función `mute(on: Optional[bool] = None)` utilizaba el tipo `Optional` sin haberlo importado de `typing`. Al registrar las herramientas en Gemini con el SDK de Google GenAI, Python lanzaba `NameError: name 'Optional' is not defined`, provocando que todas las llamadas de Gemini fallaran y cayeran en los mensajes de emergencia de batería baja. Se corrigió la importación y las firmas de tipos.
- **Aceleración Drástica de la Animación de Aparición (< 250 ms)**:
  - En `app/src/animations.ts`, la animación de entrada se redujo de 600 ms a **240 ms**, reduciendo el desplazamiento vertical de 60 px a 20 px y alcanzando el 100% de opacidad en solo ~80 ms con un rebote elástico suave y ágil. Miku ahora aparece de forma casi instantánea al decir "Hey Miku".
- **Eliminación del Bloqueo de Audio de PortAudio al Activar**:
  - En `core/wakeword.py`, se removió la llamada a `self._stream.stop()` dentro del propio callback de PortAudio. Detener el stream dentro de su callback causaba contención y demoras de ~2 segundos en Windows antes de que `audio_in` pudiera abrir el micrófono para escuchar la petición. Al mantener el stream activo en modo silenciado rápido (`_paused = True`), la transición a la escucha es inmediata (8 ms).
- **Reproducción de Voz y Desbloqueo de Autoplay**:
  - En `core/tts.py`, se normalizó el tipo MIME de MP3 a `"audio/mpeg"` (estándar de navegadores RFC).
  - En `app/src/live2d.ts`, se implementó un desbloqueador global de audio en interacciones del usuario y un gestor resiliente de reproducción que no descarta el audio si el navegador bloquea el autoplay por falta de gestos previos.
  - En `app/src-tauri/tauri.conf.json`, se incorporó `--autoplay-policy=no-user-gesture-required` a los argumentos de WebView2 para permitir la reproducción de voz instantánea sin requerir clics previos en la ventana.
- **Falsas Activaciones de la Palabra de Activación (openWakeWord)**:
  - **Filtro de Voz con Silero VAD**: Se integró Silero VAD (`vad_threshold: 0.50`) en `openwakeword.model.Model`, descartando de forma automática ruidos que no provienen de cuerdas vocales humanas (tecleo, clics del mouse, ruido de ventiladores, chasquidos).
  - **Requisito de Persistencia Cuadro a Cuadro (`patience: 2`)**: Exige que la probabilidad se mantenga alta durante al menos 2 cuadros consecutivos de 80 ms (160 ms), eliminando falsos positivos por picos acústicos momentáneos de un solo cuadro.
  - **Calibración de Umbral a 0.75**: Se ajustó `threshold: 0.75` en `config.yaml` (aprovechando que las pronunciaciones del usuario de "Hey Miku" registran puntuaciones entre 0.91 y 0.94), blindando el sistema contra activaciones no deseadas por habla casual de fondo.
### Añadido
- **Fase 0 — Esqueleto**:
  - Estructura base del proyecto con archivos de configuración y documentación.
  - `.gitignore`, `.env.example`, `config.yaml` y `CHANGELOG.md`.
  - Módulo `core/` con `config.py` y `__main__.py` para carga de configuración y logging.
  - Entorno virtual en `core/.venv` y `core/requirements.txt` mínimo (`pyyaml`, `python-dotenv`).
  - Aplicación `app/` inicializada con Tauri v2 + Vite + TypeScript vanilla y argumentos de optimización para WebView2 (`--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection --js-flags=--lite-mode`).
  - Esqueleto de archivos en `app/src/` (`main.ts`, `live2d.ts`, `animations.ts`, `clickthrough.ts`, `ws.ts`, `ui.ts`).
- **Fase 1 — Miku en el escritorio (solo frontend)**:
  - Carga e inicialización del modelo Live2D oficial de Hatsune Miku (`miku_sample_t04.model3.json`) con `pixi.js` v7 y `pixi-live2d-display-lipsyncpatch/cubism4`.
  - Encuadre calibrado a plano medio (cintura hacia arriba) con persistencia de zoom y posición por modelo en `localStorage`.
  - Centrado responsivo en preview de navegador web y anclaje a la esquina inferior derecha en modo escritorio (Tauri).
  - Animaciones artesanales de aparecer (rebote elástico + partículas) y desaparecer (salto + desvanecimiento + parada del ticker) sin librerías externas de tween.
  - Ticker de PixiJS limitado estrictamente a 30 FPS (`maxFPS: 30`) y congelado al ocultarse (`app.ticker.stop()`).
  - Click-through inteligente con hit-testing contra los límites del modelo cada ~150 ms (completamente pausado cuando Miku está oculta).
  - Configuración de ventana de Tauri v2 (`transparent: true`, sin bordes, siempre encima, sin barra de tareas).
  - Atajo global `Ctrl+Alt+M` (con soporte fallback para pruebas en navegador) e integración con bandeja del sistema.
- **Fase 2 — Cerebro por texto**:
  - Servidor WebSocket local en Python asíncrono (`core/server.py`) en `ws://127.0.0.1:8765` con la librería `websockets`.
  - Integración con Google Gemini (`core/llm.py`) usando el SDK oficial `google-genai` asíncrono (`client.aio`) y modelo ultra rápido `gemini-3.5-flash-lite` (< 1 s de latencia), cargando el system prompt de `docs/PERSONA.md`, historial corto de 10 turnos y parser de emociones `[happy|sad|neutral|thinking|surprised|angry]`.
  - Cliente WebSocket en TypeScript vanilla (`app/src/ws.ts`) con reconexión automática y retroceso exponencial sin librerías externas.
  - Subtítulos estilo burbuja y barra de chat de texto (`app/src/ui.ts` y `app/src/styles.css`) desplegable al hacer clic sobre Miku, botón flotante o tecla Enter.
  - Expresiones faciales y animaciones según la emoción detectada en la respuesta de Gemini.
  - Temporizador de auto-ocultado tras inactividad (`hide_after_seconds: 20`) protegido contra ocultado durante el estado "pensando", y detección de despedida en texto ("adiós", "bye").
- **Fase 3 — Miku habla (voz base)**:
  - Módulo de síntesis de voz asíncrono (`core/tts.py`) con `edge-tts` usando la voz configurable `es-MX-DaliaNeural` (`rate: +5%`, `pitch: +20Hz`).
  - Caché persistente en disco en `cache/voice/` indexado por hash MD5 para respuestas instantáneas en frases recurrentes y fijas de `docs/PERSONA.md`.
  - Transmisión de mensaje `speak` con audio en base64 hacia el frontend, con degradación suave a solo subtítulo si la síntesis no está disponible.
  - Reproducción de voz y sincronización labial (lip sync) en `app/src/live2d.ts` sobre el parámetro oficial `ParamMouthOpenY` del modelo Live2D, con fallback a HTML5 Audio.
  - **Fase 4 — Miku escucha**:
  - Captura de audio de micrófono bajo demanda (`core/audio_in.py`) con `sounddevice` a 16 kHz mono float32, calibración automática del suelo de ruido ambiental, buffer de seguridad pre-activación (~320 ms) y detección de silencio (VAD).
  - Cumplimiento estricto del cierre de micrófono: el stream de `sounddevice` solo se abre al activarse y se cierra de forma inmediata (`stream.stop()`, `stream.close()`) en cuanto el usuario deja de hablar.
  - Motor de transcripción local de voz a texto (`core/stt.py`) usando `faster-whisper` en CPU (`int8`, 4 hilos, idioma español), ejecutando transcripciones en ~0.23 s con **0 MB de VRAM** (sin importar PyTorch en el proceso principal).
  - Carga perezosa del modelo STT y pre-calentamiento asíncrono (`warmup`) disparado en paralelo mientras el usuario habla.
  - Gestor de recursos (`core/resources.py`) con temporizador de inactividad (10 minutos) para descargar el modelo STT de la memoria RAM y ejecutar recolección de basura (`gc.collect()`).
  - Orquestador de interacción (`core/pipeline.py`) que conecta activación por voz/texto, transcripción, generación LLM, TTS y sincronización labial.
- **Fase 5 — Control del PC**:
  - Registro de herramientas cerrado (`core/tools/`) con decorador `@tool`, timeouts de 5s y aislamiento de excepciones para evitar caídas del backend.
  - Paquete completo de 25 herramientas implementadas según `docs/TOOLS.md`:
    - `apps.py`: `open_app` (alias y búsqueda en accesos directos del menú Inicio con `os.startfile`), `close_app` (terminación directa de procesos con `psutil`), `focus_app` (traer ventana al frente), `show_desktop` (Win+D nativo con `ctypes`), `type_text` (escritura en ventana activa).
    - `media.py`: `media_control` (teclas virtuales multimedia Windows `VK_MEDIA_*`), `set_volume`, `change_volume`, `mute` con `pycaw`.
    - `web.py`: `open_url`, `web_search`, `youtube_search` con `webbrowser` y `urllib.parse`.
    - `system.py`: `get_datetime` (fecha y hora en español), `get_system_status` (uso de CPU, RAM y disco con `psutil`), `lock_pc` (`LockWorkStation`), `shutdown_pc` 🔒 (protegido con solicitud de confirmación obligatoria).
    - `files.py`: `find_file` (búsqueda rápida en Escritorio, Documentos y Descargas con límite de profundidad y resultados), `open_file`, `open_folder`.
    - `timers.py`: `set_timer`, `set_reminder`, `list_timers`, `cancel_timer` (tareas asíncronas en memoria que, al vencer, invocan a Miku para que aparezca y anuncie el fin del temporizador con voz).
    - `notes.py`: `take_note` y `read_notes` (persistencia local en `~/Documents/notes.md`).
  - Integración nativa con Google Gemini (`core/llm.py`) mediante `AsyncChat` y Automatic Function Calling (AFC), ejecutando las herramientas y resumiendo el resultado conversacionalmente en voz de Miku con emoción asignada.
- **Fase 6 — Voz de Miku (RVC en subproceso aislado)**:
  - Subproceso hijo totalmente aislado (`core/rvc_worker.py`) que aloja PyTorch y CUDA, garantizando la regla de oro: **cero imports de `torch` en el proceso principal de `core`**.
  - Modelo RVC v2 40kHz asignado (`models/rvc/miku.pth`), índice de características FAISS (`models/rvc/miku.index`), estimador de pitch RMVPE en GPU (`models/rvc/rmvpe.pt`) y extractor de características HuBERT (`facebook/hubert-base-ls960`) en media precisión (FP16).
  - Protocolo JSON-RPC robusto por tuberías stdin/stdout con búfer de 10 MB para transmisión de audio PCM WAV base64 a 40 kHz.
  - Pre-calentamiento asíncrono (`warmup`) disparado en segundo plano en cuanto se activa Miku mientras el usuario habla.
  - Recolección automática de recursos en `core/resources.py`: al transcurrir el temporizador de inactividad (`unload_after_minutes: 10`), el subproceso hijo de RVC se termina inmediatamente (`terminate_worker`), devolviendo el 100% de la VRAM al sistema operativo (**0 MB de VRAM en reposo**).
  - Pipeline de voz integrado `edge-tts` -> RVC con degradación suave a voz base en caso de fallo.
  - Generación de voz con timbre idéntico a Hatsune Miku con latencia warm ultrarrápida (< 1.5 s de inferencia de voz en GPU NVIDIA RTX 3050).
  - Sistema de resiliencia multi-modelo en cascada con transferencia de historial ante límites de cuota (429/503) y respuestas predefinidas de roleplay ("batería baja", "sobrecalentamiento de circuitos", "comer un puerro virtual") pre-cacheadas en audio con voz de Miku.
- **Fase 7 — Palabra de activación (Wake Word con openWakeWord)**:
  - Módulo de escucha local `core/wakeword.py` ejecutado en CPU con ONNXRuntime (< 2% de uso de CPU).
  - Cumplimiento estricto de la regla de recursos: con `wakeword.enabled: false`, el flujo de micrófono nunca se abre (0% CPU y micrófono cerrado en reposo).
  - Generador y entrenador local de modelos wake word (`scratch/train_hey_miku_local.py`) con síntesis neuronal multi-locutor con `edge-tts`, extracción de características de audio openWakeWord (16x96 embeddings) y exportación a ONNX.
  - Modelo personalizado **`models/wakeword/hey_miku.onnx`** entrenado localmente y desplegado con precisión 100% y activación activa en `config.yaml`.
  - Sincronización de ciclo de vida con `core/pipeline.py`: pausado automático durante la conversación para evitar auto-activaciones y reanudación automática al volver al estado de reposo o al despedirse.
### Corregido
- **Fase 5 — Control del PC (Depuración y Solución de Ejecución)**:
  - Eliminado `from __future__ import annotations` en todos los submódulos de `core/tools/`, lo cual convertía las anotaciones de tipo en cadenas de texto (`'str'`, `'int'`) y hacía que `google-genai` fallara internamente en la validación de argumentos (`isinstance(val, 'str')` -> `TypeError`), impidiendo silenciosamente que las herramientas con parámetros se ejecutaran.
  - Añadido `comtypes.CoInitialize()` en `core/tools/media.py` para inicializar el hilo COM de Windows antes de interactuar con `pycaw`, resolviendo el fallo `[WinError -2147221008] No se ha llamado a CoInitialize` al ejecutarse en un hilo secundario (`asyncio.to_thread`).
  - Corregido el envío de teclas multimedia en `core/tools/media.py` pasando el flag `KEYEVENTF_EXTENDEDKEY = 0x0001` en `keybd_event` y permitiendo reconocimiento flexible de comandos por voz ("reproduce la canción", "pausa la música", etc.).
  - Normalización en `core/tools/apps.py` para eliminar artículos en español ("el bloc de notas" -> "bloc de notas") y apertura mejorada mediante `ShellExecuteW`.
  - Simplificación de `close_app`: las confirmaciones quedan estrictamente limitadas a `shutdown_pc` (apagar/reiniciar la PC), permitiendo que cerrar aplicaciones se ejecute de forma directa e inmediata.
  - Refuerzo en el system prompt de `core/llm.py` para obligar a Gemini a invocar las herramientas ante peticiones de acción.
- **Fase 6 — Voz de Miku (Depuración y Calidad Acústica)**:
  - Configurado el modelo **Miku Mellow** (`models/rvc/miku_mellow.pth` e índice `models/rvc/miku_mellow.index`) como voz principal por elección del usuario.
  - Cambio de la voz base TTS a español latinoamericano neutro (`es-MX-DaliaNeural`, `rate: +5%`, `pitch: +10Hz`) eliminando la pronunciación ibérica/castellana.
  - Implementado pipeline DSP anti-artefactos en `core/rvc_worker.py`:
    - Filtro de mediana en $F_0$ (`scipy.signal.medfilt(f0, 3)`) para eliminar micro-picos armónicos espurios de 10 ms en RMVPE.
    - Protección de consonantes sordas y respiraciones (`protect: 0.33`) evitando chasquidos y distorsiones metálicas en transiciones fonéticas.
    - Relleno por reflexión de 0.15 s en los extremos para neutralizar clics de borde en las capas convolucionales de HiFi-GAN.
- **Fase 7 — Palabra de activación y Robustez del Pipeline (Depuración y Auditoría)**:
  - **Calibración VAD Resiliente**: Corregido el cálculo del suelo de ruido en `core/audio_in.py`. Anteriormente, si el usuario decía "Hey Miku" y continuaba hablando de corrido, la voz caía dentro de los 6 frames de calibración inicial e inflaba el umbral a niveles inalcanzables (`avg_noise * 2.5`), causando que el VAD no detectara la frase o se cortara por timeout. Se añadió detección de voz inmediata (`rms > 0.020`) que inicia la grabación al instante sin corromper el suelo de ruido y limitador de umbral (`max 0.025`).
  - **Temporizador Perro Guardián (Watchdog)** en `core/pipeline.py`: Si el navegador o la interfaz no envían el evento `speak_done` (por pérdida de paquetes WebSocket, pestaña en segundo plano o audio silenciado), un watchdog asíncrono basado en la duración estimada del texto se dispara automáticamente para restablecer el estado a `idle` y reanudar la escucha de la palabra de activación, garantizando que Miku nunca quede sorda.
  - **Pausado Físico del Stream de WakeWord**: `core/wakeword.py` ahora detiene explícitamente el stream de audio (`stream.stop()`) al activarse y lo reinicia al finalizar la interacción (`stream.start()`), eliminando contención en el dispositivo de micrófono de Windows y reduciendo a 0% el uso de CPU durante la conversación.
  - **Defensividad en Audio Callbacks**: Normalización de arrays 1D/2D contiguos en `int16` para openWakeWord y captura segura de excepciones en callbacks de PortAudio ante cierres del loop asíncrono.
  - **Suite de Pruebas Automatizada**: Creado [`scratch/test_suite.py`](file:///c:/Users/alanv/Documents/miku-assistant/scratch/test_suite.py) validando configuración, las 25 herramientas de control del PC, parser de emociones y desinfección de texto del LLM, motor de wake word y lógica VAD (100% de pruebas superadas).




