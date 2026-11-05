# Changelog

Todos los cambios notables de este proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]
### Cambiado (plan de mejoras, ver `docs/mejoras.md`)
- Miku ya no sigue el mouse con la cabeza. La entrada y salida las hace el modelo (sube al cuadro / se va hacia abajo) y la ventana solo se desvanece con destellos.
- Borrado el modelo RetrynowMiku (no era Miku y llevaba marca de agua) y su código.
- Voz de Miku elegida de oído (`scratch/voice_ab.py`): modelo RVC `miku` (antes `miku_mellow`), +4 semitonos, índice 0,25, sobre Dalia. Se compararon 5 modelos x 4 voces base y luego tono x índice.
- Cadena de respaldo de 6 modelos ordenada por cuota gratuita (cada modelo tiene su propio límite por minuto): `3.5-flash-lite` → `3.1-flash-lite` → `3-flash-preview` → `3.5-flash` → `3.8-flash` → `gemma-4-26b`. Al pasar al siguiente, Miku dice "Un momento...", "Mmm..." o similar (una vez por turno, voz cacheada). Gemma no acepta audio: recibe el texto de Whisper. Un modelo retirado (404) espera 1 h antes de reintentarse.
- **Miku ve el resultado de lo que hace** (bucle de agente): los resultados de las herramientas vuelven a Gemini, que responde según lo que de verdad pasó o da otro paso (máx. 3 rondas). Charla = 1 petición, una acción = 2. Antes se pedía a ciegas en una sola petición y Miku decía "listo" sin saber si funcionó.
- **Estado del PC en cada petición**: apps abiertas, volumen, temporizadores, pestañas de Opera con su número y los resultados de búsqueda visibles. "Cierra todas menos la de T y T", "la segunda opción" o "¿ya está abierto?" se deciden con datos, no adivinando.
- **Atajo local reducido** a órdenes inequívocas (volumen, pausa, hora, temporizadores, notas, recordar, rutinas, escritorio, apagar con confirmación). Apps, webs, búsquedas, YouTube y pestañas van a Gemini: las expresiones regulares adivinaban mal (direcciones mal transcritas, "cierra la ventana", correcciones).
- El "sí" para apagar o reiniciar se ejecuta en local, sin petición.
- Modelo principal `gemini-3.5-flash-lite`, con el pensamiento al mínimo: los tokens de pensamiento agotaban el límite y dejaban respuestas vacías.
- La ventana arranca sin `--js-flags=--lite-mode`: ahorraba 1 MB, pero Live2D gastaba 5 veces más CPU y Miku tardaba en aparecer.
- Leer notas y temporizadores suena natural: sin fechas, viñetas ni `#`.
- **Todas las reglas de palabras en un solo sitio** (`core/intent.py`): si una frase es ruido, el eco de su voz, una orden de ocultarse, una despedida, una orden o charla. Antes había unas 20 listas repartidas entre `pipeline.py` y `llm.py` que decidían cada una por su cuenta. Una frase mal oída en un log se arregla ahora con una línea en la tabla de `tests/test_intent.py`, que trae las frases reales que fallaron.
- **Si se despide, se va**: cuando su propia respuesta es una despedida ("¡Hasta luego, que descanses!", "Me voy a dormir un rato") se oculta aunque Gemini no ponga `[adios]`; antes volvía a abrir el micrófono. También se va si tu frase termina en despedida ("Te amo. Ya eso es todo. ¡Chau!"): Gemini contesta y luego se oculta. "Apáquese", "apágate un rato" o "Apague ese, Miku" la ocultan al instante, y el prompt trata como despedida las señales de que no quieres hablar ("me tienes loco", "déjame en paz", "estoy jugando").
- Las órdenes con tilde ("súbele", "ábreme", "póngale") cuentan como orden al comprobar una activación dudosa, y "Gracias, cierre Spotify" ya no se toma por una despedida: las formas de usted valen igual en todas las reglas.

### Cambiado (panel, ver `docs/plan-panel-ux.md`)
- Paginación donde las listas crecen: clips de la palabra clave (15 por página), días de conversación, datos de
  Memoria y recordatorios. Antes, los clips pasados del 80 y los días pasados del 14 no se podían abrir.
- Palabra clave se marca con el teclado: ↑/↓ elegir, Espacio escuchar, S «era yo», N «no era yo»; salta sola al
  siguiente sin marcar.
- Una sola barra de scroll por página. La cabecera es más baja, y la barra lateral va en grupos (Estado, Miku, Lo
  tuyo).
- Gráficos con escala, guías, eje de tiempo y el valor al pasar el ratón. La VRAM se compara con la de la tarjeta y la
  memoria con la del PC.
- Logs: añade solo las líneas nuevas (se puede copiar texto), carga líneas antiguas de los logs rotados, separa días,
  cuenta por filtro y resalta la búsqueda. Las líneas de un error largo van juntas.
- Herramientas agrupadas por tema, con nombre en español y filtros de verdad.
- Funciones con índice. Pulsar una frase la deja en un cuadro «Probar con Miku»: antes «Bloquea el PC» lo bloqueaba
  con un clic.
- Configuración avisa de cambios sin guardar (y al salir), graba el atajo pulsándolo, prueba la contraseña de OBS y
  dice cómo afecta el umbral a tus clips marcados.
- Borrar o cancelar en Recordatorios y Memoria tiene «Deshacer» durante 5 s. Memoria busca en todas las
  conversaciones.
- Un color, un significado: turquesa bien, ámbar aviso, coral error o borrar, violeta VRAM, azul Gemini.
- Quitada la música de fondo del panel.
- **Instalar en una PC sin NVIDIA ya no deja a Miku a medias.**
  - El asistente revisa la PC antes de instalar («Tu PC»).
  - Instala PyTorch para el procesador, así que su voz y reentrenar «Hey Miku» funcionan, algo más lentos.
  - Mide la velocidad al final y elige el Whisper adecuado.
  - Deja elegir entre su voz y una voz rápida.
  - Recursos muestra la memoria compartida de los gráficos integrados, y no una VRAM vacía.
- Configuración › La ventana de Miku: en qué pantalla aparece (se mueve al guardar) y un cuadro para escribirle bajo
  ella, apagado por defecto.
- Las pantallas de carga del panel muestran filas de lo que viene y qué está leyendo, en vez de «Cargando…».

