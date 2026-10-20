# Plan de auditoría total

Revisión completa de Miku Assistant, archivo por archivo y línea por línea. Este documento es **solo el plan**: no contiene hallazgos. Cada hallazgo se apunta en [hallazgos/](hallazgos/) mientras se revisa, con el formato de [hallazgos/README.md](hallazgos/README.md).

## Objetivo

Encontrar, con evidencia (`archivo:línea`):

1. **Seguridad**: lo que permita a un tercero, a una web o al propio LLM hacer algo no previsto en el PC.
2. **Errores**: lógica incorrecta, condiciones de carrera, excepciones no controladas, estados en los que Miku se cuelga.
3. **Recursos**: incumplimientos del presupuesto de [architecture.md](../architecture.md) (RAM/VRAM en reposo, latencia < 3 s, procesos que no mueren).
4. **Mantenibilidad**: código muerto, duplicado, valores fijos que deberían estar en `config.yaml`, desajustes entre docs y código.

Fuera de alcance: rediseñar la arquitectura o cambiar código durante la auditoría. Los arreglos se planifican al final.

## Reglas de trabajo

- **Un commit de referencia.** Se audita un commit fijo. Se anota su hash en `hallazgos/README.md` al empezar y no se cambia código hasta terminar.
- **Rama de trabajo.** Los hallazgos se apuntan en `develop` (o en una rama `audit/...` que salga de ella).
- **Lectura completa.** Cada archivo se lee de arriba abajo, en bloques de unas 50 líneas. Al terminar cada bloque se pasa la lista de comprobación de su categoría (sección "Listas de comprobación").
- **Apuntar en el momento.** Un hallazgo se escribe en cuanto se ve, no al final de la fase. Si es una sospecha sin confirmar, se apunta con estado `por-verificar`.
- **Evidencia obligatoria.** Cada hallazgo cita `archivo:línea` y explica cómo se produce el fallo (entrada → resultado). Sin evidencia no es un hallazgo.
- **Marcar el avance.** Al cerrar un archivo, se marca su casilla en este plan y se anota en el archivo de hallazgos de la fase "revisado hasta línea N de N".
- **Comprobar con herramientas.** Lo que se pueda verificar ejecutando algo (un test, un `nvidia-smi`, una conexión WebSocket desde el navegador) se verifica; el resultado va en el hallazgo.

## Severidad

| Nivel | Significado |
|---|---|
| **Crítica** | Un tercero puede ejecutar acciones en el PC, o se filtran secretos. |
| **Alta** | Miku se cuelga, pierde datos del usuario, o una acción destructiva se ejecuta sin confirmación. |
| **Media** | Fallo funcional con solución alternativa, o incumplimiento claro del presupuesto de recursos. |
| **Baja** | Calidad de código, configuración fija, logs, docs desactualizadas. |

## Fase 0: preparación (antes de leer código)

- [ ] Anotar el hash del commit auditado en `hallazgos/README.md`.
- [ ] Generar el mapa del código con graphify (`graphify-out/GRAPH_REPORT.md`) y guardar la lista de nodos centrales: `tool()`, `async_main()`, `MikuBrain`, `load_config()`, `MikuPipeline`, `WakeWordListener`, `Live2DManager`. Son los puntos donde un fallo tiene más alcance.
- [ ] Medir la **línea base** de recursos y anotarla en `hallazgos/00-linea-base.md`:
  - RAM de `app` y del backend con Miku oculta (Administrador de tareas).
  - VRAM con Miku oculta tras `unload_after_minutes` (`nvidia-smi`): debe ser 0 MB del proceso Python.
  - Latencia desde activación hasta que Miku empieza a hablar, 5 mediciones.
- [ ] Ejecutar análisis automáticos y guardar la salida resumida en `hallazgos/00-linea-base.md`:
  - Python: `ruff check core/`, `pip-audit -r core/requirements.txt`.
  - Frontend: `npx tsc --noEmit` y `npm audit` en `app/`.
  - Rust: `cargo audit` y `cargo clippy` en `app/src-tauri/`.
