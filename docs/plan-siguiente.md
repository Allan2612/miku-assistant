# Plan siguiente (26-oct)

Lo del navegador funciona: pestañas por número, "cierra todas menos…", "la tercera opción" leída de la extensión y
correcciones en la misma pestaña. Este plan cubre lo que queda: lo que falla hoy, Windows como el navegador,
recordatorios/notas/memoria y la voz.

## Lo que dice el log de hoy (sesión 10:03–10:16)

| # | Qué pasó | Dónde | Causa |
|---|---|---|---|
| 1 | Tras anunciar un recordatorio, Miku abre el micrófono y escucha | 10:10:04, 10:16:17 | `handle_speak_done` abre el modo conversación tras **cualquier** frase, también los avisos de temporizador |
| 2 | Un recordatorio sonó encima de la despedida ("¡Con gusto!" y "¡Recordatorio!" a la vez) | 10:09:56–10:10:04 | El aviso espera el candado del pipeline, pero no a que termine el audio |
| 3 | "Nada, nada." gastó una petición y Miku respondió "¡De nada!" sin ocultarse | REQ #22 | La lista de despedidas tiene "nada", no la palabra repetida |
| 4 | Activaciones sin querer | 24-oct 10:55:15 (puntuación 0,988, no habló nadie) | Las falsas tienen puntuación **alta** y las reales a veces baja (0,355, 0,369, 0,371): subir el umbral no lo arregla |
| 5 | "Otra voz" | 16 veces en el log | Tras 10 min sin uso se descarga RVC; recargarlo tarda 11–53 s y mientras tanto habla la voz base de edge-tts (Dalia) |
| 6 | Cerrar 8 pestañas dio "Opera no respondió" aunque sí las cerró | 10:04:47 | La respuesta de la extensión llegó tarde o se perdió (espera fija de 6 s) |
| 7 | Recordatorios incoherentes | REQ #17, #20 | "En un minuto" → `set_reminder` a las 10:10; "recordatorio en 5 min" → `set_timer`, que anuncia "Tu **temporizador** de ir a bañarme". Dos herramientas para lo mismo |

Sin errores en lo demás: 22 peticiones, un 504 de Gemini que la cadena de respaldo resolvió sola.

## Fase A — Arreglos inmediatos ✅ (26-oct)

- **A1. Los avisos solo hablan**: tras un recordatorio, ni modo conversación ni micrófono; si Miku estaba oculta, se
  muestra, habla y se vuelve a ocultar. Si está hablando, el aviso espera a que termine el audio (no solo la respuesta).
- **A2. Frase para ocultarla sin petición**: ampliar las despedidas locales y aceptar palabras repetidas ("nada, nada",
  "ya, ya"). Frases nuevas: "ocúltate", "escóndete", "ya puedes irte", "eso era todo", "no era nada", "me equivoqué".
  Sin respuesta hablada si la frase es solo "ocúltate" (se oculta al instante).
- **A3. Cerrar pestañas**: que la extensión responda en cuanto Opera acepta la orden y, si la respuesta no llega,
  comprobar con el siguiente estado de pestañas si de verdad se cerraron antes de decir que falló.
- **A4. Un solo recordatorio**: una herramienta `remind(text, minutes | at)` que acepta "en N minutos" o una hora, y
  anuncia siempre "¡Oye, recuerda: tomar agua!". `set_timer` queda para temporizadores de verdad ("pon 5 minutos para el té").
  El atajo local también entiende "recuérdame en un minuto tomar agua" (sin "que").

Prueba: tests de pipeline (aviso sin micrófono), tabla de frases de despedida, test del recordatorio unificado.
Cuota: A2 ahorra peticiones; el resto no cambia.

## Fase B — Activaciones sin querer (wake word)

1. ✅ **Medir antes de tocar** (26-oct): cada activación guarda sus 2 s de audio en `cache/wake/`
   (`fecha_puntuación.wav`); el log dice si después hubo voz. Un par de días de uso normal dan los casos reales.
2. **Verificar con Whisper**: al detectar "Hey Miku", Whisper (ya cargado) transcribe esos 2 s mientras el micrófono
   ya escucha; si no se parece a "miku", cancela y la oculta antes de que hable. Coste: 0 peticiones. Whisper tarda
   ~1,5 s en frases cortas en este PC: hay que medir si cabe sin retrasar la activación real.
3. Si con eso no basta: reentrenar el modelo de openWakeWord con los audios falsos del paso 1 como negativos
   (los sonidos de tu PC: YouTube, Discord, juegos).

Criterio: un día de uso normal sin activaciones falsas, sin perder las reales de puntuación baja.

## Fase C — Siempre la misma voz ✅ (26-oct)