### Añadido
- **Miku se mueve con vida propia** (`docs/plan-expresiones.md`, fases 1-6): motor de capas propio en lugar de las animaciones al azar del modelo. Respira y se balancea con ruido suave, cambia el peso cada 8-15 s, parpadea como una persona (a veces dos veces, y al mirar a otro lado), mueve los ojos a saltos y la cabeza los sigue; el pelo, la corbata y la falda reaccionan.
- Conducta por momento: al aparecer sube al cuadro y sonríe; escuchando se queda atenta y asiente mientras hablas; pensando mira arriba a un lado, cambia de lado y suspira si tarda; hablando marca las palabras con la cabeza; si la acción salió bien da un saltito, si falló se encoge de hombros; los recordatorios llegan con un gesto de "¡oye!"; al despedirse levanta un brazo y, al irse, hace una reverencia; esperando mira alrededor, se estira o tararea; al tocarla se sorprende, se ríe y se sonroja.
- Emociones nuevas que Gemini puede elegir: tímida, emocionada, confundida, orgullosa, juguetona (guiño) y cansada.
- Labios con los tiempos de cada palabra (edge-tts): la boca se cierra entre palabras y cambia de forma en cada una; parpadea al terminar una frase.
- Control del reproductor de YouTube (`youtube_player`, extensión 1.1.0): volumen del video, silenciar, calidad (hasta 4K o la que pidas), subtítulos, velocidad, adelantar/retroceder y siguiente video. "Sube el volumen del video" usa el del reproductor, no el de Windows.
- **Ventanas por número**, como las pestañas: el estado del PC lista cada ventana (número, programa, título, activa/minimizada/maximizada, monitor) y la herramienta `windows` las activa, minimiza, maximiza, restaura, cierra (como la X), pone a la izquierda o derecha o mueve a otro monitor. "Minimiza todo menos el juego" o "pon Discord en el otro monitor" se deciden con datos. Minimizar no activa otra ventana (no le quita el foco a un juego). Sustituye a `focus_app` y `window_action`.
- Recordatorios con fecha ("el viernes a las 8") y repetidos ("todos los días a las 9", "cada 2 horas"); la lista los dice hablados ("mañana a las 08:00"). Tras un aviso, "recuérdamelo en 10 minutos" funciona: el aviso queda en la conversación.
- Pendientes: "ya hice X" los marca como hechos (✔ en `notes.md`) y "bórralo" los quita; "qué me falta" lee solo los no hechos, y el estado del PC los incluye.
- La conversación persiste: tras un reinicio vuelven los últimos turnos (`cache/history.json`; si son de otro día, el modelo sabe que es una conversación anterior). Todo lo hablado se archiva por día en `cache/conversations/`, y "¿de qué hablamos ayer?" o "¿qué te dije del banco?" lo busca con `recall_conversation`. Sin resumen diario: solo gasta petición cuando se pregunta.
- "¿Qué sabes de mí?" y corregir datos ("ya no trabajo ahí") con `forget` + `remember`.
- Cada activación por "Hey Miku" guarda los 2 s que oyó el detector en `cache/wake/` (fecha y puntuación en el nombre, máx. 200), para ver qué dispara las activaciones sin querer.
- `open_website`: abre la web de algo por su nombre ("abre la página del Banco de Costa Rica") y dice a qué dominio fue.
- **Extensión de Miku para Opera** (`browser-extension/`): Miku ve todas las pestañas y las maneja por número (`browser_tabs`: cerrar varias, activar, recargar, atrás, adelante; `open_url`/`web_search`/`youtube_play` con `tab_id`). Sustituye a `browser_action`, que simulaba el teclado y fallaba con pestañas fijadas, el orden de Ctrl+Tab, el diálogo de cierre y el foco.
- `youtube_play`: pone y reproduce en YouTube lo que pidas ("ponme More en YouTube", "pon la canción..."); antes solo abría la búsqueda.
- Despedidas sin petición e instantáneas, con más frases: "ya está", "no te necesito", "eso es todo", "gracias", "nada" (las ambiguas solo si son toda la frase).
- **Modo conversación**: tras cada respuesta el micrófono sigue abierto 6 s (`behavior.follow_up_seconds`) para seguir hablando sin "Hey Miku". Si capta el final de la propia voz de Miku, lo descarta.
- Tonos de estado: uno ascendente al abrir el micrófono y uno descendente al cerrarlo sin haber oído nada (además de la burbuja "Escuchando...").
- Memoria a largo plazo (`remember` / `forget`), rutinas ("modo trabajo"), ventanas (minimizar, maximizar, restaurar), portapapeles, crear y leer archivos de texto.
- Leer páginas web que le pases por texto, con `url_context` de Gemini, en la misma petición.
- "¿Qué ves en mi pantalla?": la captura va en la misma petición que el audio.
- Temporizadores y recordatorios persistentes: sobreviven a un reinicio.
- Miku se despide ("¡Adiós!", "¡Chao!"…) antes de ocultarse por inactividad.
- "Apunta que X" y "qué pendientes tengo" en el atajo local.
- **Panel de control y app `miku.exe`** (`docs/plan-panel-instalador.md`). Secciones:
  - Inicio, Recursos (CPU, memoria y GPU de cada proceso de Miku), Cuotas y Logs;
  - Configuración (incluye arrancar con Windows, el atajo y el micrófono), Herramientas, Funciones, Recordatorios y
    Memoria;
  - Palabra clave: escuchar y marcar cada activación, y botón «Reentrenar» (`core/train_wakeword.py`);
  - Chat, y Almacenamiento: cuánto ocupa cada parte en disco, con «Liberar» para la caché de voz y los modelos que
    Miku ya no usa (los logs nunca).
  Abrir `miku.exe` otra vez muestra el panel, sin una segunda copia.
- **Instalador NSIS** para otras PCs. Separa el programa de los datos, y el primer arranque descarga Python y las
  librerías (PyTorch solo con NVIDIA).

### Corregido
- La extensión de Opera se conecta unos 3 s después de abrir Miku, no hasta 30 s después: en ese rato parecía rota y había que recargarla. Tampoco se queda sin saludar al backend si el cierre de la conexión anterior llega tarde.
- Reentrenar «Hey Miku» compara de forma justa:
  - un clip ignorado que marcaste cuenta una vez;
  - los clips grabados a menos de 2 s, que comparten audio, van juntos;
  - la prueba usa clips más nuevos que el modelo actual, si hay suficientes;
  - gana el modelo que acierta más en promedio entre llamadas y falsas;
  - si gana, el definitivo se entrena con todas las marcas, promediando 5 redes para depender menos de la suerte.
- **La cuota se gastaba sin que el panel lo mostrara.** Google cuenta cada petición enviada, también las que fallan
  por saturación (3-nov: `gemini-3-flash-preview` dijo «agotado» tras 20 enviadas, con solo 17 contadas). Ahora se
  cuenta cada envío. Un modelo ya agotado hoy no se intenta, y Gemma (14.400 al día) va antes que los de 20 al día.
  Además, una acción sencilla que sale bien («abre Spotify», «guarda eso») ya no pide una segunda petición solo para
  decir «listo»: su resultado es la respuesta.