- [ ] Buscar secretos en todo el historial de git (`git log -p | grep -E "AIza|sk-|gh[op]_"`).

## Fase 1: herramientas de control del PC (`core/tools/`, 1222 líneas)

Es el límite de confianza más importante: aquí el texto que genera el LLM se convierte en acciones reales.

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/tools/__init__.py` (registro `@tool`) | 77 | [x] |
| `core/tools/apps.py` | 387 | [x] |
| `core/tools/files.py` | 138 | [x] |
| `core/tools/media.py` | 173 | [x] |
| `core/tools/notes.py` | 79 | [x] |
| `core/tools/system.py` | 97 | [x] |
| `core/tools/timers.py` | 174 | [x] |
| `core/tools/web.py` | 97 | [x] |

Preguntas que deben quedar respondidas:

- ¿La lista de herramientas registradas coincide exactamente con [tools.md](../tools.md)? ¿Puede registrarse algo fuera de ella?
- ¿Alguna herramienta usa `shell=True`, `os.system`, `ShellExecute` o concatena texto del LLM en un comando?
- `open_app` / `close_app`: ¿cómo se resuelve el nombre de la app? ¿Puede el LLM pasar una ruta o ejecutable arbitrario?
- `find_file` / `open_file` / `open_folder`: ¿hay validación de rutas? ¿Puede abrir un `.exe`, `.bat`, `.lnk` o una ruta UNC (`\\servidor\...`)?
- `open_url` / `web_search`: ¿se limita el esquema a `http`/`https`? ¿Qué pasa con `file://`, `javascript:` o un protocolo registrado (`ms-settings:`, etc.)?
- `take_note`: ¿se puede escribir fuera del archivo de notas? ¿Crece sin límite?
- `set_timer` / `set_reminder`: ¿hay límite de cantidad y duración? ¿Se cancelan al salir?
- `lock_pc`, `close_app` y cualquier acción destructiva: ¿piden confirmación siempre, también desde el atajo local de `llm.py`?
- ¿Cada herramienta captura sus errores y devuelve un mensaje, en vez de lanzar una excepción que rompa el turno?

## Fase 2: superficie de red (`core/server.py`, `app/src/ws.ts`, 360 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/server.py` | 218 | [x] |
| `app/src/ws.ts` | 142 | [x] |

- ¿El servidor escucha solo en `127.0.0.1`?
- ¿Se comprueba la cabecera `Origin`? Cualquier página abierta en el navegador puede conectarse a `ws://127.0.0.1:8765`. Hay que **probarlo**: abrir una página local que se conecte y envíe `text_input`.
- ¿Hay límite de tamaño de mensaje y de clientes simultáneos?
- ¿Se valida el JSON entrante (tipo, campos, longitudes) antes de usarlo?
- ¿`broadcast` aguanta que un cliente se desconecte a mitad de envío?
- En `ws.ts`: ¿la reconexión tiene espera creciente y tope? ¿Se descartan mensajes de tipos desconocidos?

## Fase 3: cerebro (`core/llm.py`, 441 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/llm.py` | 441 | [x] |

- ¿La API key se lee solo de `.env` y nunca aparece en logs ni en errores?
- **Inyección de prompts**: ¿qué texto externo llega al modelo (resultados de herramientas, títulos de ventanas, contenido web, notas)? ¿Puede ese texto pedir una herramienta destructiva sin confirmación?
- El atajo local (`_try_fast_path_tool`): ¿qué patrones reconoce? ¿Puede activar algo distinto de lo que el usuario dijo?
- Cascada de modelos de respaldo: ¿qué pasa si fallan todos? ¿Hay tiempo máximo por llamada?
- ¿El historial se limita a 10 turnos como dice la arquitectura?
- Parser de emociones `[emocion]`: ¿qué hace con etiquetas desconocidas o mal formadas?
- `is_farewell`: ¿falsos positivos que oculten a Miku a mitad de conversación?

