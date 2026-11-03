# Handoff: retomar en una conversación nueva (3-nov, noche)

## El proyecto en 4 líneas

Miku es una asistente de voz para Windows. El backend en Python asyncio ([core/](../core/)) oye la palabra clave (openWakeWord), transcribe con faster-whisper en CPU, pide la respuesta a Gemini (bucle de agente con herramientas del PC, [core/tools/](../core/tools/)) y habla con edge-tts + RVC (subproceso de GPU, [core/rvc_worker.py](../core/rvc_worker.py)). El frontend es Tauri v2 + TypeScript con Live2D ([app/src/](../app/src/)). Una extensión de Opera maneja las pestañas. Todo habla por WebSocket en `ws://127.0.0.1:8765`. Lo usa el usuario en su PC y, con el instalador, algunos amigos.

Para empezar, lee el [README.md](../README.md) y [docs/architecture.md](architecture.md). Hay un grafo en `graphify-out/` (`graphify query|path|explain`).

## Preferencias del usuario (siempre)

- Responder en **español**, con lenguaje sencillo.
- **No robar el foco**: suele estar jugando. No abrir ventanas ni reiniciar Miku sin que lo pida.
- **No instalar nada**: ni paquetes, ni pip, ni npm nuevos.
- **No borrar los logs** (`cache/core.log`, `cache/rvc_worker.log`): se trabaja con ellos.
- **Push solo cuando lo pida.** Los commits van en `develop`.
- **Miku apagada por defecto:** encenderla solo para probar algo y apagarla después.
- **Una sola voz (RVC).** Si RVC falla, Miku responde solo con subtítulo, nunca con la voz base.
- Ahorrar cuota gratuita de Gemini. La RAM no importa; la VRAM sí.
- Para reiniciar Miku en segundo plano, usar WMI `Win32_Process Create`: un proceso lanzado desde una herramienta muere con la llamada.

## Estado actual

- Rama `develop`, con push hecho el 3-nov. Los 26 módulos de test pasan; `npm run build` y `npx tauri build` compilan.
- Ahora Miku es una app con dos ventanas: `miku.exe`, hecha con Tauri. Una ventana es Miku en Live2D; la otra es un
  **panel de control**. El backend corre como proceso hijo de `miku.exe`.
- También hay un **instalador NSIS**: `app/src-tauri/target/release/bundle/nsis/`. En el primer arranque descarga
  Python y las librerías. Detalle en [docs/plan-panel-instalador.md](plan-panel-instalador.md), sección "Estado".
- Miku queda **apagada** salvo que haga falta para una prueba. Se enciende con `start.bat` o desde el panel.

### Lo último (3-nov)

- Panel y instalador: fases 1 a 5, y además:
  - una sola instancia;
  - arrancar con Windows;
  - atajo y micrófono desde el panel;
  - música en Inicio;
  - botón «Reentrenar» de «Hey Miku».
- Los recordatorios suenan aunque el PC se haya suspendido. Se miran con el reloj de pared cada 30 s
  ([core/tools/timers.py](../core/tools/timers.py)).
- El tiempo de espera de Gemini bajó a 8 s ([core/llm.py](../core/llm.py)). En los logs, la mediana era 1,9 s;
  46 peticiones fallidas esperaron 10 s.
- La palabra clave:
  - ignora los disparos en silencio (`MIN_CLIP_PEAK`);
  - guarda los casi disparos en `cache/wake/near`.
- Se dejó de grabar un clip de OBS que el usuario no pidió: la frase repetida en la charla.

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

- **Probar en el PC del usuario (lo hace él):**
  - instalar el `.exe` en otra PC;
  - en la app real: el panel completo (Live2D, encender y apagar, logs, reproductor de clips, "¿Qué oyó?", chat "Solo
    texto", cerrar = ocultar, Apagar/Encender en la bandeja, música, arranque con Windows, cambio de atajo y de
    micrófono).
- **Reentrenar «Hey Miku»:** el usuario marca 60 clips (20 suyos) en Palabra clave y pulsa «Reentrenar».
  - Se probó con marcas falsas en modo `--dry` (≈1 min 15 s).
  - Sin marcas reales todavía no hay resultado.
- **Partes que la auditoría no revisó:**
  - `rvc_worker.py`, `infer_pack/` y `rmvpe.py`;
  - `stt.py`, `state.py` y `screen.py`;
  - `motion.ts`, `behavior.ts` y `animations.ts`.
- **Fase E** de [docs/plan-siguiente.md](plan-siguiente.md): prueba en vivo de la herramienta `windows`.
- **Siguiente ronda de logs:** revisar `cache/core.log` en busca de frases mal clasificadas y órdenes perdidas.