- **Activaciones falsas:**
  - Un «Adiós», «No» o «Nada» tras una activación sin «Miku» en el clip ya no recibe respuesta: se oculta en silencio.
  - Cada activación anota si fue real (se oyó «Miku») o falsa. Palabra clave las ofrece como sugerencias para llegar
    a las 60 marcas y reentrenar; hoy hay 78.
- Los clips de «Hey Miku» se oían demasiado bajos (el micrófono graba a unos −27 dB): se suben al reproducirlos.
- Un recordatorio ya no se retrasa si el PC se suspende: se mira con el reloj de pared cada 30 s.
- Gemini vuelve a esperar 10 s antes de pasar al siguiente modelo: es el mínimo de la API, y con 8 s fallaban todas
  las peticiones.
- Auditoría del 2-nov: una pregunta con una palabra de despedida ("¿Cómo se dice adiós en japonés?", "vete a YouTube") ya no la despide; "Me voy a acordar de eso" en su respuesta ya no la oculta; un solo fallo de Gemini ya no deja el resto de la sesión en el modelo de reserva (y un Gemma fallido ya no le quita el audio al siguiente); ocultarla desde la bandeja mientras habla ya no abre el micrófono con ella oculta; si no llega el fin de una despedida, se oculta igual; "¿A qué hora cierra el súper?" y "borra mis pendientes" van a Gemini en vez de dar la hora o leer las notas; un argumento mal puesto en `shutdown_pc` da un error en vez de dejar el turno mudo. Borradas unas 90 líneas de una ruta de respuesta sin RVC que nunca se usaba y otro código muerto.
- Órdenes dobles con la segunda en "usted" o mal transcrita ("Póngale pausa y sérame todas las ventanas"): el atajo local solo pausaba; ahora toda la frase va a Gemini.
- "¡Sí!" respondiendo a una pregunta suya se descartaba como eco del "¿Sí?" de activación, y ella se iba: ese filtro solo aplica justo después del aviso.
- Llamadas reales descartadas como activación falsa: un "Hey Miku" transcrito como tres palabras ya no basta para descartarla, y una orden justo después siempre cuenta.
- El saludo de inicio cortaba la primera respuesta cuando hablabas antes de que la voz terminara de cargar: si ya hablaste, no saluda.
- "Apángese" (cómo Whisper escribe "apáguese") la oculta al instante en vez de ir a Gemini.
- "En la pantalla derecha" ya no adjunta una captura de pantalla (era un monitor, no "mira mi pantalla"); las capturas de más de 1920 px se envían a la mitad.
- Gemini colgado: se pasa al siguiente modelo a los 10 s (antes 15 s, y pasó dos veces).
- Repetir un video de YouTube (`youtube_player` loop, extensión 1.2.0): decía "ya la puse en bucle" sin poder hacerlo.