## Fase 4: orquestación y arranque (885 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/__main__.py` (`async_main`) | 160 | [x] |
| `core/pipeline.py` (`MikuPipeline`) | 388 | [x] |
| `core/resources.py` (`ResourceManager`) | 104 | [x] |
| `core/config.py` | 206 | [x] |
| `config.yaml` | 27 | [x] |

- Recorrer el flujo completo de una petición (pasos 1–12 de [architecture.md](../architecture.md)) y marcar en qué línea ocurre cada paso.
- ¿Hay llamadas bloqueantes (CPU, disco, red) dentro del bucle `asyncio` sin `to_thread`/executor?
- ¿Se guardan referencias a las tareas creadas con `create_task`? ¿Se registran sus excepciones?
- Carreras entre `warmup` y `unload`: ¿qué pasa si el usuario activa a Miku justo cuando se está descargando un modelo?
- Barge-in y watchdog de `speak_done`: ¿puede quedar el pipeline en un estado del que no sale?
- Apagado: ¿`signal_handler` cierra el servidor, el micrófono, el worker de RVC y los timers?
- `config.py`: ¿qué pasa con un `config.yaml` incompleto o con tipos erróneos? ¿Hay valores fijos en el código que deberían estar en la config?

## Fase 5: audio de entrada (570 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/audio_in.py` | 185 | [x] |
| `core/stt.py` | 145 | [x] |
| `core/wakeword.py` | 240 | [x] |

- ¿El micrófono se cierra siempre al terminar de grabar, también si hay excepción?
- Límite de 15 s de grabación y 0,8 s de silencio: ¿están en la config y se respetan?
- Whisper: ¿corre en CPU `int8` como exige la arquitectura? ¿Se libera de verdad al descargar (`gc.collect`)?
- Wake word: ¿consumo de CPU en reposo? ¿Cómo se filtran los falsos positivos? ¿Qué pasa si el dispositivo de audio cambia o desaparece?

## Fase 6: voz de salida y GPU (1136 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/tts.py` | 103 | [x] |
| `core/rvc.py` (`RVCManager`) | 209 | [x] |
| `core/rvc_worker.py` | 392 | [x] |
| `core/rmvpe.py` | 432 | [x] |

- **Regla principal**: confirmar con `grep` y en ejecución que el proceso principal nunca importa `torch`.
- Protocolo JSON-RPC por stdio: ¿qué pasa si el worker escribe basura en stdout, se cuelga o muere a mitad de una conversión?
- ¿Hay tiempo máximo por petición al worker? ¿Se mata con `kill` si `terminate` no basta?
- ¿Puede quedar un worker huérfano si el backend muere? Probarlo matando el backend con el worker vivo.
- Caché de voz (`cache/voice/`, MD5): ¿crece sin límite? ¿Qué pasa con un archivo corrupto?
- Degradación: si RVC falla, ¿se usa la voz base de edge-tts? Si edge-tts falla (sin internet), ¿solo subtítulo?
- ¿Se cargan los modelos `.pth` con `torch.load(..., weights_only=True)`? Un `.pth` descargado puede ejecutar código al cargarse.

## Fase 7: modelos RVC incluidos (`core/infer_pack/`, 2438 líneas)

