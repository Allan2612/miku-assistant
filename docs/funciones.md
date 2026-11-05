# Qué puede hacer Miku

Todo lo que Miku sabe hacer y cómo pedírselo. Las frases son ejemplos: con Gemini no hace falta decirlas exactas.
Lo de "local" sí tiene que decirse más o menos así.

- **Local** = se hace en tu PC, **0 peticiones a Gemini** (no gasta cuota y responde al instante).
- **Gemini** = gasta cuota del plan gratuito. Gemini oye tu audio, ve el estado del PC (ventanas, pestañas de Opera,
  pendientes, recordatorios) y elige la herramienta.

Detalles técnicos de cada herramienta: [tools.md](tools.md).

## Cómo llamarla

| Forma | Qué pasa |
|---|---|
| Decir **"Hey Miku"** | Aparece, dice "¿Sí?" y te escucha (hasta 8 s para empezar a hablar, 10 s de frase) |
| **Ctrl+Alt+M** | Igual que "Hey Miku". Si está hablando, la corta y te escucha |
| **"Hey Miku" mientras habla** | La interrumpe y te escucha |
| Escribirle en el cuadro bajo ella | Solo si activas «Escribirle desde su ventana» en el panel › Configuración. Lo que escribes le llega como si se lo dijeras |
| Bandeja → **Mostrar / Ocultar / Salir** | Ocultar corta lo que esté haciendo (no habla ni abre el micrófono oculta). Salir cierra también el backend |
| Clic sobre ella | Solo reacciona (sonrisa y gesto); no la activa |

## Local (0 peticiones)

La frase tiene que ser **solo la orden**. Con una pregunta alrededor ("¿qué significa pausa en inglés?") o dos órdenes
juntas ("abre Spotify y sube el volumen"), va a Gemini.

| Qué | Cómo pedirlo |
|---|---|
| Saludo según la hora | "Hola", "Hola Miku", "Buenos días", "Buenas tardes", "Buenas noches", "Hola, ¿qué tal?" |
| Volumen exacto | "Pon el volumen al 30", "Volumen al 50 por ciento", "Súbelo al máximo", "Sube el volumen a tope", "Baja el volumen al mínimo" |
| Subir o bajar volumen (15 %) | "Sube el volumen", "Súbele el volumen", "Bájale el volumen", "Bajá el volumen", "Más volumen", "Menos volumen" |
| Silenciar el PC | "Silencio", "Silencia el PC", "Mutea", "Pon silencio" |
| Pausar | "Pausa", "Pon pausa", "Ponle pausa a la canción", "Pausa la música", "Pausa el video" |
| Reanudar | "Play", "Dale play", "Dale play a la canción", "Reanuda", "Pon la música", "Continúa la música" |
| Canción siguiente o anterior | "Siguiente canción", "Pasa a la siguiente", "Salta esta canción", "Pon la anterior", "Canción anterior" |
| Quitar el silencio del PC | "Quita el silencio", "Activa el sonido", "Desmutea" |
| Video de YouTube (necesita la extensión de Opera) | "Sube / baja el volumen del video", "Volumen del video al 50", "Silencia el video", "Siguiente video", "Adelanta 30 segundos", "Regresa 10 segundos", "Pon subtítulos", "Quita los subtítulos", "Ponlo en 1080", "Máxima calidad", "Velocidad 1,5", "Velocidad normal", "Ponlo en bucle" |
| OBS (solo con OBS abierto) | "Guarda eso", "Clip", "Empieza a grabar", "Deja de grabar", "Para la grabación", "Cambia a la escena X" |
| Clima de tu ciudad | "¿Cómo está el clima?", "¿Va a llover hoy?", "¿Va a llover mañana?", "¿Qué temperatura hace?", "¿Cómo estará el clima mañana?" |
| Tu día | "¿Qué tengo hoy?", "¿Qué tengo que hacer hoy?", "¿Cómo está mi día?", "Resumen del día" |
| Cuota de Gemini | "¿Cuánta cuota me queda?", "¿Cuántas peticiones llevas hoy?", "¿Cómo va la cuota?" |
| Aviso de descargas | "Avísame cuando termine la descarga", "Avísame cuando terminen las descargas" |
| Bloquear el PC | "Bloquea el PC", "Bloquea la pantalla" |
| Ver recordatorios | "¿Qué recordatorios tengo?", "¿Cuáles son mis recordatorios?" |
| Hora | "¿Qué hora es?", "Dime la hora" |
| Temporizador | "Pon un temporizador de cinco minutos para el té", "Avísame en media hora" |
| Recordatorio en N minutos/horas | "Recuérdame en 10 minutos que saque la ropa", "Recuérdame en una hora llamar a mamá" (números en cifra o: un, una, dos, tres, cuatro, cinco, diez, quince, veinte, treinta, media) |
| Apuntar una nota o pendiente | "Toma nota: llamar a mamá", "Anota comprar pan", "Apunta que tengo pendiente subir el PR", "Apúntame que mañana hay examen" |
| Leer pendientes | "¿Qué pendientes tengo?", "Léeme mis notas", "Mis pendientes", "¿Cuáles son mis notas?" |
| Recordar un dato tuyo para siempre | "Recuerda que mi gato se llama Mochi", "Acuérdate de que mi cumple es el 3 de mayo", "No olvides que…" |
| Mostrar el escritorio | "Muestra el escritorio", "Minimiza todo", "Minimiza todas las ventanas" |
| Rutinas de `config.yaml` | "Modo trabajo" (Opera + volumen 30), "Activa el modo música" (Spotify + volumen 50) |
| Apagar, reiniciar o suspender | "Apaga el PC", "Reinicia la computadora", "Suspende el equipo". Te pregunta antes; contesta **"sí"** (también local) en menos de 60 s. Apagar deja 30 s para cancelar |
| Despedirse (se va) | "Adiós", "Gracias", "Ya está", "Eso es todo", "Listo, gracias", "Déjalo", "Olvídalo", "No importa" |
| Ocultarse sin decir nada | "Ocúltate", "Vete", "Escóndete", "Apágate", "Duérmete", "Puedes irte" |

