# Fase 0 · Línea base

## Análisis automáticos (hechos el 2026-10-21 sobre el commit auditado)

| Herramienta | Resultado |
|---|---|
| Secretos en todo el historial de git (`git log -p --all`, patrones `AIza…`, `sk-…`, `gh[op]_…`) | **0** coincidencias |
| `npx tsc --noEmit` (frontend) | **sin errores** |
| `npm audit --omit=dev` (frontend) | **0 vulnerabilidades** |
| `pip-audit` sobre `core/.venv` | **1 vulnerabilidad:** `certifi 2026.10.18` (PYSEC-2026-4320), corregida en `2026.10.19`. `torch` y `torchaudio` no se pudieron auditar por ser versiones *nightly* que no están en PyPI (ver H-052) |
| `ruff check core/` (sin `infer_pack/`, reglas por defecto del entorno) | 244 avisos, 150 corregibles automáticamente. Los más relevantes: 15 imports sin usar (F401), 12 `try/except/pass` que ocultan errores (S110), 2 nombres sin definir (F821, previsiblemente `N_MELS`/`N_CLASS` de `rmvpe.py`, H-042) y 1 import de depurador (`pdb`, T100) |

**Acción derivada:** actualizar `certifi` (`pip install -U certifi`). Se añade como nota, sin hallazgo propio.

## No hecho: falta ejecutar con la app en marcha

Estas mediciones necesitan el asistente arrancado y una persona usándolo; quedan pendientes:

- [ ] RAM de `app.exe` y del backend con Miku oculta (Administrador de tareas).
- [ ] VRAM con Miku oculta tras `unload_after_minutes` (`nvidia-smi`): el proceso `pythonw -m core` no debe aparecer y no debe quedar ningún `rvc_worker`.
- [ ] Latencia desde que el usuario termina de hablar hasta que Miku empieza, 5 mediciones.
- [ ] CPU en reposo con la wake word activa (objetivo < 1 %, ver H-037).
- [x] `cargo audit` y `cargo clippy` en `app/src-tauri/` (23-oct): clippy sin avisos; audit encontró tokio 1.54.0 (RUSTSEC-2026-0384), actualizado a 1.54.1. Quedan 2 avisos de crates de GTK que solo se usan en Linux.

Las pruebas en vivo de los hallazgos `por-verificar` están listadas en `99-resumen.md`.