Es código de terceros (RVC/VITS). Se revisa para detectar modificaciones locales y riesgos, no su matemática.

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/infer_pack/models.py` | 1142 | [x] |
| `core/infer_pack/modules.py` | 522 | [x] |
| `core/infer_pack/attentions.py` | 417 | [x] |
| `core/infer_pack/transforms.py` | 193 | [x] |
| `core/infer_pack/commons.py` | 164 | [x] |
| `core/infer_pack/__init__.py` | 0 | [x] |

- Identificar de qué versión del repo original de RVC viene y compararlo con `diff` contra ella. Cada diferencia se lee línea por línea.
- Anotar la licencia del original y si se cumple.
- Marcar las clases que no se usan nunca (el grafo muestra varios sintetizadores: `SynthesizerTrnMs256NSFsid`, `SynthesizerTrnMs768NSFsid`, sus variantes `_nono`).

## Fase 8: frontend (1746 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `app/src/main.ts` | 384 | [x] |
| `app/src/live2d.ts` | 580 | [x] |
| `app/src/animations.ts` | 219 | [x] |
| `app/src/clickthrough.ts` | 99 | [x] |
| `app/src/ui.ts` | 126 | [x] |
| `app/src/styles.css` | 225 | [x] |
| `app/index.html` (incluye el parche de Cubism 5) | 41 | [x] |
| `app/public/samples/index.html` | 72 | [x] |

- **XSS**: ¿el texto del LLM o del usuario se inserta con `innerHTML`? Con `withGlobalTauri` activo, un XSS da acceso a la API de Tauri.
- Con Miku oculta: ¿`app.ticker.stop()` y el intervalo de click-through se detienen de verdad? Comprobarlo con la pestaña de rendimiento de las DevTools.
- ¿Se liberan texturas, canvas de partículas y listeners al ocultar o recargar el modelo?
- Audio: ¿qué pasa si llega un `speak` mientras otro está sonando?
- Click-through: ¿el hit-test respeta la escala de DPI de Windows y varios monitores?
- `samples/index.html`: ¿debe ir en el build de producción?

## Fase 9: shell de Tauri (181 líneas)

| Archivo | Líneas | Hecho |
|---|---|---|
| `app/src-tauri/src/lib.rs` | 85 | [ ] |
| `app/src-tauri/src/main.rs` | 6 | [ ] |
| `app/src-tauri/build.rs` | 3 | [ ] |
| `app/src-tauri/Cargo.toml` | 27 | [ ] |
| `app/src-tauri/tauri.conf.json` | 41 | [ ] |
| `app/src-tauri/capabilities/default.json` | 19 | [ ] |

- ¿Hay una CSP definida en `tauri.conf.json`? ¿Es `null`?
- ¿`withGlobalTauri` es necesario? Si no, desactivarlo reduce el impacto de un XSS.
- ¿Los permisos de `capabilities/default.json` son los mínimos que usa el frontend? Listar cada permiso y dónde se usa.
- ¿El atajo global se libera al salir? ¿El menú de bandeja cierra también el backend?

## Fase 10: configuración, dependencias y scripts

| Archivo | Líneas | Hecho |
|---|---|---|
| `core/requirements.txt` | 18 | [ ] |
| `app/package.json` | 25 | [ ] |
| `app/vite.config.ts` | 38 | [ ] |
| `app/tsconfig.json` | 23 | [ ] |
| `start.bat` | 37 | [ ] |
| `stop.bat` | 20 | [ ] |
| `install_autostart.bat` | 23 | [ ] |
| `uninstall_autostart.bat` | 19 | [ ] |
| `.gitignore`, `.env.example` | 39 | [ ] |

- ¿Las versiones de las dependencias están fijadas? ¿Alguna sin uso?
- `app/package-lock.json` (2010 líneas) no se lee a mano: se revisa con `npm audit` (fase 0) y se comprueba que coincide con `package.json`.
- `stop.bat`: ¿mata solo los procesos de Miku o cualquier `python`/`pythonw` del sistema?
- `start.bat`: ¿qué pasa si el puerto 8765 ya está ocupado por otro programa?
- `install_autostart.bat`: ¿qué escribe y dónde (registro, carpeta de inicio)? ¿Con qué permisos?

## Fase 11: scripts de prueba (`scratch/`, ~4400 líneas, 63 archivos)

No son código de producción, pero se leen enteros porque pueden contener secretos, rutas personales o lógica que debería estar en tests reales.

- [ ] Leer cada archivo y clasificarlo en una tabla dentro de `hallazgos/11-scratch.md`: **convertir en test**, **conservar como herramienta de diagnóstico** o **borrar**.
- [ ] Prestar atención a `test_token.py`, `test_launch_with_token.py`, `test_createprocess_desktop.py` y `test_switch_desktop.py`: manipulan tokens y escritorios de Windows.
- [ ] `test_suite.py` es lo más parecido a una batería de tests: anotar qué cubre y qué no.
- [ ] `train_hey_miku*.py` (tres versiones): decidir cuál es la buena.

## Fase 12: documentación frente a código

- [ ] [architecture.md](../architecture.md): cada componente, mensaje del protocolo WebSocket y cifra del presupuesto existe en el código.
- [ ] [tools.md](../tools.md): lista, parámetros y confirmaciones coinciden con `core/tools/`.
- [ ] [persona.md](../persona.md): las emociones y frases fijas coinciden con `llm.py` y `tts.py`.
- [ ] [roadmap.md](../roadmap.md): las casillas marcadas corresponden a funciones que existen.
- [ ] [setup.md](../setup.md) y el `README.md` raíz: los pasos de instalación funcionan en limpio.
- [ ] `CHANGELOG.md`: completo y sin entradas que contradigan el código.

## Fase 13: cierre

- [ ] Revisar todos los hallazgos `por-verificar` y confirmarlos o descartarlos.
- [ ] Completar el índice de `hallazgos/README.md` con todos los hallazgos ordenados por severidad.
- [ ] Escribir `hallazgos/99-resumen.md`: totales por severidad y fase, los 5 hallazgos más importantes y un orden de arreglo propuesto (críticos y altos primero, agrupados por archivo para minimizar cambios).
- [ ] Repetir las mediciones de la fase 0 si se arregló algo, y comparar.

## Listas de comprobación por categoría

Se aplican a cada bloque de ~50 líneas leído.

**Todo el código**
- ¿Hace lo que dice su nombre o docstring?
- ¿Qué pasa con entrada vacía, `None`, muy larga o con caracteres raros (acentos, emojis, rutas con espacios)?
- ¿Se capturan las excepciones al nivel adecuado, sin `except:` vacíos que oculten errores?
- ¿Hay código muerto, duplicado o `print` sueltos en vez de logs?
- ¿Hay valores fijos (rutas, tiempos, umbrales) que deberían estar en `config.yaml`?

**Python asíncrono (`core/`)**
- ¿Hay llamadas bloqueantes dentro de `async def`?
- ¿Cada `create_task` tiene referencia guardada y manejo de excepción?
- ¿Los recursos (micrófono, archivos, subprocesos) se cierran en `finally` o con `with`?
- ¿Hay estado compartido modificado desde varios hilos sin protección?

**Límites de confianza (herramientas, WebSocket, LLM)**
- ¿De dónde viene cada dato y quién lo controla (usuario, LLM, red, web)?
- ¿Se valida antes de usarse en una ruta, URL, comando o API de Windows?
- ¿Una acción irreversible exige confirmación?

**Recursos**
- ¿Algo queda corriendo con Miku oculta (bucles, timers, render, polling < 100 ms)?
- ¿Lo que se carga en memoria se libera al descargar?

**TypeScript / frontend**
- ¿Se inserta texto externo en el DOM sin escapar?
- ¿Cada `setInterval`, `addEventListener` y `requestAnimationFrame` tiene su limpieza?

## Orden y estimación

Las fases van ordenadas por riesgo: primero lo que puede causar daño en el PC (1–3), luego estabilidad (4–6), y después el resto. Unas 10 300 líneas propias más ~4400 de `scratch/`. A unas 400 líneas revisadas con cuidado por hora, son **unas 30–35 horas** en total, repartibles en sesiones de una fase cada una.
