# Arquitectura

## Visión general

Dos procesos principales que se comunican por WebSocket local, más un subproceso efímero bajo demanda para la GPU (RVC):

```
┌──────────────────────────────┐        ws://127.0.0.1:8765        ┌─────────────────────────────────┐
│  app/  (Tauri v2 + TS)       │  ◄──────────────────────────────► │  core/  (Python 3.11, asyncio)  │
│  Ventana transparente        │                                   │  Activación (atajo / wake word) │
│  Live2D (PixiJS)             │                                   │  Micrófono + VAD + Whisper(CPU) │
│  Animaciones aparecer/irse   │                                   │  Gemini (function calling)      │
│  Reproducción de audio +     │                                   │  Herramientas de control del PC │
│  lip sync, subtítulos        │                                   │  edge-tts ──► [rvc_worker.py]   │
└──────────────────────────────┘                                   └──────────────────┬──────────────┘
                                                                                      │ (Subproceso GPU:
                                                                                      │  muere tras inactividad
                                                                                      ▼  = 0 MB VRAM real)
```

`start.bat` lanza primero el backend (con `pythonw` del venv, sin consola) y luego la app.

## Stack

| Parte | Tecnología | Motivo |
|---|---|---|
| Ventana | **Tauri v2** (WebView2) | Ventana transparente, siempre encima, ~3-4x menos RAM que Electron |
| Render 2D | **pixi.js v7** + **pixi-live2d-display-lipsyncpatch** | Live2D Cubism 2/3/4 con lip sync integrado (`model.speak()`). Verificar compatibilidad de versiones antes de instalar |
| Backend | Python 3.11 + `websockets` | Ligero (~50 MB RAM base), sin FastAPI |
| VAD | **silero-vad** (ONNX, CPU) | Detecta inicio/fin de voz con consumo mínimo |
| Voz → texto | **faster-whisper** `small`, `cpu`, `int8`, `cpu_threads` de la config, idioma de `language` | 0 MB VRAM, ~1,5 s por frase. Es un **filtro local**: descarta ruido y silencio, y alimenta el atajo local. Gemini oye el audio real. Se descarga tras inactividad |
| Cerebro | **Gemini API** (`google-genai`), `gemini-3.5-flash-lite` (flash solo da 20 peticiones/día gratis) | **Una petición por turno**: audio + historial + herramientas. Si un modelo falla (cuota por minuto, 503), Miku dice "Un momento..." y prueba el siguiente de una cadena de 6 (`llm.models_fallback`); Gemma, el último, recibe el texto de Whisper |
| Texto → voz | **edge-tts** (voz femenina, p. ej. `es-MX-DaliaNeural`) | Gratis, buena calidad, base para RVC |
| Voz Miku | **RVC** en subproceso aislado (`rvc_worker.py` por `stdio`/`pipe`) | Usa GPU (RTX 3050). Al matar el subproceso tras inactividad, Windows libera el 100 % de la VRAM y RAM de PyTorch |
| Activación | Atajo global (Tauri `global-shortcut`) + opcional **openWakeWord** (CPU) | Fase 7 |
| Audio | `sounddevice` (mic) | Simple y estable |

## Flujo principal y optimización de latencia

1. **Activación**: atajo (`Ctrl+Alt+M` por defecto) o palabra clave → backend envía `show`.
2. **Pre-calentamiento asíncrono**: en el mismo instante de la activación, `resources.py` lanza/despierta en segundo plano el subproceso `rvc_worker.py` y carga Whisper si estaban descargados (aprovechando los segundos que el usuario tarda en hablar para que la carga tenga **costo cero en latencia percibida**).
3. Frontend: muestra ventana → animación **aparecer** → estado `listening`.
4. Backend graba del mic hasta que el VAD detecta ~0,8 s de silencio (máx. 15 s).
5. Whisper transcribe en CPU (`int8`). Si no hay texto, o solo es el propio "¿Sí?" de Miku, se descarta: 0 peticiones.
6. **Sin Gemini (0 peticiones)**: el atajo local resuelve los comandos simples ("abre Spotify", "baja el volumen", "apunta que…", "modo trabajo"), y un "sí" a una confirmación pendiente ejecuta la acción guardada.
7. **Si no, una sola petición**: Gemini recibe el historial (últimos 10 turnos, en texto), los datos de la memoria, el **audio** (y una captura si se pregunta por la pantalla) y las declaraciones de herramientas. Solo en turnos de **texto** van también `url_context` (leer una página) y, si `llm.web_search: true`, `google_search`: Google los ejecuta dentro de la misma petición. Con audio Gemini los rechazaba (400), y el plan gratuito rechaza `google_search` (429).
8. Gemini devuelve en una respuesta `[emoción] frase` + las herramientas a usar. Las herramientas se ejecutan en local y su resultado **no** vuelve a Gemini: si falla, pide confirmación o devuelve datos, Miku lee el resultado en lugar de la frase. Si la frase dice que hizo algo sin pedir herramienta, Miku admite que no lo hizo. El subtítulo del usuario es el texto de Whisper (se probó pedirle a Gemini lo que oyó: nunca lo devolvió).
9. `edge-tts` genera wav → el subproceso `rvc_worker.py` (ya caliente en VRAM) lo convierte → wav en base64 al frontend con `speak`.
10. Frontend reproduce con lip sync + expresión + subtítulo.
11. Tras `hide_after_seconds` sin actividad, el frontend envía `idle_timeout`: Miku se despide ("¡Adiós!", frase cacheada) y el backend envía `hide` (si no llega en 8 s, el frontend se oculta solo). Tras un "adiós" del usuario, igual sin despedida extra → animación **desaparecer** → ventana oculta, render detenido (`app.ticker.stop()`).
12. Tras `unload_after_minutes` sin uso → se termina el subproceso `rvc_worker.py` y se libera el objeto Whisper + `gc.collect()`, volviendo a **0 MB de VRAM**.

