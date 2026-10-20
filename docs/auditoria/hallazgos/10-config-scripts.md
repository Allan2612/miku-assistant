# Fase 10 · Configuración, dependencias y scripts

Avance: `requirements.txt` 18/18 · `package.json` 25/25 · `vite.config.ts` 38/38 · `tsconfig.json` 23/23 · `start.bat` 37/37 · `stop.bat` 20/20 · `install_autostart.bat` 23/23 · `uninstall_autostart.bat` 19/19 · `.gitignore` y `.env.example` 39/39 · **fase completa** (`package-lock.json` queda para `npm audit` en la fase 0)

Lo que está bien: `tsconfig.json` usa `strict` y avisa de variables sin usar; `.gitignore` excluye `.env`, modelos, cachés y binarios; `uninstall_autostart.bat` solo borra el acceso directo que creó el instalador.

### H-052 · `requirements.txt` no permite reinstalar el backend: faltan paquetes y nada está fijado

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/requirements.txt`
- **Categoría:** mantenibilidad

**Qué pasa:**

- Faltan dos dependencias que el código importa: `torch` (`rvc_worker.py:33`, `rmvpe.py:1`) y `openwakeword` (`wakeword.py:23`). `pip install -r requirements.txt` en un venv nuevo deja el backend sin poder arrancar.
- Todas las versiones son mínimas (`>=`), sin límite superior ni archivo de bloqueo. Una reinstalación dentro de unos meses puede traer versiones incompatibles: por ejemplo, websockets ya marca como obsoleta la API que usa `server.py` (H-021).
- El venv actual usa una versión *nightly* de PyTorch (`2.15.0.dev20260907+cu126`), que no se puede volver a instalar de forma fiable y puede tener errores.

**Propuesta:** generar un `requirements.lock` con `pip freeze` del venv que funciona, añadir `torch` (versión estable con CUDA 12.6, con su `--index-url` documentado en `setup.md`) y `openwakeword`, y fijar al menos la versión mayor de cada paquete.

### H-053 · `stop.bat` puede matarse a sí mismo antes de parar el backend, y mata procesos ajenos

- **Severidad:** Media
- **Estado:** confirmado por lectura (no se ejecutó, porque mata procesos)
- **Ubicación:** `stop.bat:13`, `:16`
- **Categoría:** error

**Qué pasa:** el filtro mata todo proceso cuya línea de comandos contenga `miku-assistant` o `-m core`:

- La propia línea de comandos de ese PowerShell contiene el texto `*miku-assistant*`, así que **coincide consigo mismo**. Y el `cmd.exe` que ejecuta `stop.bat` también coincide, porque su línea de comandos lleva la ruta del proyecto. Los procesos se recorren en el orden que devuelve WMI; si uno de los dos aparece antes que el backend, el script se mata y el backend y el worker de RVC siguen vivos, aunque el mensaje final nunca se llega a ver.
- También coincide con cualquier otro programa abierto con una ruta del proyecto en su línea de comandos: VS Code (`Code.exe "C:\...\miku-assistant"`), una terminal, otro Python… Todos se cierran con `-Force`, sin guardar.
- `taskkill /F /IM app.exe` mata cualquier proceso llamado `app.exe`, no solo Miku (el nombre del binario es genérico).

**Propuesta:** guardar los PID al arrancar (`start.bat` o el propio backend escribiendo `cache/core.pid`) y que `stop.bat` mate solo esos PID; o filtrar por la ruta exacta del ejecutable (`core\.venv\Scripts\pythonw.exe`) y excluir `$PID`. Mejor aún, un apagado ordenado por WebSocket (ver H-050). Renombrar el binario de Tauri a algo propio (`productName`/`name` en `Cargo.toml`).

### H-054 · Detalles de `start.bat`, `vite.config.ts` y el arranque automático

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `start.bat:15-19`, `app/vite.config.ts:69`, `:52-64`, `install_autostart.bat:12`
- **Categoría:** error / seguridad

**Qué pasa:**

- `start.bat` espera al puerto 8765 con `netstat | findstr 8765` (que también coincide con, p. ej., el puerto 18765), y si el puerto no aparece tras unos 20 s, lanza la app igualmente sin avisar. Si Miku ya estaba en marcha, arranca un segundo backend (que falla al abrir el puerto) y una segunda app con otro icono en la bandeja.
- El servidor de desarrollo de Vite escucha en `0.0.0.0` (`vite.config.ts:69`): durante `npm run dev` o `tauri dev`, cualquier equipo de la misma red puede descargar el código y la configuración embebida.
- Todo `config.yaml` se incrusta en el JavaScript compilado (`__APP_CONFIG__`). Hoy no contiene secretos (la API key está en `.env`), pero cualquier valor que se añada en el futuro acabará visible en el bundle.
- El arranque automático apunta a `start.bat`: en cada inicio de sesión aparece una ventana de consola.

**Propuesta:** comprobar el puerto con `findstr ":8765 "`, avisar si ya hay una instancia, usar `host: host || "127.0.0.1"` en Vite, pasar al frontend solo las claves que usa, y lanzar el arranque con `pythonw`/la app directamente (o un `.vbs` sin ventana).
