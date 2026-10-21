# Miku Assistant

Asistente de escritorio para Windows: una Miku 2D (Live2D) que aparece con una animación, escucha lo que le pides por voz o texto, responde con su voz y controla el PC con un conjunto cerrado de herramientas. Proyecto personal.

El objetivo de diseño es **consumo casi nulo en reposo** y **respuesta en menos de 3 s** al activarla.

## Cómo funciona

Dos procesos que hablan por WebSocket local (`ws://127.0.0.1:8765`), más un subproceso de GPU que solo existe mientras se usa:

```
app/  (Tauri v2 + TypeScript)  ◄──── WebSocket ────►  core/  (Python 3.14, asyncio)
  Ventana transparente                                   Activación (atajo / wake word)
  Live2D con PixiJS                                      Micrófono + VAD + Whisper (CPU)
  Animaciones, lip sync, subtítulos                      Gemini con function calling
                                                         Herramientas del PC
                                                         edge-tts ──► rvc_worker.py (GPU)
```

Flujo de una petición:

1. **Activación** con `Ctrl+Alt+M` o la palabra clave "hey Miku".
2. En ese mismo instante se precargan Whisper y el worker de RVC, mientras el usuario todavía habla.
3. Se graba hasta detectar silencio y Whisper transcribe en CPU (`int8`).
4. Gemini responde y, si hace falta, llama herramientas. Las acciones destructivas piden confirmación.
5. edge-tts genera la voz base y RVC la convierte a la voz de Miku.
6. El frontend la reproduce con lip sync, expresión y subtítulo.
7. Tras un rato sin uso, Miku se oculta y deja de renderizar. Más tarde se mata el worker de RVC y se libera Whisper, volviendo a 0 MB de VRAM.

Si TTS o RVC fallan, Miku responde con la voz base o solo con subtítulo; nunca se cuelga.

### Decisiones clave

- **Nada de `torch` en el proceso principal.** En Windows, inicializar CUDA deja 300–500 MB residentes que no se liberan. Por eso RVC corre en un subproceso aislado que se puede matar, y Whisper corre en CPU.
- **Herramientas en lista cerrada** ([docs/tools.md](docs/tools.md)), registradas con el decorador `@tool`. El LLM nunca ejecuta comandos de shell arbitrarios.
- **Sin frameworks de UI**: TypeScript + Vite en vanilla, para mantener baja la RAM de WebView2.
- **Atajo local** para comandos frecuentes (volumen, media, etc.): se ejecutan sin pasar por Gemini.

## Estructura

| Ruta | Contenido |
|---|---|
| [core/](core/) | Backend: `server.py` (WebSocket), `pipeline.py` (orquestación), `llm.py` (Gemini), `stt.py`, `tts.py`, `rvc.py` + `rvc_worker.py`, `wakeword.py`, `audio_in.py`, `resources.py` |
| [core/tools/](core/tools/) | Herramientas del PC: apps, archivos, media, notas, sistema, temporizadores, web |
| [core/infer_pack/](core/infer_pack/) | Modelos de RVC (VITS, RMVPE) |
| [app/src/](app/src/) | Frontend: `live2d.ts`, `animations.ts`, `clickthrough.ts`, `ui.ts`, `ws.ts`, `main.ts` |
| [app/src-tauri/](app/src-tauri/) | Shell de Tauri en Rust (ventana, bandeja, atajo global) |
| [docs/](docs/) | Arquitectura, roadmap, herramientas, persona y preparación |
| [scratch/](scratch/) | Scripts de prueba y diagnóstico |
| [config.yaml](config.yaml) | Toda la configuración ajustable |

## Requisitos

- Windows 10/11 con GPU NVIDIA (probado en RTX 3050 de 8 GB)
- Python 3.14 (la versión del venv actual), Node.js 20+, Rust (`rustup`) y Microsoft C++ Build Tools
- API key de Gemini (Google AI Studio)

Recursos que **no** están en el repo y hay que conseguir aparte (detalles en [docs/setup.md](docs/setup.md)):

- Modelo Live2D de Miku en `app/public/models/miku/`
- `live2dcubismcore.min.js` del Cubism SDK for Web en `app/public/lib/`
- Modelo RVC de Miku (`.pth` y `.index`) en `models/rvc/`
- (Opcional) wake word `hey_miku.onnx` en `models/wakeword/`

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

`install_autostart.bat` y `uninstall_autostart.bat` activan o quitan el arranque con Windows.

## Documentación

- [docs/architecture.md](docs/architecture.md): arquitectura, protocolo WebSocket y presupuesto de recursos
- [docs/roadmap.md](docs/roadmap.md): fases del proyecto
- [docs/tools.md](docs/tools.md): herramientas disponibles
- [docs/persona.md](docs/persona.md): personalidad, emociones y frases fijas
- [CHANGELOG.md](CHANGELOG.md): historial de cambios
- [docs/auditoria/plan.md](docs/auditoria/plan.md): plan de auditoría total y sus [hallazgos](docs/auditoria/hallazgos/)