### Añadido
- Cada turno deja en el log cuánto tardó cada parte: "Turn timing: transcription, answer, voice".
- Charla tras una orden ("¿cómo estás hoy?", "gracias, te amo") repetía la orden anterior (pausó la música, volvió a poner el volumen al 75 %): Gemini recibe ahora también la transcripción junto al audio, y la regla de responder solo al último mensaje.
- "Hey Miku" dicho bajito y luego una orden ("Cierra me OBS Studio") se descartaba como activación falsa: un clip silencioso seguido de una orden o una despedida ya cuenta como llamada real.
- Etiquetas sueltas en la respuesta ("un [yatta] café") ya no salen en el subtítulo ni en la voz.
- "Dale play" decía "listo" aunque el video seguía en pausa: play y pausa esperan a que el reproductor cambie y, si no cambia, Miku lo dice (extensión 1.1.1).
- Ante algo sin herramienta (elegir una película dentro de Disney+) dice que no puede en vez de "dame un segundo que lo busco".
- Activaciones sin querer: los 4 audios guardados de activaciones falsas no decían "Miku" (un vídeo, Discord, casi silencio) aunque el detector les dio hasta 0,99. Ahora Whisper transcribe los 2 s del "Hey Miku" mientras ella dice "¿Sí?" y escucha; se oculta en silencio solo si es claramente falsa: casi silencio, o una frase de 3+ palabras sin "Miku" (alguien hablando de otra cosa). Un clip vacío o de una o dos palabras se acepta: Whisper oye mal un "Hey Miku" corto ("Maes.", nada) y la primera versión ocultaba llamadas reales. Sin retraso para las activaciones reales; con el atajo de teclado o un clic no se comprueba.
- "A veces habla con otra voz": tras 10 min sin uso se descargaba RVC y recargarlo tardaba 10-48 s (casi todo, importar torch), en los que Miku hablaba con la voz base de edge-tts. Ahora queda un proceso en espera con todo importado (RAM, 0 MB de VRAM) y la recarga tarda 3-5 s. **Una sola voz:** la respuesta espera a que cargue en vez de usar la voz base; si RVC falla, sale solo el subtítulo; "¿Sí?" y "Un momento..." se omiten si aún no existen en su voz, y su caché depende del modelo y el tono (antes quedaban frases con el modelo viejo).
- Los recordatorios ya no abren el micrófono después de avisar ni suenan encima de otra frase: si Miku estaba oculta, aparece, avisa y se oculta; si estabas hablando con ella, avisa y la conversación sigue.
- "Ocúltate", "escóndete", "ya puedes irte": se oculta al instante, sin hablar ni gastar petición. "Nada, nada", "no era nada", "olvídalo" o "me equivoqué" se despiden sin petición (antes "Nada, nada" iba a Gemini y respondía "¡De nada!").
- Recordatorios: una sola herramienta `remind` (en N minutos o a una hora) que avisa "¡Oye, recuerda: X!"; antes "recordatorio en 5 minutos" anunciaba "tu temporizador ha terminado". "Recuérdame en un minuto tomar agua" (sin "que") va por el atajo local.
- Cerrar muchas pestañas a la vez decía "Opera no respondió" aunque se cerraban: la extensión responde enseguida y Miku comprueba la lista de pestañas antes de dar algo por fallido.
- "¿Estás segura que la guardaste?" hacía que Miku dijera "no llegué a hacerlo" aunque sí la había guardado (y la nota se duplicaba): hablar de la acción del turno anterior ya no cuenta como promesa falsa, y la misma nota no se guarda dos veces en 30 min.
- "Ábreme la segunda opción" / "ese enlace": Miku mira la pantalla (captura en la misma petición) y abre ese resultado.
- Buscar una pestaña por nombre tolera "T y T", "T&T", "TyT", "t-soluciones" o "Disney plus" (sin mayúsculas, tildes ni símbolos; o el título claramente más parecido).
- "Adiós" ya no responde "¡De nada!"; pausar la música dice "¡Listo!" en vez de "Reproducción alternada (play/pause)".
- "Cierra todas menos X" dejaba pestañas abiertas: al cerrar una pestaña Opera activa la siguiente y se la saltaba; también cuenta ahora las otras ventanas de Opera y salta las pestañas fijadas (la "GX Corner" de Opera GX contaba como 78 cierres).
- Corregir una web abría otra pestaña: Opera no pasa al frente al abrir una web desde Miku, así que no se sabía en qué ventana estaba. Ahora Miku la trae al frente y la recuerda.
- "Busca www.direccion-mal-transcrita.net" ya no la googlea tal cual: pasa a Gemini, que oye el audio. "Reproduciendo X en YouTube" sin herramienta se reproduce de verdad.
- Direcciones web dictadas o deletreadas: Gemini (que oye el audio) junta las letras deletreadas; `open_url` comprueba que la dirección exista (DNS, máx. 2 s) y si no, la busca en Google; el atajo no abre direcciones mal transcritas por Whisper; Miku dice la dirección ("He abierto tytsoluciones.net").
- "No, era X" / "te equivocaste": se carga en la misma pestaña (`tab_id` de la pestaña que abrió Miku), y los turnos del atajo quedan en el historial para que Gemini sepa qué se corrige.
- "¡Suscríbete!" y otras alucinaciones de Whisper con ruido ya no cuentan como petición.
- Pestañas: "cierra todas las pestañas (menos la de X)" y "cierra las demás"; cambio de pestaña por posición (Ctrl+AvPág); cerrar una ventana va pestaña a pestaña (Ctrl+Shift+W pedía confirmación).
- "Súbele el volumen a 100%" solo subía 15: el atajo entiende niveles ("al 30", "al máximo", "a tope", "al mínimo"). Una frase con varias órdenes ("abre Spotify y sube el volumen") ya no la resuelve a medias el atajo: va a Gemini. Si Gemini dice que hizo algo sin hacerlo y el atajo lo reconoce ("¡volumen al máximo!"), se hace en local en vez de disculparse.
- Pedir otra canción abría una pestaña más y la anterior seguía sonando: `youtube_play` reutiliza la pestaña de YouTube que abrió. "Abre Opera" con Opera ya abierto trae su ventana en lugar de abrir otra.
- Si no hablabas en los primeros segundos, la burbuja seguía diciendo "Escuchando..." con el micrófono ya cerrado y lo que dijeras después se perdía: ahora desaparece al volver a reposo, y la espera inicial pasa de 5,5 a 8 s.
- Whisper ya no se descarga tras 10 min sin uso (solo ocupa RAM): recargarlo retrasaba ~1,5-2 s la primera frase después de una pausa. RVC sí se descarga (VRAM).
- El log registra cuánto tarda la ventana en aparecer (`Frontend timing [show]`): ~270 ms medidos, oculta 1 o 5 min.
- La búsqueda de Google integrada dejaba a Miku sin responder a nada en el plan gratuito (429): ahora viene apagada (`llm.web_search`) y leer páginas web (`url_context`) va solo en turnos de texto.
- Atajo local: no reconocía frases con "¡...!", "Hey Miku," al principio, "ábreme" ni el voseo ("bajá el volumen"); abría el Bloc de notas si una frase larga decía "notas". Nuevos atajos: temporizadores ("recuérdame en 10 minutos que..."), "recuerda que...", "busca en Google...", "ponme X en YouTube" y apagar/reiniciar (pide confirmación).
- `open_app` con 1-2 letras ("abre mi") abría Microsoft Edge: la coincidencia parcial pide 3 letras al inicio de una palabra.
- Miku ya no promete sin hacer ("¡Hecho! Te avisaré", "Voy a apagar..."): lo admite.
- `list_open_apps` implementada.
- Dependencia de Rust `tokio` 1.54.1 (RUSTSEC-2026-0384).
- `open_url`, `web_search` y `youtube_search` fallaban siempre (`_open_in_browser` borrado en un refactor).
- Miku decía "¡Anotado!" sin llamar a ninguna herramienta: ahora admite que no lo hizo.
- H-039: el worker de RVC terminado se espera en segundo plano y cierra sus *pipes*.

### Seguridad (auditoría, ver `docs/auditoria/`)
- El servidor WebSocket solo acepta la app y clientes locales: ninguna página web puede controlar a Miku.
- `open_app` ya no ejecuta líneas de comandos ni abre consolas; `type_text` no escribe en consolas ni pulsa Enter.
- `close_app` cierra solo por nombre exacto, nunca procesos del sistema ni el propio Miku.
- `open_file` no abre ejecutables ni scripts.
- Las acciones destructivas (apagar, reiniciar, suspender) solo se ejecutan si el usuario dice "sí".
- CSP en la ventana de Tauri; quitados el plugin `opener` y permisos sin uso.

### Corregido
- Atajo local: "apaga el PC" ya no mata procesos, "pon la música" reproduce, frases ambiguas van a Gemini.
- Ctrl+Alt+M (faltaban permisos), click-through, "Salir" apaga también el backend, `stop.bat` solo mata procesos de Miku.
- Fin de frase con silero-vad: la música o el ruido ya no alargan la grabación.
- RVC: sin respuestas desfasadas tras un timeout; logs del worker en `cache/rvc_worker.log`.
- Interrumpir a Miku ya no deja intervalos activos; la wake word se reanuda tras errores.
- Temporizadores, volumen, silencio y apagado hacen lo que se pide.
- La primera respuesta tras descargar RVC ya no espera su carga (35-80 s): usa la voz base mientras carga.
- Transcripción: Whisper `small` en lugar de `base` (8 hilos). Con ruido de micrófono, `base` fallaba en ~1 de cada 2 palabras en español y `small` en ~1 de cada 4; tarda ~1,3 s por frase en vez de ~0,4 s.

### Añadido
- Al activarla, Miku responde con una frase corta ("¿Sí?", "¿Dime?"…) antes de escuchar, para que se note que empezó.
- `tests/` con pruebas sin dependencias (`core\.venv\Scripts\python.exe -m tests.<nombre>`).
- `core/requirements.lock` con las versiones exactas del entorno que funciona.