Si TTS o RVC fallan, Miku responde solo con subtítulo o con la voz base de `edge-tts` (degradación elegante, nunca se cuelga).

## Protocolo WebSocket (JSON)

El servidor solo acepta conexiones cuyo `Origin` sea la app (`http://tauri.localhost`), el servidor de desarrollo (`http://localhost:1420`) o clientes locales sin `Origin` (scripts). Cualquier página web abierta en el navegador es rechazada.

Backend → Frontend:
```jsonc
{ "type": "show" }
{ "type": "hide" }
{ "type": "state", "value": "idle|listening|thinking|speaking" }
{ "type": "subtitle", "who": "user|miku", "text": "..." }
{ "type": "expression", "name": "happy" }
{ "type": "speak", "audio_b64": "...", "mime": "audio/wav", "text": "...", "emotion": "happy" }
{ "type": "stop_speaking" }        // barge-in: cortar el audio actual
// confirm_request / confirm_response: pendientes; la confirmación se hace hoy por voz (ver tools.md)
```
Frontend → Backend:
```jsonc
{ "type": "ready" }
{ "type": "activate" }            // atajo global o clic en Miku
{ "type": "text_input", "text": "..." }   // caja de texto opcional
{ "type": "shutdown" }            // "Salir" en la bandeja: apaga también el backend
{ "type": "speak_done" }
{ "type": "dismiss" }             // usuario la despide
{ "type": "idle_timeout" }        // venció el ocultado automático: el backend se despide y envía hide
```

## Ventana (Tauri)
- `transparent: true`, `decorations: false`, `alwaysOnTop: true`, `skipTaskbar: true`, `shadow: false`, `resizable: false`.
- Tamaño ~400×600, anclada abajo a la derecha sobre la barra de tareas (configurable).
- **Optimización WebView2**: en `tauri.conf.json`, configurar argumentos adicionales del navegador (`--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection`). Sin `--js-flags=--lite-mode`: medido el 23-oct, ahorraba ~1 MB de heap pero Live2D gastaba 5x más CPU (24% del hilo principal en reposo frente a 4,5%) y Miku tardaba en aparecer.
- **Click-through**: `setIgnoreCursorEvents(true)` por defecto; cada ~150 ms (solo con Miku visible) se consulta la posición del cursor y se hace hit-test contra los límites del modelo para desactivar el ignore cuando el cursor está encima. Con Miku oculta, este intervalo se detiene por completo.
- Icono en bandeja del sistema: Mostrar / Ocultar / Salir.

## Animaciones
- **Aparecer** (~600 ms): sube desde abajo + fade-in + escala con rebote (0.85 → 1.05 → 1) + unas pocas partículas/destellos (máx. ~20 sprites, se destruyen al terminar). Luego motion de saludo del modelo si existe.
- **Desaparecer** (~500 ms): pequeño salto + escala a 0 + fade-out + destellos → `window.hide()` → `app.ticker.stop()`.
- **Idle**: motions idle del modelo, parpadeo y respiración nativos de Live2D; la mirada sigue al cursor solo mientras está visible.
- Los easings se implementan a mano (sin librerías de tween).

## Estructura de carpetas

