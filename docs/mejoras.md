# Plan de mejoras — "se siente tontita"

Diagnóstico y plan para subir la inteligencia, la velocidad y el alcance de Miku.
Fuente: síntomas reportados por el usuario + `config.yaml`, `core/llm.py` y la auditoría del 21-oct.

## El problema de fondo

"Se siente tontita" no es un fallo único: son **varias capas mediocres a la vez que se suman**.
La cadena es `micrófono → STT (te oye) → LLM (piensa) → tools (actúa) → RVC (habla)`.
Hoy casi cada eslabón está en su versión floja, y el resultado se multiplica.

**Empezar de cero no arregla esto.** "Pocas herramientas", "me oye mal" y "RVC lento" son
trabajo que hay que hacer en cualquier base; no son defectos de la arquitectura, que sigue siendo buena.

## Síntomas → causa → arreglo

| Síntoma | Causa real | Arreglo | Esfuerzo |
|---|---|---|---|
| No me entiende | Whisper `small` CPU: ~1 de cada 4 palabras mal con ruido (comentario en `config.yaml`) | Audio directo a Gemini (multimodal), o Whisper en GPU | Medio |
| Interpreta/hace mal | Modelo **lite** (el más tonto) + `temperature 0.8` + `fast-path` de regex que adivina antes que Gemini | Modelo→`flash`, temp→0.35, recortar fast-path | Bajo |
| Respuestas lentas | **RVC 6–20 s/frase** en la 3050 (auditoría) + STT CPU ~1.3 s + varias idas/vueltas a Gemini por tool | Audio→Gemini (quita un paso), cachear voz, voz base cuando urge | Medio-alto |
| Pocas tools / limitada | 26 tools superficiales + tope de **2 llamadas** por petición (`llm.py:141`) | Subir tope a 4 + tools reales (mensajería, archivos, web, memoria) | Alto (trabajo real) |
| No me hace caso al llamarla | Wake word `hey_miku.onnx` propio + `threshold 0.50` pierde activaciones | Bajar threshold o reentrenar; mientras, `Ctrl+Alt+M` | Bajo / Medio |

## Bug a confirmar — descartado (23-oct)

Sospecha: `gemini-3.5-flash-lite` y `gemini-3.6/3.7-flash` no eran IDs válidos. **Falso**: la API key
los lista todos. Lo real: `3.7-flash`, `3.8-flash` y `flash-latest` existen pero con esta key dan
504 o tardan 130–160 s, así que no sirven ni de fallback. `3.5-flash` ~2,5 s (algún 503 por demanda),
`3.5-flash-lite` ~1,1 s.

---

## Fase 1 — Victorias baratas (one-liners)

Objetivo: que se sienta menos tonta hoy, sin tocar arquitectura. Todo reversible.

- [x] **Paso 0 — listar modelos reales.** Hecho; ver "Bug a confirmar".
- [x] ~~**Modelo** `lite` → `gemini-3.5-flash`~~ **Revertido el mismo día**: en el plan gratuito
      `3.5-flash` solo da **20 peticiones/día** (Google lo cuenta como `3.6-flash`). Principal vuelve a
      `gemini-3.5-flash-lite` con `thinking_level=MINIMAL`; en pruebas eligió las mismas tools que flash.
      Flash queda de fallback. Una cuota diaria agotada pone el modelo 1 h en cooldown.
- [x] **Temperatura** `0.8` → `0.35` en `config.yaml` (si la quieres más viva, 0.5).
- [x] **Tope de tools** `maximum_remote_calls` `2` → `4` en `core/llm.py`.
- [x] **Wake word**: `threshold` `0.50` → `0.35` en `config.yaml`. Falta medir falsos positivos.

**Prueba:** pedir una tarea de dos pasos ("abre el bloc de notas y pon el volumen al 30"); debe
entender mejor, hacer ambas y responder más coherente. Llamarla 10 veces por voz y contar cuántas responde.

---

## Fase 2 — El gran salto: audio directo a Gemini

Objetivo: arreglar "no me entiende" **y** bajar latencia a la vez. Mata tres pájaros.

En vez de `mic → Whisper (CPU) → texto → Gemini`, enviar el audio grabado como parte multimodal
a Gemini, que transcribe + entiende + llama tools en una sola vuelta.

**Regla del usuario (23-oct): como máximo UNA petición a Gemini por turno.** Plan gratuito:
`3.5-flash` da 20 peticiones/día.

Hecho así (`core/llm.py`, `core/pipeline.py`):

1. Whisper local (0 peticiones) transcribe. Texto vacío o solo el "¿Sí?" de Miku → se descarta.
   Esto además filtra ruido/silencio, en el que Gemini "oía" palabras inventadas.
