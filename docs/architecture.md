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
| Voz → texto | **faster-whisper**, modelo `small`, `cpu`, `int8`, `cpu_threads: 4`, idioma `es` | 0 MB VRAM, ~0.5 s para audios cortos, sin contexto CUDA fantasma. Se descarga tras inactividad |
| Cerebro | **Gemini API** (`google-genai`), modelo Flash actual | Function calling, rápido, capa gratuita. Nombre del modelo en `config.yaml` |
| Texto → voz | **edge-tts** (voz femenina, p. ej. `es-MX-DaliaNeural`) | Gratis, buena calidad, base para RVC |
| Voz Miku | **RVC** en subproceso aislado (`rvc_worker.py` por `stdio`/`pipe`) | Usa GPU (RTX 3050). Al matar el subproceso tras inactividad, Windows libera el 100 % de la VRAM y RAM de PyTorch |
| Activación | Atajo global (Tauri `global-shortcut`) + opcional **openWakeWord** (CPU) | Fase 7 |
| Audio | `sounddevice` (mic) | Simple y estable |

## Flujo principal y optimización de latencia

1. **Activación**: atajo (`Ctrl+Alt+M` por defecto) o palabra clave → backend envía `show`.
2. **Pre-calentamiento asíncrono**: en el mismo instante de la activación, `resources.py` lanza/despierta en segundo plano el subproceso `rvc_worker.py` y carga Whisper si estaban descargados (aprovechando los segundos que el usuario tarda en hablar para que la carga tenga **costo cero en latencia percibida**).
3. Frontend: muestra ventana → animación **aparecer** → estado `listening`.
4. Backend graba del mic hasta que el VAD detecta ~0,8 s de silencio (máx. 15 s).
5. Whisper transcribe en CPU (`int8`) → se envía `subtitle` (usuario) al frontend.
6. Gemini recibe historial corto (últimos 10 turnos) + transcripción + declaraciones de herramientas.
7. Si Gemini pide herramientas → se ejecutan (con confirmación si son destructivas) → resultado vuelve a Gemini.
8. Respuesta final con etiqueta de emoción (`[happy] ¡Listo!`) → se separa emoción y texto.
9. `edge-tts` genera wav → el subproceso `rvc_worker.py` (ya caliente en VRAM) lo convierte → wav en base64 al frontend con `speak`.
10. Frontend reproduce con lip sync + expresión + subtítulo.
11. Tras `hide_after_seconds` sin actividad (o "adiós") → animación **desaparecer** → ventana oculta, render detenido (`app.ticker.stop()`).
12. Tras `unload_after_minutes` sin uso → se termina el subproceso `rvc_worker.py` y se libera el objeto Whisper + `gc.collect()`, volviendo a **0 MB de VRAM**.

Si TTS o RVC fallan, Miku responde solo con subtítulo o con la voz base de `edge-tts` (degradación elegante, nunca se cuelga).

## Protocolo WebSocket (JSON)

Backend → Frontend:
```jsonc
{ "type": "show" }
{ "type": "hide" }
{ "type": "state", "value": "idle|listening|thinking|speaking" }
{ "type": "subtitle", "who": "user|miku", "text": "..." }
{ "type": "expression", "name": "happy" }
{ "type": "speak", "audio_b64": "...", "mime": "audio/wav", "text": "...", "emotion": "happy" }
{ "type": "confirm_request", "id": "abc", "text": "¿Cierro Chrome?" }
```
Frontend → Backend:
```jsonc
{ "type": "ready" }
{ "type": "activate" }            // atajo global o clic en Miku
{ "type": "text_input", "text": "..." }   // caja de texto opcional
{ "type": "confirm_response", "id": "abc", "ok": true }
{ "type": "speak_done" }
{ "type": "dismiss" }             // usuario la despide
```

## Ventana (Tauri)
- `transparent: true`, `decorations: false`, `alwaysOnTop: true`, `skipTaskbar: true`, `shadow: false`, `resizable: false`.
- Tamaño ~400×600, anclada abajo a la derecha sobre la barra de tareas (configurable).
- **Optimización WebView2**: en `tauri.conf.json`, configurar argumentos adicionales del navegador (`--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection --js-flags=--lite-mode`) para minimizar la huella de RAM en segundo plano.
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
   ├─ llm.py               # Gemini + historial + function calling
   ├─ tts.py               # edge-tts
   ├─ rvc.py               # gestor del subproceso de voz (start/warmup/convert/kill)
   ├─ rvc_worker.py        # script aislado que carga PyTorch/RVC en GPU
   ├─ wakeword.py          # openWakeWord (opcional)
   ├─ resources.py         # temporizador de inactividad para matar rvc_worker y descargar STT
   └─ tools/
      ├─ __init__.py       # registro + declaraciones para Gemini
      ├─ apps.py  media.py  system.py  files.py  web.py  timers.py  notes.py
```

## config.yaml (claves esperadas)

```yaml
hotkey: "Ctrl+Alt+M"
language: "es"
window: { width: 400, height: 600, anchor: "bottom-right", margin: 16, fps_visible: 30 }
behavior: { hide_after_seconds: 20, max_record_seconds: 15, silence_ms: 800, unload_after_minutes: 10 }
llm: { model: "gemini-flash-latest", max_history_turns: 10, temperature: 0.8 }
stt: { model: "small", device: "cpu", compute_type: "int8", cpu_threads: 4 }
tts: { voice: "es-MX-DaliaNeural", rate: "+5%", pitch: "+20Hz" }
rvc: { enabled: true, model: "models/rvc/miku.pth", index: "models/rvc/miku.index", f0_up_key: 6 }
wakeword: { enabled: false, model: "models/wakeword/hey_miku.onnx", threshold: 0.5 }
live2d: { model: "models/miku/miku.model3.json", scale: 0.25, expressions: { happy: "exp_01", sad: "exp_02", surprised: "exp_03", angry: "exp_04", neutral: null } }
tools: { confirm_destructive: true, file_search_roots: ["~/Desktop", "~/Documents", "~/Downloads"] }
apps: { chrome: "chrome.exe", spotify: "spotify.exe", discord: "Discord" }  # alias extra; también se escanea el menú Inicio
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