También es local: la detección de "Hey Miku", la transcripción (Whisper), descartar ruido o su propia voz, y repetir
la misma frase en menos de 2 s (reutiliza la respuesta).

## Con Gemini (gasta cuota)

### Apps y ventanas
| Qué | Cómo pedirlo |
|---|---|
| Abrir una app | "Abre Spotify", "Ábreme Opera", "Abre el Bloc de notas" |
| Cerrar una app | "Cierra Discord", "Cierra Spotify" |
| Qué tienes abierto | "¿Qué tengo abierto?" |
| Manejar ventanas | "Minimiza todo menos el juego", "Pon Opera a la izquierda", "Maximiza VS Code", "Mueve Discord al otro monitor", "Trae Spotify al frente", "Cierra la ventana de Opera" |
| Escribir en la ventana activa | "Escribe: hola, ya voy" (máx. 500 caracteres, no en consolas) |

### Opera y YouTube (necesita la extensión de Miku en Opera)
| Qué | Cómo pedirlo |
|---|---|
| Abrir una web | "Abre youtube.com", "Abre tytsoluciones.net", "Abre la página del Banco de Costa Rica", "Entra a la web de Steam" |
| Corregir la última web | "No, era tytsoluciones.net" (la carga en la misma pestaña) |
| Buscar en Google | "Busca recetas de arroz con leche" |
| Poner algo en YouTube | "Ponme More en YouTube", "Reprodúceme World is Mine" (reutiliza la pestaña que abrió ella) |
| Buscar en YouTube sin reproducir | "Busca en YouTube World is Mine" |
| Abrir un resultado visible | "Ábreme el segundo resultado", "Abre ese enlace" |
| Pestañas | "Cierra esta pestaña", "Cierra todas menos la de YouTube", "Ve a la pestaña de Discord", "Recarga la página", "Vuelve atrás" |
| Reproductor de YouTube, dicho de otra forma | "Ponle subtítulos en español a este video", "Ponlo al doble de velocidad" (las frases cortas son locales, arriba) |

### PC y portapapeles
| Qué | Cómo pedirlo |
|---|---|
| Estado del PC | "¿Cómo va el PC?" (CPU, RAM, GPU/VRAM y disco) |
| Fecha | "¿Qué día es hoy?" |
| Bloquear la sesión, dicho de otra forma | "Bloquéame la compu que me voy" |
| Copiar un texto | "Copia al portapapeles mi correo" |
| Leer lo copiado | "¿Qué tengo copiado?", "Léeme el portapapeles" |