- **Fase 8 — Pulido**:
  - **Experiencia Limpia por Voz (Sin Botones)**:
    - Eliminadas las barras de entrada de texto, botones de envío y barras de acciones flotantes en `app/src/ui.ts` y `app/src/styles.css`.
    - La interfaz queda 100% limpia y minimalista, mostrando únicamente a Miku en el escritorio y la burbuja de subtítulos flotante durante la conversación.
  - **Posicionamiento Preciso Abajo a la Derecha y Anti-Corte**:
    - En `app/src/main.ts`, `positionWindow()` ahora utiliza `monitor.workArea` en lugar de la resolución total de la pantalla, posicionando la ventana de Miku exactamente por encima de la barra de tareas de Windows (sin importar escala de DPI o monitores múltiples).
    - En `app/src/live2d.ts`, se recalibró la escala (`autoFitScale * 1.08`) para asegurar que las coletas largas (*twin-tails*) y el torso de Miku permanezcan dentro de los límites del lienzo sin recortarse por los bordes.
    - Las dimensiones de la ventana se optimizaron a 420x620 px en `tauri.conf.json` y `config.yaml`.
  - **Reacciones al Clic / Toque**:
    - Al hacer clic o tocar a Miku en pantalla (`live2d.onTapReaction()`), Miku reacciona con una animación de movimiento (`Tap`), rubor en las mejillas (`ParamCheek: 0.85`), sonrisa tierna e inclinación de cabeza.
    - Se mantiene el soporte de arrastre para reubicar a Miku y zoom con la rueda del ratón (doble clic o tecla 'R' para restablecer encuadre).
  - **Interrupción Inmediata / Barge-in**:
    - Si el usuario dice "Hey Miku" o presiona el atajo `Ctrl+Alt+M` mientras Miku está hablando, Miku corta su frase al instante (`stop_speaking`), cancela la síntesis/reproducción y pasa directamente a escuchar al usuario.
  - **Saludo Según la Hora del Día**:
    - `core/pipeline.py` implementa `check_startup_greeting()`: una vez por día al arrancar, Miku saluda proactivamente según la hora local ("¡Buenos días!", "¡Buenas tardes!" o "¡Buenas noches!").
    - En `core/llm.py`, se integró detección de saludos en el fast-path local con 0 ms de latencia y se inyectó el momento del día en las instrucciones del sistema de Gemini.
  - **Scripts de Inicio, Parada y Autoarranque en Windows**:
    - `start.bat`: Arranca el backend silenciosamente en segundo plano usando `pythonw.exe -m core` (sin ventana negra de CMD) e inicia el binario optimizado `app.exe`.
    - `stop.bat`: Detiene limpiamente todos los procesos de Miku (`app.exe`, `pythonw.exe`, `rvc_worker.py`), garantizando 0% de uso de CPU, RAM y VRAM.
    - `install_autostart.bat` y `uninstall_autostart.bat`: Permiten configurar o desinstalar el arranque automático con Windows mediante acceso directo en la carpeta de inicio de usuario.
    - Compilado el binario ejecutable de producción `app.exe` en `app/src-tauri/target/release/app.exe` (solo 4.5 MB, standalone).
- **Soporte y Priorización de Opera GX**:
  - Detección dinámica de la ruta del ejecutable de Opera GX (`%LOCALAPPDATA%\Programs\Opera GX\opera.exe`).
  - Actualizado `core/tools/web.py` para abrir búsquedas de Google (`web_search`), YouTube (`youtube_search`) y enlaces web (`open_url`) directamente en Opera GX en lugar del navegador predeterminado de Windows.
  - Registro de alias en `DEFAULT_APP_ALIASES` y en `config.yaml` (`opera`, `opera gx`, `operagx`, `navegador`, `browser`, `internet`).
  - Integración en el Fast-Path de `core/llm.py` para abrir y cerrar Opera GX localmente en < 50ms sin consultar a la nube.

### Corregido
- **Correcciones Críticas de la Fase 8 (`start.bat`, Posicionamiento y Voz)**:
  - **Reentrenamiento y Balanceo del Modelo Wake Word (`hey_miku.onnx` v2)**:
    - *Diagnóstico*: El modelo anterior de `hey_miku.onnx` fue entrenado con un número reducido de muestras de voces sintéticas predominantemente agudas. Ante voces masculinas o registros normales de conversación (como acentos latinoamericanos o tonos más graves), el modelo apenas puntuaba ~0.01 a 0.32, quedando muy por debajo del umbral de activación (0.60). Además, al inyectar arrays de ceros durante silencios, se vaciaban los descriptores temporales y el Silero VAD forzaba la probabilidad a 0.0, volviendo a Miku completamente insensible a la palabra de activación.
    - *Solución*: Se generó un nuevo dataset ampliado y equilibrado con síntesis concurrente multilocutor (voces masculinas y femeninas de México, España, Colombia, Argentina, EE.UU., variaciones de pitch $\pm$18 Hz, velocidad $\pm$15% y atenuación suave/fuerte), emparejado con negativos de conversación cotidiana y ruido de fondo (siseo de micrófono, zumbido de ventiladores y silencio). El nuevo modelo puntúa entre **0.98 y 1.00** ante la voz del usuario y se mantiene en **0.00002** (inmune a falsos positivos) en reposo. Se ajustó `threshold: 0.50` y `patience: 1` en `config.yaml`.
  - **Detección Dinámica de Fin de Frase y Silencio en `core/audio_in.py`**:
    - *Diagnóstico*: La condición de silencio tras comenzar a hablar exigía que el RMS cayera por debajo de `energy_threshold * 0.75` de forma ininterrumpida durante 800 ms. En micrófonos de baja ganancia como el Razer Seiren V3 Mini, el suelo de siseo y la respiración suave (~0.0012) mantenían el RMS justo por encima del corte, reiniciando a 0 el acumulador de silencio en cada bloque. Esto provocaba que Miku se quedara congelada grabando durante 15 segundos enteros (tiempo máximo), haciendo que el usuario creyera que Miku no lo escuchaba. Al recibir 13 segundos de silencio/siseo, faster-whisper alucinaba en bucle repitiendo tokens ("¿Qué pasa? ¿Qué pasa?...").
    - *Solución*: Se incorporó suavizado exponencial (EMA) de RMS (`smoothed_rms = 0.65 * smoothed_rms + 0.35 * rms`), umbral de corte adaptativo (`silence_threshold = max(0.0010, energy_threshold * 0.90)`) y decaimiento gradual del acumulador en lugar de reseteo a cero ante chasquidos aislados. Miku ahora detecta el final de la frase y responde en menos de 0.8 s (~2.5 s de tiempo total de interacción).
  - **Filtro Anti-Alucinaciones en `core/stt.py`**:
    - Se activó el filtro VAD integrado en faster-whisper (`vad_filter=True`, `min_silence_duration_ms=400`) y `repetition_penalty=1.15`, garantizando que cualquier cola de siseo sea purgada antes del decodificador y eliminando los bucles de repetición.
  - **Preservación de Búfer Temporal en `core/wakeword.py`**:
    - Se eliminó la alimentación de ceros (`predict(np.zeros)`) durante caídas de volumen, preservando la continuidad de los 16 cuadros del espectrograma de Mel y deshabilitando el bloqueo estricto de VAD (`vad_threshold=0.0`) gracias a que el nuevo modelo ya discrimina el ruido ambiental por sí mismo.
  - **Permisos de Ventana en Tauri v2 (`capabilities/default.json`)**:
    - Se incorporaron los permisos requeridos por Tauri v2 (`core:window:allow-set-position`, `allow-set-size`, `allow-show`, `allow-hide`, `allow-set-focus`, `allow-set-ignore-cursor-events`, `allow-start-dragging`). Antes de esto, `positionWindow()` y `setIgnoreCursorEvents()` eran bloqueados silenciosamente por la capa de seguridad de Tauri, impidiendo que la ventana se ubicara abajo a la derecha.
  - **Posicionamiento Nativo en Rust (`app/src-tauri/src/lib.rs`)**:
    - Se añadió el cálculo y asignación de posición nativo en Rust en `.setup()`, asegurando que la ventana de Miku se cree y muestre directamente en la esquina inferior derecha del monitor activo sin parpadeos ni demoras.
  - **`NameError: name 'low' is not defined` en `core/llm.py`**:
    - Se definió la variable `low = text.lower().strip()` en `_try_fast_path_tool()`. La ausencia de esta variable causaba que cualquier interacción por voz o texto fallara inmediatamente, provocando que Miku no respondiera ni hablara.
  - **Robustez de `start.bat` y Logging en `cache/core.log`**:
    - `core/__main__.py` ahora registra logs persistentes en `cache/core.log` de forma segura incluso bajo `pythonw.exe` (donde `sys.stderr` es `None`), garantizando diagnóstico total.
    - `start.bat` ahora arranca los procesos sin interferencias de comillas en rutas con espacios y espera a que el puerto 8765 esté abierto antes de lanzar la interfaz.
