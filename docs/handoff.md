# Handoff: retomar en una conversación nueva (3-nov)

## El proyecto en 4 líneas

Miku es una asistente de voz para Windows. El backend en Python asyncio ([core/](../core/)) oye la palabra clave (openWakeWord), transcribe con faster-whisper en CPU, pide la respuesta a Gemini (bucle de agente con herramientas del PC, [core/tools/](../core/tools/)) y habla con edge-tts + RVC (subproceso de GPU, [core/rvc_worker.py](../core/rvc_worker.py)). El frontend es Tauri v2 + TypeScript con Live2D ([app/src/](../app/src/)). Una extensión de Opera maneja las pestañas. Todo habla por WebSocket en `ws://127.0.0.1:8765`. Lo usa una sola persona en su PC.

Para empezar, lee el [README.md](../README.md) y [docs/architecture.md](architecture.md). Hay un grafo en `graphify-out/` (`graphify query|path|explain`).

## Preferencias del usuario (siempre)

- Responder en **español**, con lenguaje sencillo.
- **No robar el foco**: suele estar jugando. No abrir ventanas ni reiniciar Miku sin que lo pida.
- **No instalar nada**: ni paquetes, ni pip, ni npm nuevos.
- **No borrar los logs** (`cache/core.log`, `cache/rvc_worker.log`): se trabaja con ellos.
- **Push solo cuando lo pida.** Los commits van en `develop`.
- **Una sola voz (RVC).** Si RVC falla, Miku responde solo con subtítulo, nunca con la voz base.
- Ahorrar cuota gratuita de Gemini. La RAM no importa; la VRAM sí.
- Para reiniciar Miku en segundo plano, usar WMI `Win32_Process Create`: un proceso lanzado desde una herramienta muere con la llamada.

## Estado actual

- Rama `develop`, **42 commits por delante de `origin/develop`, sin push**. Árbol limpio, salvo este archivo, que no está en ningún commit.
- Los 19 módulos de test pasan. TypeScript compila (`cd app && npx tsc --noEmit`).
- **No se probó nada en vivo.** Para que los cambios valgan hay que reiniciar el backend (`stop.bat` + `start.bat`). El cambio de la bandeja (`app/src/main.ts`) necesita además `npm run tauri build`.

### Últimos commits (esta sesión)

| Commit | Qué |
|---|---|
| `e2d8ec6` | "Déjalo ahí", "Mejor déjalo" y "Déjalo ahí nomás" son despedidas ("Déjalo para mañana" no) |
| `1d87139` | Arreglos de la auditoría del 2-nov (ver abajo) |
| `14af85c` | Se oculta cuando ella misma se despide, y ante más señales de que el usuario terminó |
| `745914e` | `core/intent.py`: un solo módulo decide qué es cada frase oída |

### Qué arregló la auditoría del 2-nov (`1d87139`)

1. **Despedidas en preguntas:** una palabra de despedida dentro de una pregunta u orden ya no despide a Miku ("¿Cómo se dice adiós en japonés?", "vete a YouTube"). Una frase de despedida cuenta solo si lo demás es relleno (`_KEYWORD_FILLER` en [core/intent.py](../core/intent.py)).
2. **Modelo de reserva pegado:** la cadena de modelos se prueba siempre en el orden de `config.yaml`. Antes, un solo 504 dejaba toda la sesión en el modelo de reserva. Si Gemma falla, el siguiente modelo sigue recibiendo el audio.
3. **Ocultar desde la bandeja:** ahora envía `dismiss`, y `end_conversation()` corta el turno. Antes el watchdog abría el micrófono con ella oculta.
4. **Despedida sin `speak_done`:** el watchdog la oculta. Ojo: pone `_speak_watchdog_task = None` antes de llamar a `handle_speak_done()`; si no, se cancela a sí mismo y el `hide` no sale.
5. **Atajo local:** la hora y las notas solo responden a la frase completa ("¿A qué hora cierra el súper?" va a Gemini).
6. **"Me voy" en su respuesta:** solo la oculta al final de la frase o en "me voy a dormir/descansar".
7. **Herramienta destructiva con argumentos malos:** devuelve un error y no deja nada pendiente de confirmar ([core/tools/\_\_init\_\_.py](../core/tools/__init__.py)).
8. **Código muerto:** borrada la ruta de respuesta del servidor sin pipeline. `MikuServer(host, port)` ya no recibe `brain` ni `tts`; el pipeline se pone con `set_pipeline` antes de `start()`. También se borró otro código que nadie usaba y se corrigieron los docstrings de "una voz".

## Cómo se trabaja aquí

- **Tests:** `core\.venv\Scripts\python.exe -m tests.<módulo>`, que imprime `ok`. Para pasar todos:
  `for f in tests/test_*.py; do core/.venv/Scripts/python.exe -m tests.$(basename $f .py) 2>&1 | tail -1; done`
- **Frase mal entendida en un log:** se corrige en [core/intent.py](../core/intent.py) y se añade una línea a la tabla de [tests/test_intent.py](../tests/test_intent.py) con la frase real y lo que debía ser.
- **Logs:** en `cache/core.log`, con las peticiones como `--> [GEMINI REQ #n] Model: ...` y los avisos del watchdog.
- **CHANGELOG.md:** cada arreglo lleva una línea en `[Unreleased]`, en español.
- **Commits:** en inglés, con el estilo `fix:` / `feat:`, cuerpo explicando el caso del log y la línea `Co-Authored-By`.

### Trampas conocidas

- No hacer grep recursivo sobre `core/`: entra en `core/.venv` y se cuelga. Usar el Grep acotado o excluir `.venv`.
- Los scripts de prueba van en `$TEMP` y se lanzan con `PYTHONPATH=.`. La consola estropea las tildes: imprimir con `.encode("ascii", "replace")`.
- En las ediciones con heredoc no meter regex con `\b` o `\s`: usar Edit y buscar el byte 0x08 después.

## Pendiente / ideas para seguir

- **Probar en vivo** lo de esta sesión: reiniciar el backend, compilar el frontend y probar estas frases: "¿cómo se dice adiós en japonés?", "déjalo ahí", ocultar desde la bandeja mientras habla, "¿a qué hora cierra el súper?".
- **Push** de `develop` cuando el usuario lo pida.
- **Partes que la auditoría no revisó:**
  - `rvc_worker.py`, `infer_pack/` y `rmvpe.py`.
  - Por dentro: `audio_in.py`, `stt.py`, `state.py` y `screen.py`.
  - En el frontend: `motion.ts`, `behavior.ts` y `animations.ts`.
  - Rust y los `.bat`.
- **Duda sin comprobar:** si un recordatorio largo se retrasa cuando el PC se suspende (reloj de asyncio en Windows).
- **Fase E** de [docs/plan-siguiente.md](plan-siguiente.md): prueba en vivo de la herramienta `windows` (minimizar, mover y colocar con la escala real de la pantalla).
- **Plan de expresiones:** [docs/plan-expresiones.md](plan-expresiones.md), fases 1-6 hechas.
- **Siguiente ronda de logs:** revisar `cache/core.log` en busca de frases mal clasificadas, órdenes perdidas y modelos de reserva.
