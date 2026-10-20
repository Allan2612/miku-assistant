# Hallazgos de la auditoría

Aquí se apunta lo que se va encontrando al seguir el [plan de auditoría](../plan.md).

- **Commit auditado:** _(anotar el hash al empezar la fase 0)_
- **Inicio:** _(fecha)_
- **Estado:** sin empezar

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
| | | | | |