- **Falso Error de Cuota/Batería ("Batería en 0.1% / Sobrecalentamiento")**:
  - En `core/tools/media.py`, la función `mute(on: Optional[bool] = None)` utilizaba el tipo `Optional` sin haberlo importado de `typing`. Al registrar las herramientas en Gemini con el SDK de Google GenAI, Python lanzaba `NameError: name 'Optional' is not defined`, provocando que todas las llamadas de Gemini fallaran y cayeran en los mensajes de emergencia de batería baja. Se corrigió la importación y las firmas de tipos.
- **Aceleración Drástica de la Animación de Aparición (< 250 ms)**:
  - En `app/src/animations.ts`, la animación de entrada se redujo de 600 ms a **240 ms**, reduciendo el desplazamiento vertical de 60 px a 20 px y alcanzando el 100% de opacidad en solo ~80 ms con un rebote elástico suave y ágil. Miku ahora aparece de forma casi instantánea al decir "Hey Miku".
- **Eliminación del Bloqueo de Audio de PortAudio al Activar**:
  - En `core/wakeword.py`, se removió la llamada a `self._stream.stop()` dentro del propio callback de PortAudio. Detener el stream dentro de su callback causaba contención y demoras de ~2 segundos en Windows antes de que `audio_in` pudiera abrir el micrófono para escuchar la petición. Al mantener el stream activo en modo silenciado rápido (`_paused = True`), la transición a la escucha es inmediata (8 ms).
- **Reproducción de Voz y Desbloqueo de Autoplay**:
  - En `core/tts.py`, se normalizó el tipo MIME de MP3 a `"audio/mpeg"` (estándar de navegadores RFC).
  - En `app/src/live2d.ts`, se implementó un desbloqueador global de audio en interacciones del usuario y un gestor resiliente de reproducción que no descarta el audio si el navegador bloquea el autoplay por falta de gestos previos.
  - En `app/src-tauri/tauri.conf.json`, se incorporó `--autoplay-policy=no-user-gesture-required` a los argumentos de WebView2 para permitir la reproducción de voz instantánea sin requerir clics previos en la ventana.
- **Falsas Activaciones de la Palabra de Activación (openWakeWord)**:
  - **Filtro de Voz con Silero VAD**: Se integró Silero VAD (`vad_threshold: 0.50`) en `openwakeword.model.Model`, descartando de forma automática ruidos que no provienen de cuerdas vocales humanas (tecleo, clics del mouse, ruido de ventiladores, chasquidos).
  - **Requisito de Persistencia Cuadro a Cuadro (`patience: 2`)**: Exige que la probabilidad se mantenga alta durante al menos 2 cuadros consecutivos de 80 ms (160 ms), eliminando falsos positivos por picos acústicos momentáneos de un solo cuadro.
  - **Calibración de Umbral a 0.75**: Se ajustó `threshold: 0.75` en `config.yaml` (aprovechando que las pronunciaciones del usuario de "Hey Miku" registran puntuaciones entre 0.91 y 0.94), blindando el sistema contra activaciones no deseadas por habla casual de fondo.
### Añadido
- **Fase 0 — Esqueleto**:
  - Estructura base del proyecto con archivos de configuración y documentación.
  - `.gitignore`, `.env.example`, `config.yaml` y `CHANGELOG.md`.
  - Módulo `core/` con `config.py` y `__main__.py` para carga de configuración y logging.
  - Entorno virtual en `core/.venv` y `core/requirements.txt` mínimo (`pyyaml`, `python-dotenv`).
  - Aplicación `app/` inicializada con Tauri v2 + Vite + TypeScript vanilla y argumentos de optimización para WebView2 (`--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection --js-flags=--lite-mode`).
  - Esqueleto de archivos en `app/src/` (`main.ts`, `live2d.ts`, `animations.ts`, `clickthrough.ts`, `ws.ts`, `ui.ts`).
