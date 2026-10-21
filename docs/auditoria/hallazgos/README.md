# Hallazgos de la auditoría

Aquí se apunta lo que se va encontrando al seguir el [plan de auditoría](../plan.md).

- **Commit auditado:** `01f50c8`
- **Inicio:** 2026-10-20
- **Estado:** auditoría cerrada y corregida el 2026-10-21: 55 arreglados, 2 decididos (H-002: sin confirmación; H-028: carga al arrancar), 1 parcial, 1 descartado (ver "Arreglos" en [99-resumen.md](99-resumen.md)).

## Archivos

Un archivo por fase, creado al empezarla:

| Archivo | Fase |tyt
|---|---|
| `00-linea-base.md` | 0. Mediciones y análisis automáticos |
| `01-herramientas.md` | 1. `core/tools/` |
| `02-red.md` | 2. `server.py`, `ws.ts` |
| `03-llm.md` | 3. `llm.py` |
| `04-orquestacion.md` | 4. Arranque, pipeline, recursos, config |
| `05-audio-entrada.md` | 5. Micrófono, STT, wake word |
| `06-voz-gpu.md` | 6. TTS, RVC, worker |
| `07-infer-pack.md` | 7. Modelos RVC de terceros |
| `08-frontend.md` | 8. `app/src/` |
| `09-tauri.md` | 9. Shell de Tauri |
| `10-config-scripts.md` | 10. Dependencias y `.bat` |
| `11-scratch.md` | 11. Scripts de prueba |
| `12-docs.md` | 12. Docs frente a código |
| `99-resumen.md` | 13. Cierre |

## Formato de cada hallazgo

Los IDs son correlativos en toda la auditoría (`H-001`, `H-002`, …), sin importar la fase.

```markdown
### H-001 · <título corto>

- **Severidad:** Crítica | Alta | Media | Baja
- **Estado:** por-verificar | confirmado | descartado | arreglado
- **Ubicación:** `core/tools/web.py:42`
- **Categoría:** seguridad | error | recursos | mantenibilidad | docs

**Qué pasa:** una o dos frases.

**Cómo se reproduce:** entrada o pasos → resultado observado.

**Evidencia:** fragmento de código, salida de un comando o medición.

**Propuesta:** el arreglo mínimo, sin aplicarlo todavía.
```

Al principio de cada archivo de fase va una línea de avance, por ejemplo:

```markdown
Avance: `apps.py` revisado 387/387 · `files.py` revisado 60/138
```

## Índice

Se completa a medida que aparecen hallazgos, ordenado por severidad.

