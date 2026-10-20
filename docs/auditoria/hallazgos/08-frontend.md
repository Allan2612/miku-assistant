# Fase 8 · Frontend (`app/src/`)

Avance: `main.ts` revisado 384/384 · `ui.ts` revisado 126/126 · `live2d.ts` revisado 580/580 · `animations.ts` 0/219 · `clickthrough.ts` 0/99 · `styles.css` 0/225 · `index.html` 0/41 · `samples/index.html` 0/72

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

### H-045 · Interrumpir a Miku deja un intervalo de 60 ms corriendo para siempre

- **Severidad:** Media
- **Estado:** confirmado
- **Ubicación:** `app/src/live2d.ts:551-563` frente a `:476-500`, `:511-519`
- **Categoría:** recursos / error

**Qué pasa:** `stopSpeaking()` pausa el audio, pero no llama a `cleanup()`. Un audio pausado no emite `ended`, así que esa limpieza nunca ocurre:

- el `setInterval` de *lip sync* (cada 60 ms) sigue vivo para siempre;
- la URL `blob:` del audio no se libera;
- la promesa de `speak()` no se resuelve nunca, así que el frontend no envía `speak_done` (el backend depende de su watchdog, H-031).

Pasa en cada interrupción (barge-in con el atajo, `toggleMiku`), cada vez que se oculta a Miku mientras habla (`hideMiku` llama `stopSpeaking`) y cada vez que llega un `speak` nuevo (`speak()` empieza con `stopSpeaking()`). Los intervalos se acumulan y siguen corriendo con Miku oculta, en contra de la regla "sin bucles activos con Miku oculta" y "nada por debajo de 100 ms salvo audio".

**Cómo verificar:** en las DevTools de la app, interrumpir a Miku varias veces y ocultarla; en la pestaña *Performance* se ven los temporizadores de 60 ms activos.

**Propuesta:** guardar la función `cleanup` del audio activo y llamarla desde `stopSpeaking()` (que la promesa se resuelva al interrumpir).

### H-046 · Detalles de `live2d.ts`

- **Severidad:** Baja
- **Estado:** confirmado (la parte de la marca de agua, por-verificar)
- **Ubicación:** `app/src/live2d.ts:170`, `:119`, `:244-254`, `:265-272`, `:434-435`
- **Categoría:** mantenibilidad / licencia

**Qué pasa:**

- `sanitizeParams` pone a 0 en cada frame el parámetro `Watermark` del modelo, entre otros. Si el modelo es la muestra oficial de Live2D (`miku_sample_t04`), hay que revisar en `downloads/live2d/` que sus términos de uso permitan ocultar la marca de agua.
- `live2d.scale` de la config se ignora si vale exactamente `0.25` (`:119`): se usa entonces el autoajuste. Es un valor mágico difícil de adivinar.
- El zoom con la rueda no tiene límites (se puede reducir a casi 0 y queda guardado en `localStorage`; al recargar solo se valida el máximo).
- Pulsar `R` con la ventana de Miku enfocada reinicia el encuadre; como `showMiku` le da el foco (H-044), una `r` tecleada justo cuando aparece lo resetea.
- El *hit-test* usa el rectángulo que envuelve al modelo (`getBounds()`), no la silueta: las zonas transparentes alrededor de Miku bloquean los clics al escritorio.

**Propuesta:** documentar o quitar el valor mágico de `scale`, acotar el zoom (p. ej. entre 0,5× y 1,35× del autoajuste) y revisar la licencia del modelo.

### Notas para siguientes pasos

- Fase 12: el roadmap marca como hecha la "caja de texto" de la fase 2, pero el frontend la quitó ("clean voice-only mode", `main.ts:370`, `ui.ts:4`).
