# Herramientas de control del PC

Lista **cerrada** (38). Gemini solo puede invocar estas funciones, mediante function calling. Cada una devuelve un dict `{ "ok": bool, "result": str }` corto.

**Una petición por turno.** Gemini pide las herramientas y escribe la frase de Miku en la **misma** respuesta. Las herramientas se ejecutan en local y su resultado **no** vuelve a Gemini (AFC desactivado). Por eso Miku lee el `result` tal cual, en lugar de su frase, en tres casos:
- cuando la herramienta falla;
- cuando pide confirmación;
- cuando es una herramienta que devuelve datos (`SPEAK_RESULT_TOOLS` en `llm.py`): `find_file`, `read_notes`, `get_datetime`, `get_system_status`, `list_timers`, `read_clipboard`, `read_text_file` y `list_open_apps`.

Esos resultados se escriben para ser leídos en voz alta: sin viñetas, sin `#` y sin marcas de tiempo.

Leyenda: 🔒 = requiere confirmación del usuario antes de ejecutarse.

## Apps y ventanas — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `open_app` | `name: str` | 0) Opera ya abierto: trae su ventana al frente (lanzarlo de nuevo abría otra ventana); 1) alias de `config.yaml → apps`; 2) búsqueda difusa en accesos directos del menú Inicio (`%ProgramData%` y `%AppData%\Microsoft\Windows\Start Menu`), cacheada al arrancar; 3) `os.startfile`. Si hay varias coincidencias, devuelve las opciones |
| `close_app` | `name: str` | `psutil`: solo procesos con el **nombre exacto** (o su alias); nunca procesos del sistema ni el propio Miku. `terminate()` y, si a los 3 s sigue vivo, `kill()`. Sin confirmación (decisión revisable, H-002) |
| `list_open_apps` | — | Ventanas visibles como en la barra de tareas (con título, sin dueño, ni ocultas ni de herramienta) → nombre del proceso con nombre amigable ("Visual Studio Code", "el Bloc de notas"), sin duplicados y sin la propia Miku. Se lee en voz alta |
| `focus_app` | `name: str` | Traer ventana al frente |
| `window_action` | `name: str, action: minimize \| maximize \| restore` | `ShowWindow` sobre la primera ventana visible cuyo título contiene el nombre. Un nombre vacío se rechaza (coincidiría con cualquier ventana) |
| `show_desktop` | — | Tecla Win+D |

## Medios y sonido — `tools/media.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `media_control` | `action: play_pause \| next \| previous \| stop` | Teclas multimedia virtuales |
| `set_volume` | `level: int (0-100)` | `pycaw` |
| `change_volume` | `delta: int` | `pycaw` |
| `mute` | `on: bool` | `pycaw` |

## Web — `tools/web.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `open_url` | `url: str, tab_id?` | Por la extensión de Miku en Opera (ver abajo); sin ella, `opera.exe <url>`. Solo `http`/`https`. Comprueba por DNS (máx. 2 s) que la dirección exista; si no, abre Google con ese nombre. Dice la dirección sin `https://www.`. `tab_id`: carga en esa pestaña en vez de abrir otra (corrección "no, era X": la pestaña marcada "abierta por Miku" en el estado) |
| `web_search` | `query: str, tab_id?` | Abre Google con la búsqueda (quita "en Opera" del final). La descripción le dice al modelo que solo la use si le piden buscar: antes abría Google para "¿cuánto mide la torre Eiffel?" |
| `youtube_search` | `query: str` | Abre la página de resultados en YouTube (no reproduce) |
| `browser_tabs` | `action, tab_ids: list[int]` | Pestañas de Opera **por número**, el que trae el estado del PC: `close` (varias a la vez: "cierra todas menos X" = todas las demás, fijadas incluidas), `activate`, `reload`, `back`, `forward`. Rechaza números que no están en el estado y no hace nada. Necesita la extensión; sin ella lo dice. Sustituye a `browser_action`, que simulaba atajos de teclado y fallaba con pestañas fijadas, Ctrl+Tab por uso reciente, el diálogo de cierre y el foco robado |
| `open_website` | `name, tab_id?` | Abre la web de algo **por su nombre** ("la página del Banco de Costa Rica"): lee el destino de la redirección `!ducky` de DuckDuckGo (primer resultado) y dice el dominio al que fue ("Abrí bancobcr.com"), porque el primer resultado no siempre es el pensado ("tyt soluciones" dio tytsolutions.com). Sin resultado: búsqueda en Google |
| `youtube_play` | `query: str, tab_id?` | **Reproduce** el primer resultado: lee el `videoId` de la página de resultados (sin API key, ~1 s) y abre `watch?v=`. Sin internet o sin resultado, abre la búsqueda. **Reutiliza la pestaña:** si la última pestaña que abrió Miku sigue abierta y es de YouTube, carga ahí la nueva canción (la anterior deja de sonar). Dice el título corto (o lo pedido, si el título no es legible en español) |

