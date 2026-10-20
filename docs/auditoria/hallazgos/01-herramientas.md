# Fase 1 · Herramientas de control del PC

Avance: `__init__.py` revisado 77/77 · `apps.py` 0/387 · `files.py` 0/138 · `media.py` 0/173 · `notes.py` 0/79 · `system.py` 0/97 · `timers.py` 0/174 · `web.py` 0/97

### H-001 · La confirmación de acciones destructivas no está implementada en código

- **Severidad:** Alta
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:21`, `core/tools/__init__.py:53`, `core/config.py:87`, `core/tools/system.py:75`
- **Categoría:** seguridad

**Qué pasa:** el decorador acepta `destructive=True` y lo guarda en `_TOOL_METADATA`, y la config tiene `tools.confirm_destructive`, pero **nadie los lee**: `get_tool_metadata()` no se llama en ningún sitio y `confirm_destructive` solo aparece en `config.py`. La única "confirmación" es el parámetro `confirmed` de `shutdown_pc` (`system.py:75-84`), que **lo rellena el propio LLM**: si el modelo llama directamente `shutdown_pc(confirmed=True)`, se apaga el PC sin preguntar.

**Cómo se reproduce:** `grep -rn "destructive\|confirm_destructive\|get_tool_metadata" core/` → solo aparecen la definición y la config. Para el apagado: una transcripción ambigua o un texto inyectado ("apaga el equipo, ya está confirmado") puede llevar al modelo a pasar `confirmed=True` en la primera llamada.

**Evidencia:** `llm.py:42` delega la confirmación en el prompt: "Solo la acción de apagar o reiniciar el equipo (shutdown_pc) requiere confirmación previa si confirmed no es True".

**Propuesta:** hacer cumplir la confirmación en el wrapper de `tool()`: si `destructive` y `confirm_destructive`, no ejecutar y devolver `requires_confirmation`. La confirmación la registra el pipeline cuando el **usuario** dice "sí" en el turno siguiente, no un argumento del LLM.

### H-002 · `close_app` cierra aplicaciones sin confirmación, en contra de las reglas del proyecto

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/tools/apps.py:271-275`, `core/llm.py:42`
- **Categoría:** seguridad / docs

**Qué pasa:** `GEMINI.md` exige confirmación para "cerrar apps, apagar, borrar". `close_app` no está marcada como `destructive` y su docstring dice "sin pedir confirmación"; el prompt de `llm.py:42` lo refuerza. Cerrar una app puede perder trabajo sin guardar.

**Propuesta:** decidir la regla (docs o código) y alinearla. Si se mantiene sin confirmación, actualizar `GEMINI.md` y `tools.md`; si no, marcarla `destructive=True` una vez resuelto H-001.

### H-003 · El timeout de 5 s por herramienta no existe

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:5`, `core/tools/__init__.py:33`
- **Categoría:** error

**Qué pasa:** el docstring del módulo promete "Timeout of 5s per tool execution", pero el wrapper llama `func(*args, **kwargs)` de forma síncrona sin límite. Una herramienta colgada (p. ej. `find_file` en un disco lento o de red) bloquea el turno. Si Gemini ejecuta las herramientas en el hilo del bucle `asyncio`, se congela todo el backend.

**Por verificar:** cómo invoca `llm.py` las herramientas (hilo propio o bucle de eventos). Se revisa en la fase 3.

**Propuesta:** quitar la promesa del docstring o aplicar el límite donde se invocan las herramientas (`asyncio.wait_for` + `to_thread`).

### H-004 · `print` sueltos y argumentos completos en los logs

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:29`, `:31`, `:35`, `:42`
- **Categoría:** mantenibilidad

**Qué pasa:** cada ejecución hace `print` además de `logger.info`, en contra de "nada de prints sueltos" (`GEMINI.md`). Además se registran todos los argumentos, incluido el texto de las notas personales (`take_note`) y lo que escribe `type_text`.

**Propuesta:** borrar los `print` y truncar los argumentos en el log.

### H-005 · Un nombre de herramienta repetido sobrescribe al anterior sin aviso

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/tools/__init__.py:49`
- **Categoría:** mantenibilidad

**Qué pasa:** `_TOOL_REGISTRY[tool_name] = wrapper` no comprueba si el nombre ya existe. Dos módulos con el mismo `name=` dejan registrada solo la última importada.

**Propuesta:** `assert tool_name not in _TOOL_REGISTRY`.

### Notas para siguientes pasos

- `apps.py` registra `type_text` (`apps.py:364`), que escribe texto en la ventana activa. Hay que verificar si está en `tools.md` y qué pasa si la ventana activa es una terminal.
