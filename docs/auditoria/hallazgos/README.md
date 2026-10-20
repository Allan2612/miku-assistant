# Hallazgos de la auditoría

Aquí se apunta lo que se va encontrando al seguir el [plan de auditoría](../plan.md).

- **Commit auditado:** `01f50c8`
- **Inicio:** 2026-10-20
- **Estado:** fases 1-3 completas, fase 4 en curso (fase 0 pendiente: mediciones y análisis automáticos)

## Archivos

Un archivo por fase, creado al empezarla:

| Archivo | Fase |
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
| H-019 | Crítica | confirmado | `core/server.py:203` | Cualquier página web puede controlar a Miku y el PC |
| H-006 | Crítica | confirmado | `core/tools/apps.py:260` | `open_app` ejecuta cualquier línea de comandos del LLM |
| H-001 | Alta | confirmado | `core/tools/__init__.py:21` | La confirmación de acciones destructivas no está implementada en código |
| H-007 | Alta | por-verificar | `core/tools/apps.py:367` | `type_text` + alias de consola permiten ejecutar comandos |
| H-008 | Alta | confirmado | `core/tools/apps.py:290` | `close_app` mata procesos por subcadena y con `kill()` |
| H-023 | Alta | confirmado | `core/llm.py:249` | El atajo local cierra procesos con "apaga la luz" o "apaga el PC" |
| H-020 | Media | confirmado | `core/server.py:50` | `broadcast` falla si cambian los clientes mientras envía |
| H-002 | Media | confirmado | `core/tools/apps.py:271` | `close_app` cierra apps sin confirmación |
| H-003 | Media | confirmado | `core/tools/__init__.py:33` | El timeout de 5 s por herramienta no existe |
| H-011 | Media | confirmado | `core/tools/files.py:97` | `open_file` ejecuta programas y scripts de Descargas |
| H-013 | Media | confirmado | `core/tools/media.py:86` | `media_control` y `mute` hacen lo contrario de lo pedido |
| H-015 | Media | confirmado | `core/tools/system.py:80` | `shutdown_pc` pregunta por una acción y ejecuta otra |
| H-024 | Media | confirmado | `core/llm.py:227` | El atajo local secuestra peticiones y siempre dice que funcionó |
| H-025 | Media | confirmado | `core/llm.py:337` | El atajo local bloquea el bucle de eventos |
| H-026 | Media | confirmado | `core/llm.py:384` | Las llamadas a Gemini no tienen tiempo máximo |
| H-028 | Media | confirmado | `core/__main__.py:125` | Whisper y RVC se cargan al arrancar el PC |
| H-030 | Media | confirmado | `core/pipeline.py:280` | Un error al procesar texto deja la wake word en pausa |
| H-004 | Baja | confirmado | `core/tools/__init__.py:29` | `print` sueltos y argumentos completos en logs |
| H-005 | Baja | confirmado | `core/tools/__init__.py:49` | Nombre de herramienta repetido se sobrescribe |
| H-009 | Baja | confirmado | `core/tools/apps.py:38` | Alias de apps fijos; `config.yaml → apps` se ignora |
| H-010 | Baja | confirmado | `core/tools/apps.py:104` | Fugas de handles y llamadas bloqueantes |
| H-012 | Baja | confirmado | `core/tools/files.py:136` | Errores menores en `files.py` |
| H-014 | Baja | confirmado | `core/tools/media.py:112` | Volumen dice "ok" aunque no cambie nada |
| H-017 | Baja | confirmado | `core/tools/timers.py:92` | Carrera, mensajes y persistencia de temporizadores |
| H-018 | Baja | confirmado | `core/tools/web.py:15` | Código duplicado y descripciones que no cuadran |
| H-021 | Baja | confirmado | `core/server.py:13` | Detalles de `server.py` |
| H-022 | Baja | confirmado | `app/src/ws.ts:58` | El cliente reenvía mensajes viejos al reconectar |
| H-027 | Baja | confirmado | `core/llm.py:408` | Detalles de `llm.py` |
| H-029 | Baja | confirmado | `core/__main__.py:30` | Detalles de `__main__.py` |
| H-031 | Baja | confirmado | `core/pipeline.py:118` | Avisos de temporizador se pisan con la conversación |
| H-032 | Baja | confirmado | `core/pipeline.py:231` | Detalles de `pipeline.py` |
| H-016 | — | descartado | `core/tools/timers.py:30` | Un temporizador puede no sonar nunca (el bucle sí se configura) |