**Extensión de Opera (`browser-extension/`, `core/browser.py`):** se conecta al servidor local de Miku, le envía cada pestaña abierta (número, título, dirección, ventana, activa/fijada/suena) y los resultados visibles de una búsqueda (Google, YouTube, DuckDuckGo, Bing), y ejecuta las órdenes por número con la API `tabs`. Ese estado va en cada petición a Gemini (ver `core/state.py`). Instalación en `browser-extension/README.md`.

**Leer y buscar (no son herramientas propias):** en turnos de **texto**, la petición lleva también la herramienta integrada `url_context`: Google lee la página que le pases dentro de la misma petición (probado: resume python.org). Con `llm.web_search: true` va además `google_search`, pero **el plan gratuito responde 429 a toda petición que la lleve** (probado el 23-oct), así que viene apagada. No van en turnos de voz o con imagen: Gemini respondía 400. Si Google rechaza las integradas (400 o 429), se reintenta sin ellas y solo se apagan para la sesión si el reintento funciona; si también falla, era la cuota del modelo.

## Sistema — `tools/system.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `get_datetime` | — | Fecha y hora local |
| `get_system_status` | — | CPU %, RAM %, uso de GPU/VRAM (`pynvml`), espacio en disco |
| `lock_pc` | — | `LockWorkStation` |
| `shutdown_pc` 🔒 | `mode: shutdown \| restart \| sleep` | `shutdown /s /t 30` (con 30 s para cancelar), etc. |
| `copy_to_clipboard` | `text: str` | `Set-Clipboard` de PowerShell; el texto va por una variable de entorno, nunca en la línea de comandos |
| `read_clipboard` | — | `Get-Clipboard -Raw`, máx. 400 caracteres |

## Archivos — `tools/files.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `find_file` | `name: str` | Búsqueda difusa solo en `tools.file_search_roots`, máx. 3 niveles de profundidad y 10 resultados, con timeout de 3 s |
| `open_file` | `path: str` | Solo rutas devueltas por `find_file` en esta sesión |
| `open_folder` | `name: str` | Escritorio, Descargas, Documentos, Imágenes o rutas de las raíces configuradas |
| `create_text_file` | `name: str, content: str` | Solo en el Escritorio, solo el nombre (sin carpetas ni `..`), `.txt` si no es `.txt/.md/.csv/.log`. Modo `x`: **nunca sobrescribe** |
| `read_text_file` | `name: str` | Busca un `.txt/.md/.csv/.log` en las raíces y lee los primeros 600 caracteres |

No hay herramientas para borrar, mover ni renombrar archivos.

## Tiempo — `tools/timers.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `set_timer` | `minutes: float, label: str?` | Cuenta atrás ("5 minutos para el té"); al terminar: "¡Tu temporizador de el té ha terminado!" |
| `remind` | `text, minutes?, at?: "HH:MM", date?: "AAAA-MM-DD", every_minutes?` | Recordatorio en N minutos, a una hora o en una fecha ("el viernes a las 8": el modelo calcula la fecha desde la de hoy, que va en el prompt en español y AAAA-MM-DD). Se repite con `every_minutes` (1440 = cada día, 10080 = cada semana, 120 = cada 2 h): al sonar sigue con el mismo número a su siguiente hora. Sin fecha y ya pasada la hora: mañana; el minuto actual cuenta como ahora; una fecha pasada es un error. Avisa "¡Oye, recuerda: X!". `list_timers` y el estado del PC lo dicen hablado: "mañana a las 08:00", "todos los días a las 09:00" |
| `list_timers` / `cancel_timer` | `id?` | — |

