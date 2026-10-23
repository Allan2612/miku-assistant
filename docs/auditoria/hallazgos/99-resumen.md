# Resumen de la auditoría

- **Commit auditado:** `01f50c8` · **Fechas:** 2026-10-20 a 2026-10-21
- **Alcance:** todo el código propio (unas 10 300 líneas), el código de terceros de RVC comparado con su original, los 63 scripts de `scratch/`, la configuración, los scripts `.bat` y la documentación.

## Totales

| Severidad | Confirmados | Por verificar | Total |
|---|---|---|---|
| Crítica | 2 | 0 | **2** |
| Alta | 3 | 1 | **4** |
| Media | 18 | 3 | **21** |
| Baja | 30 | 1 | **31** |
| **Total** | **53** | **5** | **58** |

Además, 1 hallazgo descartado tras verificarlo (H-016).

## Los 5 más importantes

1. **H-019 (Crítica) · Cualquier web puede controlar a Miku.** El servidor WebSocket acepta conexiones de cualquier origen, sin autenticación. Una página abierta en el navegador puede enviarle órdenes y leer sus respuestas.
2. **H-006 (Crítica) · `open_app` ejecuta líneas de comandos.** Si el nombre no es un alias ni un acceso directo, se pasa tal cual a `CreateProcessW` y, como último recurso, a `cmd.exe` con `shell=True`. Junto con H-019, una web visitada puede ejecutar programas en el PC.
3. **H-001 (Alta) · No hay confirmación real de acciones destructivas.** `destructive` y `confirm_destructive` no se leen nunca; el apagado se "confirma" con un argumento que rellena el propio LLM.
4. **H-023 + H-008 (Altas) · Cerrar procesos por error.** El atajo local manda a `close_app` cualquier frase que empiece por "cierra" o "apaga", y `close_app` mata con `kill()` todo proceso cuyo nombre contenga ese texto: "apaga el PC" mata procesos en vez de apagar.
5. **H-038 (Media) · Respuestas de RVC desfasadas.** Tras un timeout con el worker, cada respuesta lee la de la petición anterior y Miku pronuncia la frase previa. La primera descarga de ContentVec (H-041) lo hace probable en una instalación nueva.

## Orden de arreglo propuesto

Agrupado por archivo para tocar cada uno una sola vez:

1. **`core/server.py`:** H-019 (comprobar `origins` y token; quitar `text_input` mientras no haya caja de texto), H-020, H-021.
2. **`core/tools/apps.py`:** H-006, H-007, H-008, H-002, H-010.
3. **`core/tools/__init__.py` + `pipeline.py`:** H-001 (confirmación aplicada en código), H-003, H-004, H-005, H-030.
4. **`core/llm.py`:** H-023, H-024, H-025, H-026, H-027.
5. **`core/rvc.py`:** H-038, H-039.
6. **Tauri y scripts:** H-049 (permisos del atajo global), H-050 ("Salir" apaga el backend), H-053 (`stop.bat`), H-051.
7. **Frontend:** H-045 (intervalo de *lip sync*), H-047 (click-through), H-044.
8. **Resto de herramientas:** H-011, H-013, H-015, H-014, H-012, H-017, H-018.
9. **Recursos y audio:** H-028, H-034, H-035, H-031, H-040.
10. **Dependencias, tests y documentación:** H-052 (y actualizar `certifi`), H-055 (empezar los tests junto con los arreglos 1-4), H-057, H-058, H-059, H-043.

## Pendiente de verificar en vivo

| Hallazgo | Prueba |
|---|---|
| H-019 | Con el backend arrancado, abrir un HTML local que se conecte a `ws://127.0.0.1:8765` y envíe `{"type":"text_input","text":"¿qué hora es?"}`. Si Miku responde, queda confirmado en ejecución. |
| H-007 | Abrir el Bloc de notas, pedir a Miku que escriba un texto con salto de línea y comprobar si pulsa Enter. **No probarlo con una consola.** |
| H-034 | Con música de fondo, activar a Miku, decir una frase corta y ver en `cache/core.log` si la grabación termina por silencio o por tiempo. |
| H-035 | Pasar 20 veces 3 s de ruido suave a `STTManager._transcribe_sync` y contar las transcripciones que repiten frases del prompt. |
| H-044 | Con otra app enfocada, activar a Miku por voz y pedir "escribe hola": ¿dónde aparece el texto? |
| H-047 | Con Miku visible, sacar el ratón de ella y volver a ponerlo encima: ¿responde al clic? |
| H-049 | Con otra ventana enfocada, pulsar Ctrl+Alt+M y mirar la consola de las DevTools. |
| H-053 | Leer el código basta; no ejecutar `stop.bat` con trabajo sin guardar en VS Code. |

