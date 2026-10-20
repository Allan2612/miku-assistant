# Hallazgos de la auditoría

Aquí se apunta lo que se va encontrando al seguir el [plan de auditoría](../plan.md).

- **Commit auditado:** `01f50c8`
- **Inicio:** 2026-10-20
- **Estado:** fase 1 en curso (fase 0 pendiente: mediciones y análisis automáticos)

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
| H-001 | Alta | confirmado | `core/tools/__init__.py:21` | La confirmación de acciones destructivas no está implementada en código |
| H-006 | Alta | confirmado | `core/tools/apps.py:260` | `open_app` ejecuta cualquier línea de comandos del LLM |
| H-007 | Alta | por-verificar | `core/tools/apps.py:367` | `type_text` + alias de consola permiten ejecutar comandos |
| H-008 | Alta | confirmado | `core/tools/apps.py:290` | `close_app` mata procesos por subcadena y con `kill()` |
| H-002 | Media | confirmado | `core/tools/apps.py:271` | `close_app` cierra apps sin confirmación |
| H-003 | Media | confirmado | `core/tools/__init__.py:33` | El timeout de 5 s por herramienta no existe |
| H-011 | Media | confirmado | `core/tools/files.py:97` | `open_file` ejecuta programas y scripts de Descargas |
| H-013 | Media | confirmado | `core/tools/media.py:86` | `media_control` y `mute` hacen lo contrario de lo pedido |
| H-015 | Media | confirmado | `core/tools/system.py:80` | `shutdown_pc` pregunta por una acción y ejecuta otra |
| H-016 | Media | por-verificar | `core/tools/timers.py:30` | Un temporizador puede no sonar nunca y aun así confirmarse |
| H-004 | Baja | confirmado | `core/tools/__init__.py:29` | `print` sueltos y argumentos completos en logs |
| H-005 | Baja | confirmado | `core/tools/__init__.py:49` | Nombre de herramienta repetido se sobrescribe |
| H-009 | Baja | por-verificar | `core/tools/apps.py:38` | Alias de apps fijos; `config.yaml → apps` se ignora |
| H-010 | Baja | confirmado | `core/tools/apps.py:104` | Fugas de handles y llamadas bloqueantes |
| H-012 | Baja | confirmado | `core/tools/files.py:136` | Errores menores en `files.py` |
| H-014 | Baja | confirmado | `core/tools/media.py:112` | Volumen dice "ok" aunque no cambie nada |
| H-017 | Baja | confirmado | `core/tools/timers.py:92` | Carrera, mensajes y persistencia de temporizadores |
