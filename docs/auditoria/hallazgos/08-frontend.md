# Fase 8 · Frontend (`app/src/`)

Avance: `main.ts` revisado 384/384 · `ui.ts` revisado 126/126 · `live2d.ts` 0/580 · `animations.ts` 0/219 · `clickthrough.ts` 0/99 · `styles.css` 0/225 · `index.html` 0/41 · `samples/index.html` 0/72

**XSS verificado:** el texto que viene del backend (subtítulos de Miku y del usuario) se inserta con `textContent` (`ui.ts:47`, `:52`). Los tres `innerHTML` (`ui.ts:24`, `:81`, `:104`) solo contienen cadenas fijas. No hay inyección de HTML por esta vía.

**Config del frontend:** `main.ts` usa `hotkey`, `window.*`, `live2d.model`, `live2d.scale` y `behavior.hide_after_seconds` de `config.yaml`, inyectados al compilar (`__APP_CONFIG__`). Cambiar estos valores exige recompilar la app.

### H-044 · Mostrar a Miku le quita el foco a la ventana del usuario y pierde órdenes durante las animaciones

- **Severidad:** Baja
- **Estado:** por-verificar (el efecto sobre `type_text`)
- **Ubicación:** `app/src/main.ts:184-185`, `:176`, `:209`, `:363`
- **Categoría:** error

**Qué pasa:**

- `showMiku` llama `setFocus()` cada vez que aparece (wake word, temporizador, saludo). Si el usuario estaba escribiendo en otra app, pierde el foco. Y si pide "escribe hola" por voz, la ventana activa al ejecutar `type_text` puede ser la propia Miku, no la app donde quería escribir.
- `showMiku` y `hideMiku` se ignoran si hay una animación en curso. Un `show` que llega durante la animación de desaparecer se pierde: el backend habla, pero Miku sigue oculta.
- La app se muestra siempre al arrancar (`:363`), además del saludo del backend.

**Propuesta:** no llamar `setFocus()` al mostrar (la ventana es *always on top* y no lo necesita), y encolar la última orden show/hide recibida durante una animación para aplicarla al terminar.

### Notas para siguientes pasos

- Fase 12: el roadmap marca como hecha la "caja de texto" de la fase 2, pero el frontend la quitó ("clean voice-only mode", `main.ts:370`, `ui.ts:4`).
