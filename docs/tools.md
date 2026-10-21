# Herramientas de control del PC

Lista **cerrada**. Gemini solo puede invocar estas funciones, mediante function calling. Cada una devuelve un dict `{ "ok": bool, "result": str }` corto, para que Gemini lo resuma hablando.

Leyenda: 🔒 = requiere confirmación del usuario antes de ejecutarse.

## Apps y ventanas — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `open_app` | `name: str` | 1) alias de `config.yaml → apps`; 2) búsqueda difusa en accesos directos del menú Inicio (`%ProgramData%` y `%AppData%\Microsoft\Windows\Start Menu`), cacheada al arrancar; 3) `os.startfile`. Si hay varias coincidencias, devuelve las opciones |
| `close_app` | `name: str` | `psutil`: solo procesos con el **nombre exacto** (o su alias); nunca procesos del sistema ni el propio Miku. `terminate()` y, si a los 3 s sigue vivo, `kill()`. Sin confirmación (decisión revisable, H-002) |
| `list_open_apps` | — | **Pendiente: no implementada** |
| `focus_app` | `name: str` | Traer ventana al frente |
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
| `open_url` | `url: str` | `webbrowser.open`. Solo `http`/`https` |
| `web_search` | `query: str` | Abre Google con la búsqueda |
| `youtube_search` | `query: str` | Abre la búsqueda en YouTube |

## Sistema — `tools/system.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `get_datetime` | — | Fecha y hora local |
| `get_system_status` | — | CPU %, RAM %, uso de GPU/VRAM (`pynvml`), espacio en disco |
| `lock_pc` | — | `LockWorkStation` |
| `shutdown_pc` 🔒 | `mode: shutdown \| restart \| sleep` | `shutdown /s /t 30` (con 30 s para cancelar), etc. |

## Archivos — `tools/files.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `find_file` | `name: str` | Búsqueda difusa solo en `tools.file_search_roots`, máx. 3 niveles de profundidad y 10 resultados, con timeout de 3 s |
| `open_file` | `path: str` | Solo rutas devueltas por `find_file` en esta sesión |
| `open_folder` | `name: str` | Escritorio, Descargas, Documentos, Imágenes o rutas de las raíces configuradas |

No hay herramientas para borrar, mover ni renombrar archivos.

## Tiempo — `tools/timers.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `set_timer` | `minutes: float, label: str?` | Tarea asyncio; al terminar, Miku aparece y avisa con voz |
| `set_reminder` | `time: "HH:MM", text: str` | Igual, a una hora concreta (en memoria; persistencia en Fase 9) |
| `list_timers` / `cancel_timer` | `id?` | — |

## Notas — `tools/notes.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `take_note` | `text: str` | Añade una línea con fecha a `notes.md` en Documentos |
| `read_notes` | `last_n: int = 5` | Devuelve las últimas notas |
| `open_notes` | — | Abre `notes.md` en el editor predeterminado |

## Escritura — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `type_text` | `text: str` | Escribe en la ventana activa con `keybd_event`. Máx. 500 caracteres, sin saltos de línea; se niega a escribir en consolas |

## Visión (Fase 9) — `tools/vision.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `look_at_screen` | `question: str` | Captura (`mss`), reduce a 1280 px de ancho y la envía a Gemini junto con la pregunta |

## Reglas de implementación
- Registro con decorador: `@tool(name, description, destructive=False)`. Los parámetros salen de la firma de la función; a partir de ella se generan las declaraciones para Gemini.
- Las descripciones en español, claras y cortas: Gemini decide con ellas.
- Timeout de 10 s por herramienta (`TOOL_TIMEOUT_S`); un error o un timeout devuelven `{"ok": false, "result": "<mensaje humano>"}` sin romper el pipeline.
- Confirmación 🔒 (`destructive=True`, hoy solo `shutdown_pc`): la primera llamada no ejecuta nada, guarda la acción y devuelve la pregunta, que Miku lee. Solo si el **siguiente mensaje del usuario** es un "sí" corto (en menos de 60 s) se ejecuta la acción guardada; el `confirmed=True` del LLM se ignora. Cualquier otra respuesta la cancela. Todavía no hay botón en la burbuja ni mensajes `confirm_request`.
- Máximo 2 llamadas a herramientas por petición (`maximum_remote_calls` en `llm.py`, evita bucles).
- Loguear cada llamada a herramienta con sus parámetros.
