# Fase 11 · Scripts de prueba (`scratch/`)

Avance: 63 archivos, ~4400 líneas · **fase completa**

**Método:** no son código de producción. Se buscaron en los 63 archivos secretos, rutas personales, llamadas destructivas (`kill`, `terminate`, `shutdown`, borrado de archivos, `shell=True`) y accesos a red; después se leyó la cabecera, los imports y el propósito de cada uno para clasificarlo. Los scripts marcados como "convertir en test" se leyeron completos.

**Resultado de la búsqueda de riesgos:** ningún secreto ni API key. Ninguna llamada a `shutdown_pc`, `lock_pc` ni borrado de archivos. Los `shell=True` (`test_launch_methods.py:55`, `test_launch_to_user_desktop.py:22`, `test_notepad_double.py:7`, `:11`) solo abren el Bloc de notas con texto fijo. `test_token.py` y `test_launch_with_token.py` abren el token de `explorer.exe` para lanzar procesos en el escritorio del usuario: no elevan privilegios (mismo usuario), son experimentos ya incorporados a `apps.py`.

## Clasificación

| Decisión | Archivos |
|---|---|
| **Convertir en test** (pytest, en `core/tests/` o `tests/`) | `test_suite.py` (base: config, registro de herramientas, parseo de emociones, wake word, VAD), `test_audio_in_logic.py`, `test_fast_path_expanded.py` y `test_all_user_prompts.py` (casos del atajo local: justo lo que necesitan H-023/H-024), `test_fallback.py` (cascada de modelos) |
| **Conservar como diagnóstico** | `check_audio_devices.py`, `check_devices.py`, `check_monitors.py`, `list_voices.py`, `list_visible_windows.py`, `live_wakeword_test.py`, `test_wakeword.py`, `test_stt_speed.py`, `test_warm_speed.py`, `test_rvc_pipeline.py` (prueba RVC de punta a punta), `generate_voice_samples.py` (genera `app/public/samples/`), `test_all_26_tools.py` (prueba manual de herramientas; ver H-056), `train_hey_miku_v2.py` |
| **Borrar** (experimentos ya resueltos o duplicados) | Lanzamiento de apps: `test_launch_methods.py`, `test_launch_methods_default.py`, `test_launch_to_user_desktop.py`, `test_launch_with_token.py`, `test_createprocess_desktop.py`, `test_switch_desktop.py`, `test_token.py`, `test_explorer_launch.py`, `test_shellexec_default.py`. Bloc de notas y ventanas: `test_notepad_double.py`, `test_clean_notepad.py`, `find_all_notepad_windows.py`, `inspect_notepad_hwnd.py`, `check_notepad_hwnds.py`, `check_window.py`, `check_window_pids.py`, `check_sessions.py`. Gemini y herramientas: `debug_afc.py`, `inspect_fc.py`, `test_tracing.py`, `test_gemini_models.py`, `test_brain_tools.py`, `test_all_tools.py`, `test_all_tools_fastpath.py`, `test_media_default.py`, `test_all_volume.py`, `test_opera_and_wakeword.py`. Ajuste de RVC: `test_anti_petardeo.py`, `test_anti_petardeo_latina.py`, `test_latina_samples.py`, `test_clean_rvc.py`, `test_contentvec_rvc.py`, `test_rvc_full.py`, `test_e2e_rvc.py`, `check_intelligibility.py`. Entrenadores viejos: `train_hey_miku.py`, `train_hey_miku_local.py` |

### H-055 · No hay tests automatizados de lo que más riesgo tiene

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `scratch/test_suite.py:14-100` (5 funciones de test), todo el proyecto
- **Categoría:** mantenibilidad / seguridad

**Qué pasa:** lo único parecido a una batería de tests es `scratch/test_suite.py`, que se ejecuta a mano y cubre: carga de config, que existan ciertas herramientas registradas, el parseo de emociones, el arranque del motor de wake word y la lógica del VAD. No hay ningún test para lo que la auditoría encontró más frágil: el atajo local (H-023, H-024), la validación de entradas de las herramientas (H-006, H-008, H-011, H-013, H-015), la confirmación de acciones destructivas (H-001), el origen del WebSocket (H-019) ni el protocolo con el worker de RVC (H-038). Los arreglos de esta auditoría no tendrían red de seguridad.

**Propuesta:** crear una carpeta `tests/` con pytest y empezar por tests pequeños de funciones puras: `_try_fast_path_tool` con frases reales (las listas de `test_all_user_prompts.py` sirven), `_clean_query`/`close_app` con un `psutil.process_iter` simulado, `media_control`/`mute` con `_press_key` simulado, y una conexión al servidor con `Origin: https://evil.example` que debe ser rechazada.

### H-056 · Detalles de `scratch/` y de los modelos de wake word

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `scratch/test_all_26_tools.py:49`, `models/wakeword/hey_miku.onnx.data`, `scratch/train_hey_miku*.py`
- **Categoría:** mantenibilidad

**Qué pasa:**

- `test_all_26_tools.py` ejecuta `close_app("bloc de notas")`, que mata con `kill()` **todos** los Bloc de notas abiertos (H-008). Ejecutarlo con notas sin guardar las pierde.
- Hay tres entrenadores de wake word. Por las fechas, el modelo actual (`hey_miku.onnx`, 05:55) salió de `train_hey_miku_v2.py` (05:54). El archivo `hey_miku.onnx.data` (01:57) es de una exportación anterior y probablemente sobra: hay que confirmar que el modelo carga sin él antes de borrarlo.
- `scratch/` está versionado en git con 63 archivos; tras la limpieza, quedaría en unos 15.

**Propuesta:** avisar en la cabecera de `test_all_26_tools.py`, borrar los entrenadores viejos y, tras comprobarlo, `hey_miku.onnx.data`.