```
miku-assistant/
├─ GEMINI.md
├─ CHANGELOG.md
├─ config.yaml
├─ .env.example            # GEMINI_API_KEY=
├─ start.bat
├─ docs/
├─ models/                 # (gitignored) rvc/miku.pth, rvc/miku.index, wakeword/hey_miku.onnx
├─ app/                    # Tauri
│  ├─ index.html
│  ├─ src/
│  │  ├─ main.ts           # arranque, conexión WS, enrutado de mensajes
│  │  ├─ live2d.ts         # carga del modelo, expresiones, speak()
│  │  ├─ animations.ts     # aparecer / desaparecer / partículas
│  │  ├─ clickthrough.ts
│  │  ├─ ws.ts             # cliente WS con reconexión
│  │  └─ ui.ts             # subtítulos, caja de texto, confirmaciones
│  ├─ public/
│  │  ├─ lib/live2dcubismcore.min.js   # (gitignored, lo descarga el usuario)
│  │  └─ models/miku/                  # (gitignored) *.model3.json y recursos
│  └─ src-tauri/
└─ core/
   ├─ requirements.txt
   ├─ __main__.py
   ├─ config.py            # carga config.yaml + .env
   ├─ server.py            # WebSocket
   ├─ pipeline.py          # orquesta el flujo y dispara el pre-calentamiento
   ├─ audio_in.py          # mic + VAD
   ├─ stt.py               # faster-whisper (CPU int8, descargable)
   ├─ llm.py               # Gemini: una petición por turno, atajo local, historial, memoria
   ├─ screen.py            # captura de pantalla (GDI, sin Pillow) para "¿qué ves?"
   ├─ tts.py               # edge-tts
   ├─ rvc.py               # gestor del subproceso de voz (start/warmup/convert/kill)
   ├─ rvc_worker.py        # script aislado que carga PyTorch/RVC en GPU
   ├─ wakeword.py          # openWakeWord (opcional)
   ├─ resources.py         # temporizador de inactividad para matar rvc_worker y descargar STT
   └─ tools/
      ├─ __init__.py       # registro + declaraciones para Gemini
      ├─ apps.py  media.py  system.py  files.py  web.py  timers.py  notes.py  memory.py  routines.py
```

## config.yaml (claves esperadas)

```yaml
hotkey: "Ctrl+Alt+M"
language: "es"
window: { width: 400, height: 600, anchor: "bottom-right", margin: 16, fps_visible: 30 }
behavior: { hide_after_seconds: 20, max_record_seconds: 15, silence_ms: 800, unload_after_minutes: 10 }
llm: { model: "gemini-3.5-flash-lite", models_fallback: ["gemini-3.5-flash"], max_history_turns: 10, temperature: 0.35, web_search: false }
stt: { model: "small", device: "cpu", compute_type: "int8", cpu_threads: 4 }
tts: { voice: "es-MX-DaliaNeural", rate: "+5%", pitch: "+20Hz" }
rvc: { enabled: true, model: "models/rvc/miku.pth", index: "models/rvc/miku.index", f0_up_key: 6 }
wakeword: { enabled: false, model: "models/wakeword/hey_miku.onnx", threshold: 0.5 }
live2d: { model: "models/miku/miku.model3.json", scale: 0.25, expressions: { happy: "exp_01", sad: "exp_02", surprised: "exp_03", angry: "exp_04", neutral: null } }
tools: { confirm_destructive: true, file_search_roots: ["~/Desktop", "~/Documents", "~/Downloads"] }
apps: { chrome: "chrome.exe", spotify: "spotify.exe", discord: "Discord" }  # alias extra; también se escanea el menú Inicio
routines: { trabajo: [{ tool: "open_app", args: { app_name: "opera gx" } }] }  # "modo trabajo", 0 peticiones
log_level: "INFO"
```

## Presupuesto de recursos (objetivos medibles)

| Estado | CPU | RAM total (ambos procesos) | VRAM |
|---|---|---|---|
| Oculta, en reposo (>10 min sin uso) | < 1 % | ~200 - 300 MB | **0 MB** (subproceso GPU terminado) |
| Activa / Recién usada | picos durante STT/RVC | < 950 MB | < 2.2 GB (solo RVC en GPU) |
| Latencia | — | — | Empezar a hablar en < 3 s tras terminar de hablar el usuario |

Medidas obligatorias:
- Ticker de Pixi detenido, timer de click-through detenido y ventana oculta cuando Miku no está visible; FPS limitado a `fps_visible`.
- **Aislamiento de GPU**: `core` principal NUNCA importa `torch`. Todo uso de PyTorch/CUDA ocurre dentro de `rvc_worker.py`. Al cumplirse `unload_after_minutes`, `resources.py` mata el proceso `rvc_worker.py` para garantizar liberación real de RAM y VRAM en Windows.
- **Pre-calentamiento (`warmup`)**: Al recibir la señal de activación (`activate`), si `rvc_worker` o `stt` no están activos, se inician en segundo plano inmediatamente mientras el usuario habla.
- El mic solo mantiene el stream abierto tras la activación (salvo que el wake word esté activo, que procesa a 16 kHz en CPU).
- Las texturas del modelo Live2D, si son de 4096 px, se deben reducir a 2048 px.