### Archivos (Escritorio, Documentos y Descargas)
| Qué | Cómo pedirlo |
|---|---|
| Buscar un archivo | "Busca el archivo informe" |
| Abrir lo encontrado | "Ábrelo", "Abre el informe" |
| Abrir una carpeta | "Abre Descargas", "Abre mis documentos" |
| Crear un archivo de texto en el Escritorio | "Crea un archivo lista con: pan, leche, huevos" (nunca sobrescribe) |
| Leer un .txt / .md / .csv / .log | "Léeme el archivo notas de clase" |

No puede borrar, mover ni renombrar archivos.

### Recordatorios, notas y memoria
| Qué | Cómo pedirlo |
|---|---|
| Recordatorio a una hora o fecha | "Recuérdame mañana a las 8 que tengo cita", "Recuérdame el viernes a las 6 pagar la luz" |
| Recordatorio que se repite | "Recuérdame todos los días a las 9 tomar la pastilla", "Cada 2 horas recuérdame estirar" |
| Cancelar | "Cancela el recordatorio 3" |
| Marcar un pendiente como hecho | "Ya subí el PR" |
| Borrar una nota | "Borra la nota de comprar pan" |
| Abrir el archivo de notas | "Abre mis notas" |
| Olvidar un dato | "Olvida lo de mi gato" |
| Recordar conversaciones | "¿De qué hablamos ayer?", "¿Qué te dije del banco?" |

### OBS, clima y descargas, dicho de otra forma
| Qué | Cómo pedirlo |
|---|---|
| OBS | "Guárdame la jugada de recién", "Pásate a la escena del juego" |
| Clima de otra ciudad | "¿Qué clima hace en Tokio?", "¿Llueve mañana en Madrid?" |

OBS necesita su servidor WebSocket activado (en OBS: Herramientas → Ajustes del servidor WebSocket) y la contraseña en
`.env` como `OBS_PASSWORD`. Para guardar clips, el búfer de repetición tiene que estar configurado (Ajustes → Salida);
si está apagado, Miku lo enciende y te avisa de que lo anterior no se puede guardar. No inicia ni para directos.

### Ver tu pantalla
Si la frase habla de la pantalla, va una captura en la misma petición: "¿Qué ves en mi pantalla?", "Mira este error",
"¿Qué dice esta ventana?". Nunca captura si no lo pides.

### Conversar
Preguntas, chistes, opiniones, explicaciones: "¿Quién pintó la Mona Lisa?", "Cuéntame un chiste".
La búsqueda de Google dentro de la respuesta está apagada (el plan gratuito la rechaza).

## Lo que hace sola

- **Sobre pantalla completa:** aparece también sobre juegos y videos; se puede apagar en Configuración. Apagado, no aparece encima. Te sigue
  escuchando ("Hey Miku", Ctrl+Alt+M) y responde solo con voz; los recordatorios también. No saluda al arrancar.
- **Aviso de cuota:** cuando el modelo principal llega al 90 % de sus peticiones del día, lo dice una vez.
- **Saludo de la mañana** con los recordatorios de hoy, si hay.
- **Modo conversación:** después de cada respuesta deja el micrófono abierto 6 s; puedes seguir hablando sin "Hey Miku".
- **Se oculta sola** tras 20 s sin actividad, despidiéndose si estuvieron hablando.
- **Saludo** al arrancar, una vez al día.
- **Avisa los recordatorios** aunque esté oculta: aparece, lo dice y se vuelve a ocultar. Sobreviven a reinicios; los
  que vencieron con Miku apagada (hace menos de 6 h) los dice al arrancar.
- **Descarta falsos "Hey Miku"**: si lo que oyó no era su nombre ni una orden, se oculta sin responder.
- **No miente:** si Gemini dice "lo abrí" sin haberlo hecho, Miku dice que no llegó a hacerlo.
- **Cambia de modelo** cuando uno se queda sin cuota ("Un momento…").
- **Ahorra recursos:** descarga la voz RVC de la GPU tras 10 min sin uso y congela el dibujo cuando está oculta.
- **Una sola voz:** si la voz de Miku (RVC) falla, responde solo con subtítulo, nunca con la voz base.
