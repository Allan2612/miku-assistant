# Fase 2 · Superficie de red

Avance: `server.py` revisado 218/218 · `ws.ts` revisado 142/142 · **fase completa**

### H-019 · Cualquier página web puede controlar a Miku y, a través de ella, el PC

- **Severidad:** Crítica
- **Estado:** confirmado por lectura de código y de la librería (falta la prueba en vivo)
- **Ubicación:** `core/server.py:203`
- **Categoría:** seguridad

**Qué pasa:** `websockets.serve(self.handle_client, self.host, self.port)` no pasa `origins`. Con websockets 16.1.1 (la versión del venv), el valor por defecto es `origins=None`, que **acepta cualquier origen**. Escuchar en `127.0.0.1` no protege: el navegador del usuario está en la misma máquina, y los navegadores permiten que una página abra WebSockets a `localhost` desde cualquier dominio (no aplican CORS a WebSocket). No hay ningún token ni autenticación.

**Cómo se reproduce:** cualquier web que el usuario visite ejecuta:

```js
const ws = new WebSocket("ws://127.0.0.1:8765");
ws.onopen = () => ws.send(JSON.stringify({type: "text_input", text: "abre la aplicación powershell -c start-process calc"}));
```

El texto llega a `pipeline.handle_text_input` (`server.py:156`) → Gemini → `open_app` → ejecución de comandos (H-006). También puede usar `type_text`, `close_app`, `shutdown_pc(confirmed=True)` (H-001) o leer las notas con `read_notes`, porque `broadcast` envía las respuestas de Miku **a todos** los clientes conectados, incluido el atacante (`server.py:50-52`).

**Prueba en vivo pendiente:** con el backend arrancado, abrir un HTML local con el código de arriba y enviar un texto inocuo ("¿qué hora es?"). Si Miku responde, queda confirmado en ejecución.

**Dato de la fase 8:** el frontend actual es "solo voz" y **no envía nunca `text_input`** (`sendTextInput` no se llama en ningún sitio de `app/src`). Esa rama del servidor solo la usaría un atacante.

**Propuesta:** quitar o desactivar la rama `text_input` de `server.py` mientras no haya caja de texto, y además:
1. `websockets.serve(..., origins=[<origen de la app Tauri>])`. En Tauri v2 en Windows el origen es `http://tauri.localhost` (comprobarlo en la fase 9); en desarrollo, `http://localhost:1420`.
2. Un token aleatorio generado al arrancar, que `start.bat`/Tauri pasen al frontend y que el servidor exija en el primer mensaje.

### H-020 · `broadcast` puede fallar si un cliente se conecta o desconecta mientras envía

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `core/server.py:50-55`
- **Categoría:** error

**Qué pasa:** `broadcast` recorre `self.clients` con un `await` dentro del bucle. Mientras espera, otra corrutina (`handle_client`) puede hacer `add` o `discard` en ese mismo set, y Python lanza `RuntimeError: Set changed size during iteration`. Además, solo se captura `ConnectionClosed`; cualquier otra excepción corta el envío al resto de clientes. Esto ocurre justo cuando el frontend se reconecta en mitad de una respuesta.

**Propuesta:** iterar sobre una copia (`for client in list(self.clients)`), o usar `websockets.broadcast(self.clients, payload)`, que ya maneja esto.

### H-021 · Detalles de `server.py`

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `core/server.py:13`, `:156`, `:163`, `:60`
- **Categoría:** mantenibilidad / error

**Qué pasa:**
- `from websockets.server import WebSocketServerProtocol` es la API antigua (*legacy*), obsoleta en websockets 14+; con la 16 funciona solo por compatibilidad.
- `text_input` se procesa con `await` dentro del bucle de mensajes del cliente (`:156`): mientras Miku piensa y habla, los demás mensajes de ese cliente (`dismiss`, `speak_done`) esperan en cola.
- `asyncio.create_task(...)` en `:163` no guarda la referencia (la tarea puede ser recolectada y sus excepciones se pierden).
- No hay límite de longitud del texto: hasta 1 MiB (`max_size` por defecto) se envía tal cual a Gemini y se registra entero en el log (`:60`).

**Propuesta:** importar el tipo desde `websockets.asyncio.server`, procesar `text_input` en una tarea guardada, y limitar el texto (p. ej. 1000 caracteres).

### H-022 · El cliente reenvía mensajes viejos al reconectar y no valida lo que recibe

- **Severidad:** Baja
- **Estado:** confirmado
- **Ubicación:** `app/src/ws.ts:58-61`, `:103-112`, `:47`, `:66`
- **Categoría:** error

**Qué pasa:**
- Mientras el backend está caído, los mensajes se encolan (hasta 20) y se envían todos al reconectar. Un `activate` o un `text_input` de hace minutos se ejecuta de golpe cuando el backend vuelve.
- `connect()` crea un `WebSocket` nuevo sin cerrar el anterior; si se llama dos veces, quedan dos conexiones y el `onclose` de la vieja programa otra reconexión.
- Los mensajes entrantes se convierten con `as ServerMessage` sin validar `type` ni campos.
- El tipo `confirm_request` está declarado (`:14`), pero el servidor nunca lo envía: el flujo de confirmación de `tools.md` no existe (ver H-001).
- El backoff (×1,5 hasta 10 s, sin límite de intentos) es correcto y barato.

**Propuesta:** encolar solo mensajes que sigan teniendo sentido más tarde (o ninguno, salvo `ready`), cerrar el socket anterior en `connect()` y descartar mensajes con `type` desconocido.

### Resumen de la fase 2

3 hallazgos nuevos más el crítico H-019. **H-019 es el hallazgo más importante hasta ahora**: junto con H-006 convierte cualquier página web visitada en un posible control remoto del PC. Debería arreglarse antes que todo lo demás.