## Lo que está bien

- No se filtran secretos: la API key solo está en `.env`, nunca en logs ni en el historial de git.
- No hay XSS en el frontend: todo el texto externo entra con `textContent`.
- El aislamiento de la GPU está bien planteado: `torch` no entra en el proceso principal, el worker de RVC sale solo al cerrarse su stdin y los `.pth` se cargan con `weights_only`.
- El micrófono de la grabación se cierra siempre, incluso con errores o cancelaciones.
- `open_url` valida bien el esquema de la URL.
- El código de RVC incluido no tiene modificaciones locales peligrosas respecto al original.
- 0 vulnerabilidades en las dependencias del frontend.

## Límites de esta auditoría

- Las mediciones de recursos y latencia de la fase 0 no se hicieron: necesitan la app en marcha (ver `00-linea-base.md`).
- Los 63 scripts de `scratch/` se revisaron con búsqueda de riesgos y por propósito; solo se leyeron enteros los que se proponen convertir en tests.
- `CHANGELOG.md` se comprobó en sus afirmaciones verificables, no entrada por entrada.
- `package-lock.json` se revisó con `npm audit`, no a mano. `cargo audit` no se ejecutó.

## Arreglos (2026-10-21)

**55 de 58 arreglados** (commits `9de705b` a `5f9f07b` en `develop`). Todos los críticos, altos y medios están cerrados.

**Parcial (0):** H-039 se completó el 2026-10-23: `terminate_worker` cierra el stdin del worker y espera su salida en segundo plano, así asyncio cierra las *pipes* (probado con `python -X dev`: sin `ResourceWarning`).

**Decididos (2):**

- H-002: `close_app` no pide confirmación (decisión del usuario). Ya solo cierra por nombre exacto y nunca procesos del sistema.
- H-028: Whisper y RVC se siguen cargando al arrancar. Cargar RVC al activar a Miku no puede ocultar sus 35-80 s de carga, y se descargan solos tras 10 min sin uso. Además, si RVC está cargando, la respuesta usa la voz base en lugar de esperar, y la transcripción ya no espera a RVC.

**Verificación:** 10 archivos de test en `tests/` (`core\.venv\Scripts\python.exe -m tests.<nombre>`), todos pasan; `tsc` y `cargo check` sin errores. RVC se probó de punta a punta con los modelos reales en la RTX 3050. La detección de voz se probó con las muestras de voz y señales sintéticas, no con el micrófono.

**Hallazgos de la propia tanda de arreglos:**

- La primera carga de RVC tardó 82,6 s: el timeout antiguo de 35 s nunca la habría dejado terminar (confirma H-038).
- Una conversión tarda entre 6 y 20 s con la GPU compartida (otro programa la tenía al 97 % durante la prueba); el timeout de conversión pasó a 60 s.
- Los tests destaparon que "quita el silencio" silenciaba el PC; también está corregido.

**Pendiente de probar con la app recompilada** (`npm run tauri build`):

1. Que la app arranca y dibuja a Miku con la nueva CSP (si sale en blanco, revertir el commit `aca41fa`).
2. Que conecta con el backend con el origen `http://tauri.localhost`.
3. Ctrl+Alt+M con otra ventana enfocada; pasar el ratón por encima de Miku y hacer clic.
4. "Salir" desde la bandeja: el micrófono debe quedar libre.
5. `stop.bat` y `start.bat` (este ahora se niega a arrancar dos veces).
6. Hablarle con música de fondo: la grabación debe cortar al terminar la frase.
