# Herramientas de control del PC

Lista **cerrada** (34). Gemini solo puede invocar estas funciones, mediante function calling. Cada una devuelve un dict `{ "ok": bool, "result": str }` corto.

**Una petición por turno.** Gemini pide las herramientas y escribe la frase de Miku en la **misma** respuesta. Las herramientas se ejecutan en local y su resultado **no** vuelve a Gemini (AFC desactivado). Por eso Miku lee el `result` tal cual, en lugar de su frase, en tres casos:
- cuando la herramienta falla;
- cuando pide confirmación;
- cuando es una herramienta que devuelve datos (`SPEAK_RESULT_TOOLS` en `llm.py`): `find_file`, `read_notes`, `get_datetime`, `get_system_status`, `list_timers`, `read_clipboard` y `read_text_file`.

Esos resultados se escriben para ser leídos en voz alta: sin viñetas, sin `#` y sin marcas de tiempo.

Leyenda: 🔒 = requiere confirmación del usuario antes de ejecutarse.

## Apps y ventanas — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `open_app` | `name: str` | 1) alias de `config.yaml → apps`; 2) búsqueda difusa en accesos directos del menú Inicio (`%ProgramData%` y `%AppData%\Microsoft\Windows\Start Menu`), cacheada al arrancar; 3) `os.startfile`. Si hay varias coincidencias, devuelve las opciones |
| `close_app` | `name: str` | `psutil`: solo procesos con el **nombre exacto** (o su alias); nunca procesos del sistema ni el propio Miku. `terminate()` y, si a los 3 s sigue vivo, `kill()`. Sin confirmación (decisión revisable, H-002) |
| `list_open_apps` | — | **Pendiente: no implementada** |
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
| `open_url` | `url: str` | Opera GX si está instalado; si no, el navegador predeterminado. Solo `http`/`https` |
| `web_search` | `query: str` | Abre Google con la búsqueda |
| `youtube_search` | `query: str` | Abre la búsqueda en YouTube |

**Buscar y leer (no son herramientas propias):** con `llm.web_search: true`, cada petición lleva también las herramientas integradas de Gemini `google_search` y `url_context`. Google las ejecuta **dentro de la misma petición** (combinación de herramientas de Gemini 3, `include_server_side_tool_invocations` y modo `VALIDATED`). Así Miku responde preguntas de actualidad o lee una página sin gastar una petición más. Si la API rechaza la combinación (400), se desactiva para esa sesión y se reintenta sin ella; una petición rechazada no gasta cuota.

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
| `set_timer` | `minutes: float, label: str?` | Tarea asyncio; al terminar, Miku aparece y avisa con voz |
| `set_reminder` | `time: "HH:MM", text: str` | Igual, a una hora concreta |
| `list_timers` / `cancel_timer` | `id?` | — |

**Persistentes:** cada temporizador se guarda con su hora de vencimiento absoluta en `cache/timers.json` al crearse, cancelarse o sonar. `restore_timers()` los reprograma al arrancar. Los que vencieron con Miku apagada hace menos de 6 h se anuncian a los 15 s de arrancar; los más antiguos se descartan. Cerrar el backend no los borra.

## Notas — `tools/notes.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `take_note` | `text: str` | Añade una línea con fecha a `notes.md` en Documentos |
| `read_notes` | `last_n: int = 3` | Devuelve las últimas notas, sin la fecha (se leen en voz alta) |
| `open_notes` | — | Abre `notes.md` en el editor predeterminado |

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
