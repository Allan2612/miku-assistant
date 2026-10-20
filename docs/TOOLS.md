# Herramientas de control del PC

Lista **cerrada**. Gemini solo puede invocar estas funciones, mediante function calling. Cada una devuelve un dict `{ "ok": bool, "result": str }` corto, para que Gemini lo resuma hablando.

Leyenda: 🔒 = requiere confirmación del usuario antes de ejecutarse.

## Apps y ventanas — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `open_app` | `name: str` | 1) alias de `config.yaml → apps`; 2) búsqueda difusa en accesos directos del menú Inicio (`%ProgramData%` y `%AppData%\Microsoft\Windows\Start Menu`), cacheada al arrancar; 3) `os.startfile`. Si hay varias coincidencias, devuelve las opciones |
| `close_app` 🔒 | `name: str` | `psutil` → `terminate()` del proceso coincidente |
| `list_open_apps` | — | Ventanas visibles con título (`pywin32` o `pygetwindow`) |
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

## Escritura — `tools/apps.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `type_text` | `text: str` | Escribe en la ventana activa (`pyautogui.write` o `SendInput`). Máx. 500 caracteres |

## Visión (Fase 9) — `tools/vision.py`
| Función | Parámetros | Implementación |
|---|---|---|
| `look_at_screen` | `question: str` | Captura (`mss`), reduce a 1280 px de ancho y la envía a Gemini junto con la pregunta |

## Reglas de implementación
- Registro con decorador: `@tool(name, description, params, destructive=False)`. A partir de él se generan las declaraciones para Gemini y la ejecución.
- Las descripciones en español, claras y cortas: Gemini decide con ellas.
- Timeout de 5 s por herramienta; cualquier excepción devuelve `{"ok": false, "result": "<mensaje humano>"}` sin romper el pipeline.
- Confirmación 🔒: el backend envía `confirm_request`; Miku pregunta por voz y acepta "sí" o "no" por voz, o un botón en la burbuja. Si no hay respuesta en 10 s, cancela.
- Máximo 5 llamadas a herramientas por petición (evita bucles).
- Loguear cada llamada a herramienta con sus parámetros.
