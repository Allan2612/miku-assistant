# Fase 9 · Shell de Tauri (`app/src-tauri/`)

Avance: `lib.rs` 85/85 · `main.rs` 6/6 · `build.rs` 3/3 · `Cargo.toml` 27/27 · `tauri.conf.json` 41/41 · `capabilities/default.json` 19/19 · **fase completa**

**Dato para H-019:** `tauri.conf.json` no define `app.windows[].useHttpsScheme`, así que en Windows la app se sirve desde `http://tauri.localhost`. Ese es el origen que debe permitir el servidor WebSocket.

### H-049 · El atajo global Ctrl+Alt+M no tiene permiso para registrarse

- **Severidad:** Media
- **Estado:** confirmado por lectura (falta probarlo con el ejecutable actual)
- **Ubicación:** `app/src-tauri/capabilities/default.json:17`, `app/src/main.ts:266-275`
- **Categoría:** error

**Qué pasa:** la capacidad solo concede `global-shortcut:default`. En la versión instalada del plugin (2.4.1), ese permiso por defecto está **vacío** a propósito ("No features are enabled by default… shortcuts can be inherently dangerous", `permissions/default.toml`). Las llamadas `unregisterAll()` y `register()` del frontend se rechazan por falta de permiso, el `catch` solo escribe un aviso en la consola, y el atajo global no funciona. Queda el atajo de respaldo de `main.ts:297-302`, que solo actúa si la ventana de Miku tiene el foco, y la wake word.

**Cómo verificar:** abrir la app compilada, pulsar Ctrl+Alt+M con otra ventana enfocada y mirar la consola de las DevTools ("Could not register global shortcut").

**Propuesta:** añadir a la capacidad `global-shortcut:allow-register` y `global-shortcut:allow-unregister-all` (solo esas).

### H-050 · "Salir" en la bandeja cierra la ventana, pero el backend sigue escuchando el micrófono

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `app/src-tauri/src/lib.rs:54-56`
- **Categoría:** recursos / seguridad

**Qué pasa:** la opción "Salir" hace `std::process::exit(0)`, que solo termina el proceso de Tauri. El backend de Python (`pythonw -m core`, lanzado aparte por `start.bat`) sigue vivo: la wake word mantiene el micrófono abierto, el servidor WebSocket sigue aceptando conexiones (con H-019, sigue expuesto a cualquier web) y el worker de RVC puede seguir en la GPU. El usuario cree que cerró Miku, pero no hay ninguna ventana que lo indique.

**Propuesta:** que "Salir" avise al backend para que se apague (un mensaje `{"type": "shutdown"}` por el WebSocket que active el `stop_event` de `__main__.py`), o que Tauri lance y controle el backend como proceso hijo (*sidecar*) para cerrarlo con la app.

### H-051 · Configuración de seguridad de Tauri más abierta de lo necesario

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `app/src-tauri/tauri.conf.json:9`, `:22`, `:25-27`, `app/src-tauri/capabilities/default.json:10-18`, `app/src-tauri/src/lib.rs:10`, `:19-23`
- **Categoría:** seguridad / mantenibilidad

**Qué pasa:**

- `"csp": null`: no hay *Content Security Policy*. Hoy no hay XSS (fase 8), pero sin CSP cualquier fallo futuro en el frontend tendría acceso total.
- `"withGlobalTauri": true` expone toda la API de Tauri en `window.__TAURI__`, aunque el frontend importa los módulos de `@tauri-apps/api` y no la necesita.
- El plugin `opener` se inicializa y tiene permiso `opener:default`, pero el frontend no lo usa en ningún sitio.
- Hay permisos de ventana sin uso aparente (`allow-set-size`, `allow-start-dragging`).
- `additionalBrowserArgs` desactiva SmartScreen (`msSmartScreenProtection`) dentro del WebView. Como solo carga contenido local, el riesgo es bajo, pero no aporta nada.
- `lib.rs` posiciona la ventana con tamaños fijos (420×620, margen 12) que duplican `config.yaml` y no tienen en cuenta la barra de tareas; el frontend la recoloca después (`main.ts:67-100`).

**Propuesta:** CSP mínima (`default-src 'self'; connect-src ws://127.0.0.1:8765; media-src 'self' blob: data:; img-src 'self' blob: data:`), `withGlobalTauri: false`, quitar el plugin `opener` y los permisos sin uso, y eliminar el posicionamiento duplicado de `lib.rs`.
