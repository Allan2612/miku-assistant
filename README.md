# Miku Assistant

Asistente de escritorio para Windows: una Miku 2D (Live2D) que aparece con una animación, escucha lo que le pides por voz o texto, responde con su voz y controla el PC con un conjunto cerrado de herramientas. Proyecto personal.

El objetivo de diseño es **consumo casi nulo en reposo** y **respuesta en menos de 3 s** al activarla.

> **English summary:** Windows desktop voice assistant with a Live2D avatar. Wake word or hotkey → Whisper STT (CPU) → Gemini function calling over a closed tool set, with live PC state (windows and tabs by number) → edge-tts + RVC voice on an isolated GPU worker. Designed for near-zero idle usage (0 MB of VRAM when idle) and sub-3-second responses. Tauri v2 + TypeScript frontend, Python asyncio backend, Opera extension. Personal project.

## Cómo funciona

Dos procesos que hablan por WebSocket local (`ws://127.0.0.1:8765`), más un subproceso de GPU para la voz y una extensión de Opera opcional:

```
app/  (Tauri v2 + TypeScript)  ◄──── WebSocket ────►  core/  (Python 3.14, asyncio)
  Ventana transparente                                   Activación (atajo / wake word)
  Live2D con PixiJS                                      Micrófono + VAD + Whisper (CPU)
  Animaciones, lip sync, subtítulos                      Gemini con function calling
                                                         Herramientas del PC
                                                         edge-tts ──► rvc_worker.py (GPU)
browser-extension/  (Opera) ◄─── WebSocket ───►  core/
  Pestañas por número, resultados de búsqueda
```

Flujo de una petición:

1. **Activación** con `Ctrl+Alt+M` o la palabra clave "hey Miku". Whisper revisa en paralelo el audio de la palabra clave: una activación claramente falsa (silencio, o alguien hablando de otra cosa) se descarta sin gastar petición.
2. En ese mismo instante se precarga el worker de RVC, mientras el usuario todavía habla.
3. Se graba hasta detectar silencio y Whisper transcribe en CPU (`int8`). Las órdenes inequívocas (volumen, pausa, temporizadores, notas...) se resuelven en local, sin Gemini.
4. Gemini recibe el audio y el **estado del PC** (ventanas y pestañas con su número, volumen, recordatorios, pendientes) y actúa como agente: llama herramientas, ve sus resultados y responde o da otro paso. Las acciones destructivas piden confirmación.
5. edge-tts genera la voz base y RVC la convierte a la voz de Miku.
6. El frontend la reproduce con lip sync, expresión y subtítulo. Tras la respuesta el micrófono sigue abierto unos segundos (modo conversación).
7. Tras un rato sin uso, Miku se oculta y deja de renderizar. Más tarde se mata el worker de RVC (0 MB de VRAM) y queda otro en espera con las librerías ya cargadas, solo en RAM, para que la voz vuelva en 3-5 s. Whisper se queda cargado: solo ocupa RAM.

Miku tiene una sola voz: si RVC está cargando, la respuesta espera; si falla, responde solo con subtítulo, nunca con otra voz. Nunca se cuelga.

### Decisiones clave

- **Nada de `torch` en el proceso principal.** En Windows, inicializar CUDA deja 300–500 MB residentes que no se liberan. Por eso RVC corre en un subproceso aislado que se puede matar, y Whisper corre en CPU.
- **Herramientas en lista cerrada** ([docs/tools.md](docs/tools.md)), registradas con el decorador `@tool`. El LLM nunca ejecuta comandos de shell arbitrarios.
- **Sin frameworks de UI**: TypeScript + Vite en vanilla, para mantener baja la RAM de WebView2.
- **Atajo local solo para órdenes inequívocas** (volumen, media, temporizadores, notas): se ejecutan sin pasar por Gemini. Lo que depende de qué hay abierto (apps, webs, pestañas, ventanas) lo decide Gemini con el estado del PC.
- **Ventanas y pestañas por número**, como objetos: el modelo ve la lista y actúa sobre un número concreto, en vez de adivinar por el título o simular teclas.

