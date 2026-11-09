# Propuestas de la auditoría del 9-nov

Cada propuesta lleva el dato que la justifica. Los números salen de `cache/core.log` de la PC con NVIDIA: 154 turnos y
517 peticiones a Gemini, del 1 al 4 de noviembre.

## Dónde se va el tiempo de una respuesta

| Paso | Mediana | p90 |
|---|---|---|
| Transcripción (Whisper `small`, procesador) | 1,7 s | 2,6 s |
| Respuesta de Gemini | 2,3 s | 13 s |
| Voz (edge-tts + RVC) | 1,7 s | 2,8 s |
| **Total desde que el usuario calla** | **6,2 s** | **20,7 s** |

- **El p90 de Gemini:** 30 fallos `504 DEADLINE_EXCEEDED`, 24 de ellos en una sola media hora del día 2. Cada uno
  costaba los 10 s del límite; desde el 2-nov el modelo pasa a otro después de un 504. Los 17 errores `400` fueron un
  error ya corregido: el límite de 8 s.
- **Segundas peticiones:** 147 de 517 (28 %) son la petición que sigue a una herramienta.

## Rendimiento, de más a menos ganancia

1. **Gemini en streaming + voz por frases.** La voz por frases ya existe, pero espera la respuesta entera de Gemini.
   Con streaming, la primera frase empezaría a sonar mientras llega el resto. Gana alrededor de 1 s en respuestas
   largas; en las de una frase, poco.
2. **Whisper en la tarjeta gráfica (solo con NVIDIA).** En la RTX 3050 bajaría de 1,7 s a unos 0,3–0,5 s (estimado).
   - Costes: unos 0,5–1 GB de VRAM y las librerías CUDA de CTranslate2, que hay que instalar.
   - Al usuario le importa la VRAM: tendría que ser una opción.
3. **Una voz propia en un solo paso:** [plan-voz-propia.md](plan-voz-propia.md), pendiente de permiso.
4. **Menos segundas peticiones:** las herramientas de `FINAL_TOOLS` ya no piden una segunda; habría que revisar en el
   log qué herramientas siguen pidiéndola sin necesidad.

## Funciones que pide el log

- **«Activa el búfer» de OBS:** la herramienta `obs` no puede encender el búfer de repetición, así que el modelo
  intentó iniciar una grabación (3-nov). Añadir `buffer_start` / `buffer_stop`.
- **Cuota por voz:** a «¿cuántas peticiones más puedo hacer?» respondió «muchas» sin mirar nada (3-nov). Una
  herramienta pequeña puede leer `core/quota.py`.
- **«No» después de «¿necesitas algo más?»:** volvió a preguntar «¿qué necesitas?» (4-nov). Debería despedirse.
- **Mensajes escritos mientras piensa:** se descartan («Pipeline busy. Dropping…»). Desde el 5-nov solo se salvan los
  que llegan mientras el micrófono espera. Mejor una cola de un mensaje.

## «Hey Miku»

- **El modelo reentrenado puntúa alto con silencio:** 0,69 con ceros, y en el log clips casi mudos con hasta 0,99. Lo
  frena el filtro de silencio (`MIN_CLIP_PEAK`), no el modelo. En el próximo reentrenamiento hay que añadir silencio y
  ruido de la habitación como ejemplos negativos.
- **Si un micrófono graba bajo** (la laptop AMD aún no lo ha confirmado), ese filtro también podría bloquear llamadas
  reales.

## Arquitectura y mantenimiento

- **Módulos muy grandes:** `core/llm.py` (958 líneas), `core/pipeline.py` (852) y `app/src/panel/manage.ts` (962).
  Separar por función, no por tamaño:
  - en `llm.py`, la ruta rápida local (`_try_fast_path_tool`), que es casi todo reglas de texto: a `core/intent.py`;
  - en `pipeline.py`, la voz por frases (`_VoiceChain`, `_prepare_pieces`, `_play_next_piece`): a su propio módulo;
  - en `manage.ts`, cada página del panel en su archivo, como ya están `voice.ts`, `setup.ts` y `storage.ts`.
- **`core/infer_pack/`** es código copiado de RVC, con clases que Miku no usa (`SynthesizerTrnMs256NSFsid*`,
  `ConvFlow`…). Se deja tal cual: recortarlo complica actualizarlo desde el original.
- **`core/dns_warm.py`** resuelve 5 nombres cada 5 s en todas las PCs. La causa del problema (un adaptador de
  VirtualBox en la PC AMD) ya se quitó. Cuesta muy poco; si algún día molesta, podría limitarse a cuando Miku está
  activa.
- **`tests/test_agent.py`** falló una vez y pasó al repetirlo (`ProactorEventLoop … _ssock`, al cerrar el bucle de
  asyncio). Si se repite, conviene cerrar el bucle explícitamente en ese test.
- **Documentación vieja:** `docs/roadmap.md`, `plan-siguiente.md`, `plan-funciones.md`, `plan-expresiones.md`,
  `plan-panel-*.md` y `mejoras.md` son planes terminados. Se pueden mover a `docs/historial/` para que `docs/` muestre
  solo lo vigente.