**Avisos:** si Miku estaba oculta, aparece, lo dice y se vuelve a ocultar, sin abrir el micrófono. Si estaba conversando (respondió hace menos de `hide_after_seconds` y nadie la ocultó), lo dice y la conversación sigue. Si está hablando, espera a que termine.

**Persistentes:** cada temporizador se guarda con su hora de vencimiento absoluta en `cache/timers.json` al crearse, cancelarse o sonar. `restore_timers()` los reprograma al arrancar. Los que vencieron con Miku apagada hace menos de 6 h se anuncian a los 15 s de arrancar; los más antiguos se descartan. Cerrar el backend no los borra.

## Notas — `tools/notes.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `take_note` | `text: str` | Añade una línea `- [fecha] texto` a `notes.md` en Documentos (no repite la misma nota en 30 min) |
| `read_notes` | `last_n: int = 5` | Lee los **pendientes** (las notas no hechas), sin la fecha |
| `complete_note` | `text` | "Ya hice X": marca la nota con ✔ (`- ✔ [fecha] texto`); sigue en el archivo, pero ya no es pendiente. Busca por palabras enteras o comienzos ("subí lo del PR" → "subir el PR"), sin tildes. Si hay varias o ninguna, lo dice y lista los pendientes para que el modelo lo intente de nuevo |
| `delete_note` | `text` | Borra la línea (hecha o no), con la misma búsqueda |
| `open_notes` | — | Abre `notes.md` en el editor predeterminado |

Los pendientes van en el estado del PC de cada petición (los 8 más recientes).

"Apunta / anota / apúntame (que) X" y "qué pendientes tengo" van por el atajo local (0 peticiones).

## Memoria — `tools/memory.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `remember` | `fact: str` | Guarda un dato del usuario en `cache/memory.json` (máx. 50, sin duplicados, escritura atómica). Todos se añaden al prompt de cada petición |
| `forget` | `text: str` | Borra los datos que contienen el texto |

## Rutinas — `tools/routines.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `run_routine` | `name: str` | Ejecuta en local los pasos de `config.yaml → routines` (`{tool, args}`); salta las herramientas destructivas. "modo trabajo" o "activa el modo música" van por el atajo local (0 peticiones) |

## Escritura — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `type_text` | `text: str` | Escribe en la ventana activa con `keybd_event`. Máx. 500 caracteres, sin saltos de línea; se niega a escribir en consolas |

## Visión — `core/screen.py` (no es una herramienta)
Una herramienta no serviría, porque Gemini no ve su resultado. Si el texto de Whisper pregunta por la pantalla (`SCREEN_RE` en `llm.py`: "pantalla", "qué ves", "mira esto", "este error"…), se captura la pantalla principal y va como imagen PNG **en la misma petición** que el audio. Se captura con GDI vía `ctypes` y se codifica con `numpy` + `zlib`, sin Pillow: 1920×1080 en ~70 ms, ~0,5 MB. Nunca se captura si no se pregunta.

## Reglas de implementación
- Registro con decorador: `@tool(name, description, destructive=False)`. Los parámetros salen de la firma de la función; a partir de ella se generan las declaraciones para Gemini.
- Las descripciones en español, claras y cortas: Gemini decide con ellas.
- Timeout de 10 s por herramienta (`TOOL_TIMEOUT_S`); un error o un timeout devuelven `{"ok": false, "result": "<mensaje humano>"}` sin romper el pipeline.
- Confirmación 🔒 (`destructive=True`, hoy solo `shutdown_pc`): la primera llamada no ejecuta nada, guarda la acción y devuelve la pregunta, que Miku lee. Si el **siguiente mensaje del usuario** es un "sí" corto (en menos de 60 s), la acción guardada se ejecuta **en local, sin petición a Gemini**; el `confirmed=True` del LLM se ignora. Cualquier otra respuesta la cancela.
- Si Gemini dice que hizo algo ("guardé", "abrí", "anotado"…) sin pedir ninguna herramienta, Miku dice que no llegó a hacerlo en lugar de mentir (`CLAIMED_ACTION_RE`). No se aplica a respuestas que buscaron en Google.
- Loguear cada llamada a herramienta con sus parámetros.