## Estructura

| Ruta | Contenido |
|---|---|
| [core/](core/) | Backend: `server.py` (WebSocket), `pipeline.py` (orquestación), `llm.py` (Gemini, bucle de agente), `intent.py` (qué es cada frase oída), `state.py` (estado del PC), `browser.py` (puente con Opera), `stt.py`, `tts.py`, `rvc.py` + `rvc_worker.py`, `wakeword.py`, `audio_in.py`, `resources.py` |
| [core/tools/](core/tools/) | Herramientas del PC: apps, ventanas, archivos, media, notas, memoria, rutinas, sistema, temporizadores, web |
| [browser-extension/](browser-extension/) | Extensión de Opera (pestañas por número); instalación en su [README](browser-extension/README.md) |
| [core/infer_pack/](core/infer_pack/) | Modelos de RVC (VITS, RMVPE) |
| [app/src/](app/src/) | Frontend: `live2d.ts`, `animations.ts`, `clickthrough.ts`, `ui.ts`, `ws.ts`, `main.ts` |
| [app/src-tauri/](app/src-tauri/) | Shell de Tauri en Rust (ventana, bandeja, atajo global) |
| [docs/](docs/) | Arquitectura, roadmap, herramientas, persona y preparación |
| [scratch/](scratch/) | Scripts de prueba y diagnóstico; `voice_ab.py` compara voces de oído |
| [config.yaml](config.yaml) | Toda la configuración ajustable |

## Requisitos

- Windows 10/11 con GPU NVIDIA (probado en RTX 3050 de 8 GB)
- Python 3.14 (la versión del venv actual), Node.js 20+, Rust (`rustup`) y Microsoft C++ Build Tools
- API key de Gemini (Google AI Studio)

Recursos que **no** están en el repo y hay que conseguir aparte (detalles en [docs/setup.md](docs/setup.md)):

- Modelo Live2D de Miku en `app/public/models/miku_official/`
- `live2dcubismcore.min.js` del Cubism SDK for Web en `app/public/lib/`
- Modelo RVC de Miku (`.pth` y `.index`) en `models/rvc/`
- (Opcional) wake word `hey_miku.onnx` en `models/wakeword/`
- (Opcional) cargar `browser-extension/` en Opera GX para manejar pestañas

## Puesta en marcha

```bat
:: Clave de Gemini
copy .env.example .env
:: (pega tu GEMINI_API_KEY en .env)

:: Backend
cd core
py -3.14 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu126
cd ..

:: Frontend
cd app
npm install
npm run tauri build
cd ..

:: Arrancar y detener
start.bat
stop.bat
```

El arranque con Windows se activa o se quita en el panel: Configuración → «Arrancar con Windows».

## Documentación

- [docs/architecture.md](docs/architecture.md): arquitectura, protocolo WebSocket y presupuesto de recursos
- [docs/roadmap.md](docs/roadmap.md): fases del proyecto
- [docs/tools.md](docs/tools.md): herramientas disponibles
- [docs/plan-siguiente.md](docs/plan-siguiente.md): plan actual (fases A-F) y lo que queda pendiente
- [docs/persona.md](docs/persona.md): personalidad, emociones y frases fijas
- [CHANGELOG.md](CHANGELOG.md): historial de cambios
- [docs/auditoria/plan.md](docs/auditoria/plan.md): plan de auditoría total y sus [hallazgos](docs/auditoria/hallazgos/)

## Licencia y recursos de terceros

El código de este repositorio se publica bajo la [licencia MIT](LICENSE). El repositorio **no incluye** el modelo Live2D, el Cubism SDK ni el modelo de voz RVC: cada uno tiene su propia licencia y se consigue aparte (ver [docs/setup.md](docs/setup.md)). Hatsune Miku es un personaje de Crypton Future Media. Este es un proyecto personal sin fines comerciales.