| ID | Severidad | Estado | Ubicación | Título |
|---|---|---|---|---|
| H-019 | Crítica | arreglado | `core/server.py:203` | Cualquier página web puede controlar a Miku y el PC |
| H-006 | Crítica | arreglado | `core/tools/apps.py:260` | `open_app` ejecuta cualquier línea de comandos del LLM |
| H-001 | Alta | arreglado | `core/tools/__init__.py:21` | La confirmación de acciones destructivas no está implementada en código |
| H-007 | Alta | arreglado | `core/tools/apps.py:367` | `type_text` + alias de consola permiten ejecutar comandos |
| H-008 | Alta | arreglado | `core/tools/apps.py:290` | `close_app` mata procesos por subcadena y con `kill()` |
| H-023 | Alta | arreglado | `core/llm.py:249` | El atajo local cierra procesos con "apaga la luz" o "apaga el PC" |
| H-020 | Media | arreglado | `core/server.py:50` | `broadcast` falla si cambian los clientes mientras envía |
| H-002 | Media | decidido | `core/tools/apps.py:271` | `close_app` cierra apps sin confirmación |
| H-003 | Media | arreglado | `core/tools/__init__.py:33` | El timeout de 5 s por herramienta no existe |
| H-011 | Media | arreglado | `core/tools/files.py:97` | `open_file` ejecuta programas y scripts de Descargas |
| H-013 | Media | arreglado | `core/tools/media.py:86` | `media_control` y `mute` hacen lo contrario de lo pedido |
| H-015 | Media | arreglado | `core/tools/system.py:80` | `shutdown_pc` pregunta por una acción y ejecuta otra |
| H-024 | Media | arreglado | `core/llm.py:227` | El atajo local secuestra peticiones y siempre dice que funcionó |
| H-025 | Media | arreglado | `core/llm.py:337` | El atajo local bloquea el bucle de eventos |
| H-026 | Media | arreglado | `core/llm.py:384` | Las llamadas a Gemini no tienen tiempo máximo |
| H-028 | Media | decidido | `core/__main__.py:125` | Whisper y RVC se cargan al arrancar el PC |
| H-030 | Media | arreglado | `core/pipeline.py:280` | Un error al procesar texto deja la wake word en pausa |
| H-034 | Media | arreglado | `core/audio_in.py:100` | VAD por energía: con ruido graba hasta el máximo |
| H-035 | Media | arreglado | `core/stt.py:92` | El prompt de Whisper puede hacer oír comandos en el ruido |
| H-038 | Media | arreglado | `core/rvc.py:99` | Tras un timeout de RVC, Miku dice la frase anterior |
| H-045 | Media | arreglado | `app/src/live2d.ts:551` | Interrumpir a Miku deja un intervalo de 60 ms para siempre |
| H-047 | Media | arreglado | `app/src/clickthrough.ts:22` | El click-through deja de detectar el ratón al activarse |
| H-049 | Media | arreglado | `app/src-tauri/capabilities/default.json:17` | El atajo global no tiene permiso para registrarse |
| H-050 | Media | arreglado | `app/src-tauri/src/lib.rs:54` | "Salir" deja el backend escuchando el micrófono |
| H-052 | Media | arreglado | `core/requirements.txt` | `requirements.txt` incompleto y sin versiones fijadas |
| H-053 | Media | arreglado | `stop.bat:13` | `stop.bat` puede matarse a sí mismo y mata procesos ajenos |
| H-055 | Media | arreglado | `scratch/test_suite.py` | No hay tests automatizados de lo que más riesgo tiene |
| H-004 | Baja | arreglado | `core/tools/__init__.py:29` | `print` sueltos y argumentos completos en logs |
| H-005 | Baja | arreglado | `core/tools/__init__.py:49` | Nombre de herramienta repetido se sobrescribe |
| H-009 | Baja | arreglado | `core/tools/apps.py:38` | Alias de apps fijos; `config.yaml → apps` se ignora |
| H-010 | Baja | arreglado | `core/tools/apps.py:104` | Fugas de handles y llamadas bloqueantes |
| H-012 | Baja | arreglado | `core/tools/files.py:136` | Errores menores en `files.py` |
| H-014 | Baja | arreglado | `core/tools/media.py:112` | Volumen dice "ok" aunque no cambie nada |
| H-017 | Baja | arreglado | `core/tools/timers.py:92` | Carrera, mensajes y persistencia de temporizadores |
| H-018 | Baja | arreglado | `core/tools/web.py:15` | Código duplicado y descripciones que no cuadran |
| H-021 | Baja | arreglado | `core/server.py:13` | Detalles de `server.py` |
| H-022 | Baja | arreglado | `app/src/ws.ts:58` | El cliente reenvía mensajes viejos al reconectar |
| H-027 | Baja | arreglado | `core/llm.py:408` | Detalles de `llm.py` |
| H-029 | Baja | arreglado | `core/__main__.py:30` | Detalles de `__main__.py` |
| H-031 | Baja | arreglado | `core/pipeline.py:118` | Avisos de temporizador se pisan con la conversación |
| H-032 | Baja | arreglado | `core/pipeline.py:231` | Detalles de `pipeline.py` |
| H-033 | Baja | arreglado | `core/config.py:129` | `config.py` no valida y repite valores por defecto |
| H-036 | Baja | arreglado | `core/stt.py:88` | Detalles de `stt.py` |
| H-037 | Baja | arreglado | `core/wakeword.py:80` | Detalles de `wakeword.py` |
| H-039 | Baja | parcial | `core/rvc.py:74` | Detalles de `rvc.py` |
| H-040 | Baja | arreglado | `core/tts.py:35` | Caché de voz sin límite; frases fijas sin precargar |
| H-041 | Baja | arreglado | `core/rvc_worker.py:90` | Detalles de `rvc_worker.py` |
| H-042 | Baja | arreglado | `core/rmvpe.py:1` | `rmvpe.py` es una copia de RVC con restos de depuración |
| H-043 | Baja | arreglado | `core/infer_pack/` | Falta la licencia MIT de RVC; media `models.py` sin uso |
| H-044 | Baja | arreglado | `app/src/main.ts:184` | Mostrar a Miku quita el foco y pierde órdenes en animaciones |
| H-046 | Baja | arreglado | `app/src/live2d.ts:170` | Detalles de `live2d.ts` |
| H-048 | Baja | arreglado | `app/index.html:15` | Detalles de `index.html`, CSS, click-through y muestras |
| H-051 | Baja | arreglado | `app/src-tauri/tauri.conf.json:25` | Configuración de seguridad de Tauri más abierta de lo necesario |
| H-054 | Baja | arreglado | `start.bat:15` | Detalles de `start.bat`, Vite y arranque automático |
| H-056 | Baja | arreglado | `scratch/test_all_26_tools.py:49` | Detalles de `scratch/` y modelos de wake word |
| H-057 | Baja | arreglado | `docs/tools.md` | `tools.md` no coincide con las herramientas registradas |
| H-058 | Baja | arreglado | `docs/persona.md` | `persona.md` y `architecture.md` describen otro comportamiento |
| H-059 | Baja | arreglado | `docs/setup.md` | `setup.md` y `README.md` no bastan para instalar desde cero |
| H-016 | — | descartado | `core/tools/timers.py:30` | Un temporizador puede no sonar nunca (el bucle sí se configura) |