2. Fast-path con el texto de Whisper (0 peticiones).
3. "Sí" a una confirmación pendiente (apagar/reiniciar) → la acción aprobada se ejecuta en local (0).
4. Resto: **una** petición con el **audio**. Gemini devuelve `{lo que oyó} [emoción] frase` + las
   tools. AFC desactivado: las tools corren en local y su resultado no vuelve a Gemini. Se lee el
   resultado de la tool en vez de la frase del modelo cuando falla, pide confirmación o devuelve
   datos (`find_file`, `read_notes`, `get_datetime`, `get_system_status`, `list_timers`).
5. Subtítulo e historial usan `{lo que oyó}`. Un modelo que falla (429/503) pasa al siguiente: eso
   no da respuesta ni gasta cuota.

Descartado: Gemini como transcriptor aparte (probado el mismo día; ~1,2 s y casi exacto, pero +1
petición por frase). Medido con ruido fuerte: Whisper `small` ~1,6 s con fallos tipo "blog de
notas", "alabador"; flash-lite casi exacto. Test: `tests/test_one_request.py`.

- [x] Probado por el usuario el 23-oct. Fallo encontrado: dijo "¡Anotado!" sin llamar a `take_note`.
      Arreglado así: "apunta que X" va por el fast-path; el prompt ya no invita a decir "como si ya estuviera
      hecho"; y si el modelo afirma una acción sin tool, Miku lo admite (`CLAIMED_ACTION_RE`).

**Beneficios:** Gemini oye el audio real en vez del texto de Whisper, sin petición extra; las
acciones de varias tools bajan de 2–3 peticiones a 1. **Coste:** la frase de Miku se escribe antes de
ejecutar la tool (si falla, se lee el error de la tool); Whisper sigue corriendo (~1,5 s) como filtro.

**Prueba:** hablarle con música de fondo; el subtítulo "user" debe salir correcto y la respuesta llegar antes.

---

## Fase 3 — Que haga más cosas (trabajo real)

Objetivo: quitar el "está muy limitada". Esto es construir, no tunear. Enlaza con el plan de las
9 piezas (ver conversación / video de referencia).

Hecha el 23-oct bajo la regla de **una petición por turno** (ver Fase 2):

- [x] ~~Recortar el fast-path~~ **Se queda**: cada comando que resuelve cuesta 0 peticiones, y el
      usuario lo prefiere. Solo arreglos: "ópera" con tilde ya entra, y rutinas por voz.
- [x] **Memoria**: tools `remember` / `forget` (`core/tools/memory.py`), que Gemini pide en la misma
      respuesta. Hechos en `cache/memory.json` (máx 50, escritura atómica), inyectados al prompt.
      JSON en vez de SQLite: una lista corta no necesita más. **Sin** resumen de conversaciones:
      resumir exige otra petición.
- [x] **Más herramientas** (34 en total): `window_action` (minimizar/maximizar/restaurar),
      `copy_to_clipboard` / `read_clipboard`, `create_text_file` (solo Escritorio, nunca sobrescribe),
      `read_text_file` (.txt/.md/.csv/.log, primeros 600 caracteres). Las de lectura se leen tal cual.
- [x] **Leer páginas web / preguntas de actualidad**: `google_search` + `url_context` en la misma petición
      (`include_server_side_tool_invocations`, modo `VALIDATED`). **Sin probar con la API.** Si Gemini lo
      rechaza (400), se desactiva para la sesión y se reintenta sin él (un 400 no gasta cuota).
      `llm.web_search: false` lo apaga. La búsqueda se cobra por consulta en el plan de pago.
- [ ] ~~Canal Telegram~~ — saltado por decisión del usuario.
- [x] **Rutinas**: `routines:` en `config.yaml` + tool `run_routine`. "modo trabajo" / "activa el
      modo música" van por el fast-path: **0 peticiones**. Las tools destructivas se saltan.
      Tests: `tests/test_phase3_tools.py`.

**Prueba:** usarla un día real y comprobar que cubre más tareas sin "no puedo hacer eso".

---

## La latencia de RVC (hueso duro, sin fase)

**Actualizado 23-oct:** los logs de esta semana dan **0,5–1 s** por frase (4–11x tiempo real) con
el worker caliente; ya no es el cuello de botella. Lo lento es la carga en frío (~12 s al arrancar o
tras 10 min sin uso), durante la cual se usa la voz base. Texto original: convertir a la voz de Miku
costaba 6–20 s en la 3050 compartida. Mitigaciones (no soluciones): pre-warm (ya está), cachear más frases
fijas en `cache/voice/`, usar la voz base de edge-tts cuando la rapidez importe más que el timbre,
y mantener las respuestas cortas. Si algún día hay GPU con más VRAM, evaluar GPT-SoVITS (TTS+voz
en un paso, pero ~6 GB residentes).

## Orden recomendado

1. Fase 1 (una tarde, gran mejora percibida).
2. Fase 2 (el salto de "me entiende" y velocidad).
3. Fase 3 (alcance, en incrementos).

Cada fase termina con la prueba del usuario antes de seguir, igual que en `roadmap.md`.