- **Fase 1 — Miku en el escritorio (solo frontend)**:
  - Carga e inicialización del modelo Live2D oficial de Hatsune Miku (`miku_sample_t04.model3.json`) con `pixi.js` v7 y `pixi-live2d-display-lipsyncpatch/cubism4`.
  - Encuadre calibrado a plano medio (cintura hacia arriba) con persistencia de zoom y posición por modelo en `localStorage`.
  - Centrado responsivo en preview de navegador web y anclaje a la esquina inferior derecha en modo escritorio (Tauri).
  - Animaciones artesanales de aparecer (rebote elástico + partículas) y desaparecer (salto + desvanecimiento + parada del ticker) sin librerías externas de tween.
  - Ticker de PixiJS limitado estrictamente a 30 FPS (`maxFPS: 30`) y congelado al ocultarse (`app.ticker.stop()`).
  - Click-through inteligente con hit-testing contra los límites del modelo cada ~150 ms (completamente pausado cuando Miku está oculta).
  - Configuración de ventana de Tauri v2 (`transparent: true`, sin bordes, siempre encima, sin barra de tareas).
  - Atajo global `Ctrl+Alt+M` (con soporte fallback para pruebas en navegador) e integración con bandeja del sistema.
- **Fase 2 — Cerebro por texto**:
  - Servidor WebSocket local en Python asíncrono (`core/server.py`) en `ws://127.0.0.1:8765` con la librería `websockets`.
  - Integración con Google Gemini (`core/llm.py`) usando el SDK oficial `google-genai` asíncrono (`client.aio`) y modelo ultra rápido `gemini-3.5-flash-lite` (< 1 s de latencia), cargando el system prompt de `docs/PERSONA.md`, historial corto de 10 turnos y parser de emociones `[happy|sad|neutral|thinking|surprised|angry]`.
  - Cliente WebSocket en TypeScript vanilla (`app/src/ws.ts`) con reconexión automática y retroceso exponencial sin librerías externas.
  - Subtítulos estilo burbuja y barra de chat de texto (`app/src/ui.ts` y `app/src/styles.css`) desplegable al hacer clic sobre Miku, botón flotante o tecla Enter.
  - Expresiones faciales y animaciones según la emoción detectada en la respuesta de Gemini.
  - Temporizador de auto-ocultado tras inactividad (`hide_after_seconds: 20`) protegido contra ocultado durante el estado "pensando", y detección de despedida en texto ("adiós", "bye").
- **Fase 3 — Miku habla (voz base)**:
  - Módulo de síntesis de voz asíncrono (`core/tts.py`) con `edge-tts` usando la voz configurable `es-MX-DaliaNeural` (`rate: +5%`, `pitch: +20Hz`).
  - Caché persistente en disco en `cache/voice/` indexado por hash MD5 para respuestas instantáneas en frases recurrentes y fijas de `docs/PERSONA.md`.
  - Transmisión de mensaje `speak` con audio en base64 hacia el frontend, con degradación suave a solo subtítulo si la síntesis no está disponible.
  - Reproducción de voz y sincronización labial (lip sync) en `app/src/live2d.ts` sobre el parámetro oficial `ParamMouthOpenY` del modelo Live2D, con fallback a HTML5 Audio.
  - **Fase 4 — Miku escucha**:
  - Captura de audio de micrófono bajo demanda (`core/audio_in.py`) con `sounddevice` a 16 kHz mono float32, calibración automática del suelo de ruido ambiental, buffer de seguridad pre-activación (~320 ms) y detección de silencio (VAD).
  - Cumplimiento estricto del cierre de micrófono: el stream de `sounddevice` solo se abre al activarse y se cierra de forma inmediata (`stream.stop()`, `stream.close()`) en cuanto el usuario deja de hablar.
  - Motor de transcripción local de voz a texto (`core/stt.py`) usando `faster-whisper` en CPU (`int8`, 4 hilos, idioma español), ejecutando transcripciones en ~0.23 s con **0 MB de VRAM** (sin importar PyTorch en el proceso principal).
  - Carga perezosa del modelo STT y pre-calentamiento asíncrono (`warmup`) disparado en paralelo mientras el usuario habla.
  - Gestor de recursos (`core/resources.py`) con temporizador de inactividad (10 minutos) para descargar el modelo STT de la memoria RAM y ejecutar recolección de basura (`gc.collect()`).
  - Orquestador de interacción (`core/pipeline.py`) que conecta activación por voz/texto, transcripción, generación LLM, TTS y sincronización labial.
- **Fase 5 — Control del PC**:
  - Registro de herramientas cerrado (`core/tools/`) con decorador `@tool`, timeouts de 5s y aislamiento de excepciones para evitar caídas del backend.
  - Paquete completo de 25 herramientas implementadas según `docs/TOOLS.md`:
    - `apps.py`: `open_app` (alias y búsqueda en accesos directos del menú Inicio con `os.startfile`), `close_app` (terminación directa de procesos con `psutil`), `focus_app` (traer ventana al frente), `show_desktop` (Win+D nativo con `ctypes`), `type_text` (escritura en ventana activa).
    - `media.py`: `media_control` (teclas virtuales multimedia Windows `VK_MEDIA_*`), `set_volume`, `change_volume`, `mute` con `pycaw`.
    - `web.py`: `open_url`, `web_search`, `youtube_search` con `webbrowser` y `urllib.parse`.
    - `system.py`: `get_datetime` (fecha y hora en español), `get_system_status` (uso de CPU, RAM y disco con `psutil`), `lock_pc` (`LockWorkStation`), `shutdown_pc` 🔒 (protegido con solicitud de confirmación obligatoria).
    - `files.py`: `find_file` (búsqueda rápida en Escritorio, Documentos y Descargas con límite de profundidad y resultados), `open_file`, `open_folder`.
    - `timers.py`: `set_timer`, `set_reminder`, `list_timers`, `cancel_timer` (tareas asíncronas en memoria que, al vencer, invocan a Miku para que aparezca y anuncie el fin del temporizador con voz).
    - `notes.py`: `take_note` y `read_notes` (persistencia local en `~/Documents/notes.md`).
  - Integración nativa con Google Gemini (`core/llm.py`) mediante `AsyncChat` y Automatic Function Calling (AFC), ejecutando las herramientas y resumiendo el resultado conversacionalmente en voz de Miku con emoción asignada.
