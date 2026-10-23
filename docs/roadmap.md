# Roadmap

Trabaja fase por fase. Cada fase termina con una prueba que hace el usuario. No avances sin su confirmación.

## Fase 0 — Esqueleto
- [x] Estructura de carpetas según `architecture.md`, `.gitignore`, `CHANGELOG.md`, `config.yaml`, `.env.example`
- [x] `core/` con venv, `requirements.txt` mínimo y `python -m core` que arranca y loguea la config
- [x] `app/` Tauri v2 + Vite + TS vanilla que abre una ventana con las flags de optimización de WebView2
- **Prueba:** ambos arrancan sin errores.

## Fase 1 — Miku en el escritorio (solo frontend)
- [x] Ventana transparente, sin bordes, siempre encima, fuera de la barra de tareas, anclada abajo a la derecha
- [x] Carga del modelo Live2D desde `config.yaml` con idle, parpadeo y mirada al cursor
- [x] Click-through con hit-test sobre el modelo (activo solo cuando es visible)
- [x] Animaciones de **aparecer** y **desaparecer** según `architecture.md`
- [x] Atajo global que alterna mostrar/ocultar; render y timers detenidos al ocultar
- [x] Icono en bandeja (Mostrar / Ocultar / Salir)
- **Prueba:** el atajo la hace aparecer y desaparecer con fluidez; oculta, el Administrador de tareas muestra 0 % GPU y < 250 MB de RAM en `app`.

## Fase 2 — Cerebro por texto
- [x] Servidor WS en `core/` y cliente con reconexión en `app/`
- [x] Caja de texto (aparece al hacer clic en Miku) → `text_input` *(retirada después en el modo "solo voz"; el backend aún acepta `text_input`)*
- [x] `llm.py` con Gemini, persona de `persona.md`, historial corto y parseo de `[emocion]`
- [x] Subtítulos tipo burbuja + cambio de expresión
- [x] Auto-ocultar tras `hide_after_seconds`
- **Prueba:** escribes "hola, ¿quién eres?" y Miku responde en burbuja con expresión.

## Fase 3 — Miku habla (voz base)
- [x] `tts.py` con edge-tts → wav → mensaje `speak`
- [x] Caché en disco (`cache/voice/`) para las frases fijas de `persona.md`
- [x] Reproducción con lip sync (`model.speak()`) y `speak_done`
- [x] Degradación: si falla TTS, solo subtítulo
- **Prueba:** responde con voz y la boca se mueve sincronizada.


## Fase 4 — Miku escucha
- [x] `audio_in.py`: grabación tras activación con silero-vad (fin por silencio o máximo), cerrando el stream del micrófono al terminar
- [x] `stt.py`: faster-whisper en CPU (`int8`, 4 hilos), español, con carga perezosa y descarga tras inactividad en `resources.py`
- [x] Indicador visual de "escuchando" y "pensando"
- **Prueba:** atajo → hablas → transcribe bien en < 0.8 s sin usar VRAM y responde con voz. Medir latencia total (objetivo < 3 s).

## Fase 5 — Control del PC
- [x] Registro de herramientas y declaraciones para Gemini según `tools.md`
- [x] Implementación de herramientas (apps, multimedia, volumen, web, sistema, archivos, notas y temporizadores)
- [x] Flujo de confirmación para acciones destructivas (protección obligatoria para apagar/reiniciar la PC)
- **Prueba:** "abre el bloc de notas", "cierra el bloc de notas", "pon el volumen al 50", "pausa la música", "apaga la PC" (pide confirmación).

## Fase 6 — Voz de Miku (RVC en subproceso aislado)
- [x] Modelo RVC v2 40kHz asignado: `models/rvc/miku_mellow.pth` e índice `models/rvc/miku_mellow.index` con pipeline DSP anti-artefactos (filtro de mediana en F0, protección de consonantes sordas, padding por reflexión y normalización sin clipping)
- [x] `rvc_worker.py` (proceso hijo que importa PyTorch/RVC y escucha peticiones por pipe/stdio) y `rvc.py` (gestor en el proceso principal)
- [x] Pre-calentamiento (`warmup`) al detectar el atajo de activación mientras el usuario habla
- [x] Terminación del subproceso (`kill`) en `resources.py` tras `unload_after_minutes` para garantizar 0 MB de VRAM en reposo
- [x] Pipeline edge-tts (voz base latina `es-MX-DaliaNeural`) → RVC; si falla, usa la voz base de edge-tts
- **Prueba:** suena a Miku con baja latencia; al pasar el tiempo de inactividad, `nvidia-smi` muestra que el proceso desapareció y la VRAM vuelve a 0 MB.


## Fase 7 — Palabra de activación (opcional)
- [x] `wakeword.py` con openWakeWord en CPU (modelo `.onnx` del usuario en `models/wakeword/hey_miku.onnx`, con fallback a modelos base para pruebas)
- [x] Activable desde `config.yaml` (`wakeword: { enabled: true/false, ... }`), garantizando cero uso de micrófono cuando está desactivado y pausa automática durante la interacción
- **Prueba:** activar `enabled: true` en `config.yaml`; decir la frase de activación despierta a Miku; consumo de CPU en reposo < 2 %.

## Fase 8 — Pulido
- [x] `start.bat` (backend con `pythonw` + app) y opción de arranque con Windows (`install_autostart.bat`, `stop.bat`, `uninstall_autostart.bat`)
- [x] Reacciones al clic/arrastre, saludo según la hora del día (mañana, tarde, noche)
- [x] Interrumpir a Miku si el usuario vuelve a pulsar el atajo o dice la frase mientras habla (barge-in)
- [x] Medir y documentar el consumo real frente al presupuesto
- **Prueba:** un día de uso normal sin cuelgues ni fugas de RAM/VRAM.

## Fase 9 — Extras (opcional)
- [x] `look_at_screen`: captura de pantalla enviada a Gemini (visión) para "¿qué ves en mi pantalla?" o "ayúdame con este error" (va en la misma petición que el audio; `core/screen.py`)
- [x] Recordatorios persistentes y notas (`cache/timers.json`)