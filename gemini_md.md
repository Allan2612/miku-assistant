# GEMINI.md — Instrucciones para el agente

Eres el desarrollador de **Miku Assistant**: una asistente de escritorio 2D (Live2D) con voz de Miku que aparece/desaparece con animación, entiende peticiones por voz y controla el PC. Es un proyecto **personal**, solo para Windows, en la PC del usuario.

## Antes de escribir código
1. Lee TODOS los archivos de `docs/`: `ARCHITECTURE.md`, `ROADMAP.md`, `TOOLS.md`, `PERSONA.md`, `SETUP.md`.
2. Mira en `ROADMAP.md` qué fase toca (la primera con casillas sin marcar).
3. Trabaja **solo en esa fase**.

## Reglas de trabajo
- Habla con el usuario en **español**. Código, nombres de variables y commits en inglés.
- **Una fase a la vez.** Al terminar una fase: explica cómo probarla (comandos exactos), marca las casillas en `ROADMAP.md`, añade una entrada a `CHANGELOG.md` y **espera a que el usuario confirme** que funciona antes de seguir.
- Si algo del diseño no funciona en la práctica (versión de librería incompatible, API cambiada), **dilo, propone una alternativa y espera confirmación**. No improvises cambios grandes de arquitectura.
- Antes de usar una librería, verifica en su documentación/README actual la versión y la API. No inventes funciones.
- Si un error persiste tras 2 intentos de arreglo, para y muéstrale al usuario el error completo y tus hipótesis.

## Reglas de recursos (prioridad máxima)
El objetivo es **consumo casi nulo en reposo y respuesta rápida (< 3 s) al activarse**. Respeta estrictamente el presupuesto de `ARCHITECTURE.md` → "Presupuesto de recursos".
- Nada de frameworks de UI (sin React/Vue/Svelte). TypeScript + Vite vanilla.
- No añadas dependencias nuevas sin justificarlo y pedir permiso. Prefiere la librería estándar.
- **Prohibido importar `torch` en el proceso principal de `core`**: En Windows, inicializar CUDA deja ~300–500 MB de memoria residente que `empty_cache()` no libera. Por eso, `faster-whisper` corre en CPU (`int8`, 4 hilos) y RVC debe ejecutarse en un **subproceso hijo aislado (`rvc_worker.py`)** que se mata (`terminate`/`kill`) tras `unload_after_minutes` de inactividad.
- **Pre-calentamiento (`warmup`)**: Para que descargar modelos no penalice la latencia, dispara la carga de `stt` y del subproceso `rvc_worker` de forma asíncrona en el instante en que el usuario activa a Miku (mientras habla).
- **Cierre de micrófono**: Cuando `wakeword.enabled` es `false`, el stream de `sounddevice` solo se abre al activar a Miku y se cierra inmediatamente al terminar de grabar la frase.
- **Con Miku oculta**: renderizado completamente detenido (`app.ticker.stop()`, ventana oculta) y el `setInterval` de click-through pausado. Sin bucles activos salvo la escucha de activación.
- Sin polling agresivo: nada por debajo de 100 ms salvo audio.

## Reglas de seguridad
- Las herramientas de control del PC son una **lista cerrada** (`docs/TOOLS.md`). **Nunca** implementes ejecución arbitraria de comandos de shell generados por el LLM.
- Acciones destructivas o irreversibles (cerrar apps, apagar, borrar) **piden confirmación por voz/texto** antes de ejecutarse.
- La API key va en `.env`, nunca en el código ni en commits.

## Archivos que NUNCA se suben a git
Añádelos a `.gitignore` desde la Fase 0:
```
.env
models/
cache/
app/public/models/
app/public/lib/live2dcubismcore*.js
core/.venv/
*.pth
*.index
*.onnx
__pycache__/
node_modules/
app/src-tauri/target/
```

## Estilo de código
- Archivos pequeños y con una responsabilidad (ver estructura en `ARCHITECTURE.md`).
- Python 3.11, tipado con type hints, `asyncio` en el backend.
- Logs claros con nivel configurable; nada de prints sueltos.
- Toda opción ajustable va en `config.yaml`, no hardcodeada.