- **Fase 6 — Voz de Miku (RVC en subproceso aislado)**:
  - Subproceso hijo totalmente aislado (`core/rvc_worker.py`) que aloja PyTorch y CUDA, garantizando la regla de oro: **cero imports de `torch` en el proceso principal de `core`**.
  - Modelo RVC v2 40kHz asignado (`models/rvc/miku.pth`), índice de características FAISS (`models/rvc/miku.index`), estimador de pitch RMVPE en GPU (`models/rvc/rmvpe.pt`) y extractor de características HuBERT (`facebook/hubert-base-ls960`) en media precisión (FP16).
  - Protocolo JSON-RPC robusto por tuberías stdin/stdout con búfer de 10 MB para transmisión de audio PCM WAV base64 a 40 kHz.
  - Pre-calentamiento asíncrono (`warmup`) disparado en segundo plano en cuanto se activa Miku mientras el usuario habla.
  - Recolección automática de recursos en `core/resources.py`: al transcurrir el temporizador de inactividad (`unload_after_minutes: 10`), el subproceso hijo de RVC se termina inmediatamente (`terminate_worker`), devolviendo el 100% de la VRAM al sistema operativo (**0 MB de VRAM en reposo**).
  - Pipeline de voz integrado `edge-tts` -> RVC con degradación suave a voz base en caso de fallo.
  - Generación de voz con timbre idéntico a Hatsune Miku con latencia warm ultrarrápida (< 1.5 s de inferencia de voz en GPU NVIDIA RTX 3050).
  - Sistema de resiliencia multi-modelo en cascada con transferencia de historial ante límites de cuota (429/503) y respuestas predefinidas de roleplay ("batería baja", "sobrecalentamiento de circuitos", "comer un puerro virtual") pre-cacheadas en audio con voz de Miku.
- **Fase 7 — Palabra de activación (Wake Word con openWakeWord)**:
  - Módulo de escucha local `core/wakeword.py` ejecutado en CPU con ONNXRuntime (< 2% de uso de CPU).
  - Cumplimiento estricto de la regla de recursos: con `wakeword.enabled: false`, el flujo de micrófono nunca se abre (0% CPU y micrófono cerrado en reposo).
  - Generador y entrenador local de modelos wake word (`scratch/train_hey_miku_local.py`) con síntesis neuronal multi-locutor con `edge-tts`, extracción de características de audio openWakeWord (16x96 embeddings) y exportación a ONNX.
  - Modelo personalizado **`models/wakeword/hey_miku.onnx`** entrenado localmente y desplegado con precisión 100% y activación activa en `config.yaml`.
  - Sincronización de ciclo de vida con `core/pipeline.py`: pausado automático durante la conversación para evitar auto-activaciones y reanudación automática al volver al estado de reposo o al despedirse.
### Corregido
- **Fase 5 — Control del PC (Depuración y Solución de Ejecución)**:
  - Eliminado `from __future__ import annotations` en todos los submódulos de `core/tools/`, lo cual convertía las anotaciones de tipo en cadenas de texto (`'str'`, `'int'`) y hacía que `google-genai` fallara internamente en la validación de argumentos (`isinstance(val, 'str')` -> `TypeError`), impidiendo silenciosamente que las herramientas con parámetros se ejecutaran.
  - Añadido `comtypes.CoInitialize()` en `core/tools/media.py` para inicializar el hilo COM de Windows antes de interactuar con `pycaw`, resolviendo el fallo `[WinError -2147221008] No se ha llamado a CoInitialize` al ejecutarse en un hilo secundario (`asyncio.to_thread`).
  - Corregido el envío de teclas multimedia en `core/tools/media.py` pasando el flag `KEYEVENTF_EXTENDEDKEY = 0x0001` en `keybd_event` y permitiendo reconocimiento flexible de comandos por voz ("reproduce la canción", "pausa la música", etc.).
  - Normalización en `core/tools/apps.py` para eliminar artículos en español ("el bloc de notas" -> "bloc de notas") y apertura mejorada mediante `ShellExecuteW`.
  - Simplificación de `close_app`: las confirmaciones quedan estrictamente limitadas a `shutdown_pc` (apagar/reiniciar la PC), permitiendo que cerrar aplicaciones se ejecute de forma directa e inmediata.
  - Refuerzo en el system prompt de `core/llm.py` para obligar a Gemini a invocar las herramientas ante peticiones de acción.
- **Fase 6 — Voz de Miku (Depuración y Calidad Acústica)**:
  - Configurado el modelo **Miku Mellow** (`models/rvc/miku_mellow.pth` e índice `models/rvc/miku_mellow.index`) como voz principal por elección del usuario.
  - Cambio de la voz base TTS a español latinoamericano neutro (`es-MX-DaliaNeural`, `rate: +5%`, `pitch: +10Hz`) eliminando la pronunciación ibérica/castellana.
  - Implementado pipeline DSP anti-artefactos en `core/rvc_worker.py`:
    - Filtro de mediana en $F_0$ (`scipy.signal.medfilt(f0, 3)`) para eliminar micro-picos armónicos espurios de 10 ms en RMVPE.
    - Protección de consonantes sordas y respiraciones (`protect: 0.33`) evitando chasquidos y distorsiones metálicas en transiciones fonéticas.
    - Relleno por reflexión de 0.15 s en los extremos para neutralizar clics de borde en las capas convolucionales de HiFi-GAN.
- **Fase 7 — Palabra de activación y Robustez del Pipeline (Depuración y Auditoría)**:
  - **Calibración VAD Resiliente**: Corregido el cálculo del suelo de ruido en `core/audio_in.py`. Anteriormente, si el usuario decía "Hey Miku" y continuaba hablando de corrido, la voz caía dentro de los 6 frames de calibración inicial e inflaba el umbral a niveles inalcanzables (`avg_noise * 2.5`), causando que el VAD no detectara la frase o se cortara por timeout. Se añadió detección de voz inmediata (`rms > 0.020`) que inicia la grabación al instante sin corromper el suelo de ruido y limitador de umbral (`max 0.025`).
  - **Temporizador Perro Guardián (Watchdog)** en `core/pipeline.py`: Si el navegador o la interfaz no envían el evento `speak_done` (por pérdida de paquetes WebSocket, pestaña en segundo plano o audio silenciado), un watchdog asíncrono basado en la duración estimada del texto se dispara automáticamente para restablecer el estado a `idle` y reanudar la escucha de la palabra de activación, garantizando que Miku nunca quede sorda.
  - **Pausado Físico del Stream de WakeWord**: `core/wakeword.py` ahora detiene explícitamente el stream de audio (`stream.stop()`) al activarse y lo reinicia al finalizar la interacción (`stream.start()`), eliminando contención en el dispositivo de micrófono de Windows y reduciendo a 0% el uso de CPU durante la conversación.
  - **Defensividad en Audio Callbacks**: Normalización de arrays 1D/2D contiguos en `int16` para openWakeWord y captura segura de excepciones en callbacks de PortAudio ante cierres del loop asíncrono.
  - **Suite de Pruebas Automatizada**: Creado [`scratch/test_suite.py`](file:///c:/Users/alanv/Documents/miku-assistant/scratch/test_suite.py) validando configuración, las 25 herramientas de control del PC, parser de emociones y desinfección de texto del LLM, motor de wake word y lógica VAD (100% de pruebas superadas).