1. Medir en qué se van los 11–53 s de carga de RVC (importar torch, HuBERT, el modelo, la primera inferencia) y la
   VRAM que ocupa cargado.
2. Opciones, de menos a más cambio:
   - Subir `unload_after_minutes` (p. ej. 60) si la VRAM que ocupa es poca.
   - Dejar RVC listo en RAM y pasar solo el modelo a la GPU al activarla (segundos en vez de decenas).
   - Nunca hablar con la voz base: si RVC no está listo, esperar (con tope) en lugar de cambiar de voz.
3. Decidir con los números del paso 1.

Medido (26-oct): cargar los modelos tarda 3-5 s; lo lento es arrancar el proceso (importar torch, transformers y
faiss: 10 s con la caché del disco caliente, ~48 s en frío). Un proceso con todo importado no ocupa VRAM.
Hecho: tras descargar queda un worker en espera (solo RAM), la respuesta espera hasta 8 s a una carga en curso, y
el saludo de arranque espera a la voz de Miku.

Criterio: ninguna respuesta con la voz de Dalia tras el arranque.

## Fase D — Recordatorios, notas y memoria

Lo que hay hoy:
- Temporizadores y recordatorios persistentes (sobreviven a reinicios), máx. 20, solo "en N minutos" o "a las HH:MM"
  (hoy o mañana). Listar y cancelar por número.
- Notas: un archivo `notes.md`; apuntar, leer las últimas, abrirlo. No se pueden borrar ni marcar como hechas.
- Memoria: hasta 50 datos sueltos del usuario ("le encanta Frieren"), todos en cada petición. La conversación
  (últimos 10 turnos) **se pierde al reiniciar**.

Qué añadir:
- **Recordatorios con fecha y repetición**: "mañana a las 8", "el viernes", "todos los días a las 9", "cada 2 horas".
  Posponer: "recuérdamelo en 10 minutos" justo después del aviso. "¿Qué recordatorios tengo?" con hora hablada.
- **Pendientes de verdad**: lista con estado ("ya hice lo del PR" → la marca), borrar, "¿qué me falta?". Las notas
  libres siguen en `notes.md`.
- **Memoria de la conversación**: guardar los últimos turnos en disco para que un reinicio no la deje en blanco, y
  un resumen corto de días anteriores.
- **"¿Qué sabes de mí?"** y corregir datos ("ya no trabajo en X").
- Los pendientes y próximos recordatorios entran en el estado del PC, igual que las pestañas.

Criterio: tests por herramienta y una prueba en vivo de cada frase.

## Fase E — Windows como el navegador

La misma idea que con Opera: que Miku vea qué hay y actúe por número, sin adivinar.

- **Estado**: cada ventana visible con número, programa, título, si está minimizada/maximizada/activa y en qué monitor.
  Sustituye a "Apps abiertas" en el estado del PC.
- **Herramienta `windows(action, ids)`**: activar, minimizar, maximizar, restaurar, cerrar (con confirmación si hay
  algo sin guardar), mover a otro monitor, poner a la izquierda/derecha. API de Windows directa, sin simular teclas.
- Sustituye a `window_action`/`close_app` por nombre, que hoy adivinan la ventana por coincidencia parcial.
- Después, si hace falta: ajustes rápidos (brillo, modo oscuro, Bluetooth, no molestar) y leer/pulsar dentro de una
  app con UI Automation (lo que es la extensión para Opera, pero para cualquier programa). Lo segundo es grande:
  solo si hay casos concretos.

Criterio: "cierra todas las ventanas menos VS Code", "pon Discord en el otro monitor", "minimiza todo menos Spotify"
funcionan a la primera.

## Fase F — Voz más cercana a Miku (investigación)

Hoy: edge-tts (Dalia, +10 Hz) → RVC (`miku_mellow`, `index_rate` 0,25). Opciones a comparar con las mismas 10 frases:

1. **Afinar lo actual**: método de tono `rmvpe`, `protect`, `index_rate`, subir el tono base; probar el modelo
   `miku.pth` frente a `miku_mellow`. Barato: una tarde.
2. **Entrenar un RVC propio** con voz limpia de Miku (más datos y mejor f0 que el modelo descargado).
3. **Clonación de voz directa** (XTTS-v2, F5-TTS con ajuste en español, GPT-SoVITS): genera la voz sin pasar por
   Dalia, pero pide más VRAM y latencia. Medir en la RTX 3050 antes de decidir.

Criterio: escucha a ciegas tuya entre opciones; latencia y VRAM medidas para cada una.

## Orden

A (cambios pequeños) → B y C (medir primero, luego arreglar) → D → E → F. A y C son lo que más se nota hoy; E es lo más grande.
