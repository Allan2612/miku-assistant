# Fase 12 · Documentación frente a código

Avance: `architecture.md`, `tools.md`, `persona.md`, `roadmap.md`, `setup.md`, `README.md` comparados con el código · `CHANGELOG.md` revisado solo en sus afirmaciones verificables (número de herramientas, nombres de módulos) · **fase completa**

Las diferencias que ya tienen hallazgo propio no se repiten: confirmación (H-001), timeout de herramientas (H-003), alias de `config.yaml` (H-009), VAD silero (H-034), carga al arrancar (H-028), saludo diario (H-032), frases fijas en caché (H-040), caja de texto (fase 8), dependencias (H-052).

### H-057 · `tools.md` no coincide con las herramientas registradas

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `docs/tools.md`, `core/tools/`
- **Categoría:** docs

**Qué pasa:** comparando `tools.md` con `_TOOL_METADATA` (26 herramientas registradas):

- `list_open_apps` está documentada pero no existe.
- `open_notes` existe pero no está documentada.
- El decorador documentado es `@tool(name, description, params, destructive)`; el real no tiene `params`.
- "Máximo 5 llamadas a herramientas por petición"; el código usa 2 (`llm.py:137`).
- `type_text` dice usar `pyautogui.write` o `SendInput`; usa `keybd_event`. `close_app` dice `terminate()`; usa `kill()` (H-008).
- El flujo `confirm_request`/`confirm_response` está descrito como implementado; no existe ni en el backend ni en el frontend (H-001).
- `CHANGELOG.md` habla de "25 herramientas"; hay 26.

**Propuesta:** regenerar la tabla de `tools.md` a partir del registro (nombre, descripción, `destructive`) y marcar como "pendiente" lo que aún no existe.

### H-058 · `persona.md` y `architecture.md` describen un comportamiento distinto del real

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `docs/persona.md`, `docs/architecture.md:30-45`, `:120`, protocolo WebSocket
- **Categoría:** docs

**Qué pasa:**

- **Frases fijas:** el aviso de temporizador documentado es "¡Ding! Se acabó el temporizador de {label}." y el real "¡Tu temporizador de {label} ha terminado!" (`timers.py:61`). Las frases "Ups, no tengo conexión" y "¿Me lo repites?" no se usan: sin red, Miku elige al azar una de las respuestas de "sin batería" (`llm.py:60-65`); si no entiende el audio, vuelve a reposo en silencio (`pipeline.py:208-213`).
- **Expresiones:** `persona.md` dice que el mapeo emoción → expresión se configura en `config.yaml → live2d.expressions`, pero el frontend nunca lee ese mapeo: llama a `model.expression(<emoción>)` y, si falla, mueve parámetros fijos (`live2d.ts:308-349`).
- **Protocolo WebSocket:** la arquitectura lista `confirm_request` y `confirm_response`, que no existen, y no menciona `stop_speaking`, que sí se usa (`pipeline.py:155`, `main.ts:131`).
- **Whisper:** la arquitectura dice modelo `small` con 4 hilos; `config.yaml` usa `base` con 6.

**Propuesta:** actualizar ambos documentos al comportamiento real, o abrir tareas en el roadmap para lo que se quiera implementar (frases de error, mapeo de expresiones, confirmación).

### H-059 · `setup.md` y el `README.md` no bastan para instalar el proyecto desde cero

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `docs/setup.md`, `README.md` (sección "Puesta en marcha"), `GEMINI.md`
- **Categoría:** docs

**Qué pasa:**

- Todos los documentos piden **Python 3.11** (y el `README.md` usa `py -3.11 -m venv`), pero el venv real es **Python 3.14.7**. No se sabe si el proyecto funciona en 3.11.
- No se menciona `models/rvc/rmvpe.pt`, que el worker exige (`rvc_worker.py:83`, `:101-104`); sin él, RVC falla en silencio y Miku usa la voz base.
- No se avisa de que ContentVec (`lengyue233/content-vec-best`) y el modelo de Whisper se descargan de Hugging Face en el primer uso (H-036, H-041).
- No se explica cómo instalar `torch` con CUDA (H-052).

**Propuesta:** fijar la versión de Python real en los documentos, añadir `rmvpe.pt` a la lista de recursos de `setup.md`, y un paso de "descarga de modelos" que traiga ContentVec y Whisper durante la instalación.

### Resumen de la fase 12

3 hallazgos de documentación, todos bajos. La documentación describe el diseño previsto, no el estado actual: tras arreglar los hallazgos de las fases 1-10 conviene una pasada para alinearla.
