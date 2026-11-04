# Plan: auditoría de UI/UX del panel y mejoras (3-nov)

## Estado: fases 0 a 5 hechas (3-nov, noche)

Comprobado sin la app real: capturas a 1240×800 y 980×640 con los datos reales (log, clips, conversaciones,
herramientas, almacenamiento) y pruebas de interacción. Las pruebas cubren:

- marcar con el teclado;
- cambiar de página;
- buscar en las conversaciones;
- el aviso al salir con cambios;
- que una frase solo llene el cuadro;
- «Deshacer»;
- el diálogo de «Liberar».

A 1240×800 ninguna página pasa de 1,5 pantallas:

| Página | Antes | Después |
|---|---|---|
| Palabra clave | 6.245 px | 1.184 px |
| Funciones | 5.713 px | 927 px |
| Herramientas | 4.150 px | 800 px |

Inicio, Recursos, Cuotas, Logs, Memoria y Chat caben en una pantalla.

**Cambios respecto a lo planeado:**

- **Recursos:** las muestras las toma el panel cada 2 s mientras está abierto, en cualquier página, en lugar de
  guardarlas en el backend. Un hueco sin medir se ve como hueco.
- **Recordatorios:** "Hecho" y "Borrar" esperan 5 s con «Deshacer», en lugar de dejar lo hecho tachado debajo. La lista
  de notas no guarda cuándo se hizo cada una.
- **Memoria:** usa dos pestañas (Lo que recuerda / Conversaciones). Las conversaciones van en dos columnas.
- **Configuración:** las tarjetas van en dos columnas, con el control bajo su etiqueta. Así cabe en 1.113 px.

**De paso, un fallo grave:** el tiempo de espera de Gemini en 8 s, que puse antes ese mismo día, hacía fallar todas las
peticiones: la API exige al menos 10 s. Volvió a 10 s, con un test.

Revisé el panel pantalla por pantalla. Lo hice con el navegador sin ventana y con tus datos reales:

- el log (las últimas 1.500 líneas);
- los 121 clips de la palabra clave;
- 6 días de conversaciones;
- las 46 herramientas;
- `funciones.md`.

Lo probé en los dos tamaños de la ventana: 1240×800 (al abrirla) y 980×640 (el mínimo). También leí todo el
código del panel (`app/src/panel/`, unas 1.800 líneas).

Pediste cuatro cosas:

1. Quitar la música.
2. Paginación.
3. Gráficos claros y pantallas que no crezcan sin límite.
4. Un apartado de almacenamiento.

Las cuatro están en las fases de abajo.

## 1. Lo que encontré, medido

Esto es lo que mide cada página a 1240×800. Ahí, una pantalla son 800 px.

| Página | Alto | Pantallas | Qué la hace crecer |
|---|---|---|---|
| Palabra clave | 6.245 px | 8 | 80 clips, uno debajo de otro |
| Funciones | 5.713 px | 7 | Todo `funciones.md` en una sola página |
| Herramientas | 4.150 px | 5 | Las 46 herramientas seguidas |
| Configuración | 1.092 px | 1,4 | Las tarjetas de ajustes |
| Recordatorios | 1.025 px | 1,3 | — |
| Inicio, Cuotas | 915 px | 1,1 | Lo de abajo queda cortado justo en el borde |

### Fallos (no son gustos)

1. **En Palabra clave no se llega a todos los clips.** La lista se corta en 80 sin avisar (`voice.ts`, `slice(0, 80)`).
   Hoy tienes 121, así que los 41 más viejos no se pueden escuchar ni marcar. Cada carpeta guarda hasta 200, así que
   pueden llegar a 600.
2. **En Memoria solo se ven los 14 días más recientes.** Los botones de días se cortan en 14
   (`manage.ts`, `slice(0, 14)`). Cuando tengas más días, los anteriores no se podrán abrir.
3. **En Logs no se puede seleccionar ni copiar texto.** El panel vuelve a dibujar unas 2.000 líneas cada 1,5 s, aunque
   no haya ninguna nueva, y al redibujar se pierde la selección.
4. **Pasa lo mismo, en menor grado, en Recordatorios (cada 5 s) e Inicio (cada 3 s).** Si haces clic justo cuando
   redibuja, el clic se puede perder.
5. **En Configuración y Recordatorios hay tarjetas pegadas, sin separación.**
   - En Configuración: "Clima y OBS" contra "Palabras que Whisper debe conocer".
   - En Recordatorios: "Nuevo recordatorio" contra "Pendientes".
   - La causa: el contenedor (`#cfg`, `#rem`) no tiene el espacio entre bloques que tiene el resto.
6. **Funciones ejecuta órdenes reales con un clic.** Pulsar "Bloquea el PC" bloquea el PC al instante. Pulsar
   "Cierra Discord" cierra Discord y gasta una petición de Gemini. Nada avisa de eso antes de pulsar.
7. **Aparecen dos barras de scroll a la vez.**
   - Memoria: la conversación tiene su propio scroll de 460 px dentro de una página que también se desplaza.
   - Logs: a 980×640 la página mide 655 px, así que se desplaza la página y también la caja del log.
8. **Algunas pantallas se quedan en "Cargando…" para siempre.** Si el backend no responde en 5 s, la petición devuelve
   vacío y Memoria y Recordatorios no lo dicen ni ofrecen reintentar.
9. **El asistente de primer arranque promete "unos 4 GB".** En este PC Miku ocupa unos 6,6 GB: PyTorch solo son
   4,0 GB. Sin NVIDIA serían unos 2,5 GB.
10. **Cuotas pinta en turquesa un modelo que lleva 18 de 20.** El ámbar solo sale por encima del 90 % (`> 0.9`), y 18
    de 20 es justo el 90 %. Además, a ese modelo se le dibuja una barra aunque haya usado 0, porque hay un mínimo de
    1,5 %.

### Problemas que se repiten en todas las pantallas

- **La cabecera repite y ocupa mucho.** Cada página empieza con:
  - una píldora con su nombre (que ya marca la barra lateral);
  - un título de 38 px;
  - una frase.

  Son unos 180 px de 640 a tamaño mínimo. En Inicio se dice tres veces que está encendida: "Todo en orden",
  "Encendida" en grande y "Encendida" en la barra lateral.
- **El rosa significa demasiadas cosas.** Se usa para la VRAM, las peticiones de Gemini, los modelos de respaldo, los
  casi disparos, los errores, los botones de borrar y la píldora "En vivo". Por eso no avisa de nada.
- **El estado se muestra solo con color.** Los puntos de "Piezas" son verdes o grises, sin texto ni icono que lo
  diga.
- **Se pierden cambios sin aviso.** Si cambias algo en Configuración o Herramientas y te vas a otra página, el cambio
  se pierde sin preguntar.
- **Se borra sin poder deshacer.** Borrar un dato de Memoria, borrar un pendiente o cancelar un recordatorio es
  inmediato.
- **Algunos textos están en español de España.** "Lo que hablasteis", "Todavía no habéis hablado hoy". Debería ser
  "lo que hablaron" y "todavía no han hablado hoy".
- **A tamaño mínimo (980×640) hay detalles cortados.**
  - El estado de abajo de la barra lateral queda cortado.
  - En Recursos, "GPU total" queda sola en una fila.
- **Faltan detalles técnicos.**
  - No hay `color-scheme: dark`, así que los menús nativos y las barras de scroll pueden salir claros.
  - El ecualizador se anima siempre, aunque el sistema pida menos movimiento.

## 2. Pantalla por pantalla

### Inicio

- **Bien:** el botón de encender y apagar es claro, y Miku en Live2D le da vida.
- **Mal:**
  - Dice tres veces que está encendida.
  - El ecualizador se mueve igual esté escuchando, pensando o callada (solo acelera al hablar), así que no informa de
    nada.
  - Sobra el botón de música.
  - En "Piezas" se cortan textos ("En uso: gemini-3.5-").
  - Las tres tarjetas de abajo quedan a medias en el borde de la ventana.
  - "Hoy" muestra frases sueltas que no llevan a ninguna parte.
- **Mejora:**
  - Una sola línea de estado que siga lo que hace Miku: "Escuchando «Hey Miku»", "Te escucha…", "Pensando…",
    "Hablando". El backend ya manda esos estados.
  - El ecualizador solo se mueve cuando ella habla.
  - Un bloque principal más bajo, para que todo quepa en 800 px.
  - "Piezas" como lista con texto de estado. Si algo falla, una pista de qué hacer (por ejemplo, "Opera sin conectar ·
    abre Opera").
  - En "Hoy", lo más nuevo primero, y cada frase abre esa conversación.

### Recursos

- **Bien:** la tabla de procesos y que coincida con el Administrador de tareas.
- **Mal (los gráficos):**
  - **No tienen escala.** El eje vertical se ajusta al máximo de lo que se ve: una CPU que pasa de 2,8 % a 4,9 %
    parece un pico enorme.
  - No hay valores en los ejes, ni líneas de guía, ni marcas de tiempo. Al pasar el ratón no se ve el valor.
  - La VRAM no se compara con la memoria total de tu tarjeta.
  - El eje horizontal cuenta muestras, no tiempo: si te vas de la página y vuelves, los huecos desaparecen y el
    gráfico miente.
  - Con dos muestras ya ocupa todo el ancho.
  - "GPU total 41 %" es de todo tu PC, pero está entre las cifras de Miku, y confunde.
  - Debajo de la tabla de procesos queda un hueco grande.
- **Mejora:**
  - **CPU** con escala fija de 0 a 100 %, que se acerca a 0–25 % cuando el uso es bajo. La escala siempre se ve.
  - **VRAM** de 0 a la VRAM de tu tarjeta, con una línea en el total.
  - En los dos: valores en el eje, una guía a media altura, "hace 2 min … ahora" debajo y el valor exacto al pasar el
    ratón.
  - El backend guarda las últimas 60 muestras. Así el gráfico sale completo al abrir la página, sin huecos.
  - "GPU total" pasa a una nota pequeña: "GPU de todo el PC: 41 %".
  - La barra de memoria de cada proceso se compara con la RAM total del PC, no con el proceso que más gasta.
  - Los gráficos van debajo de la tabla, a todo el ancho, para que no quede hueco.

### Cuotas

- **Bien:** el anillo del modelo principal y la lista de respaldos.
- **Mal (el gráfico de 7 días):**
  - No tiene escala.
  - La leyenda es una frase ("turquesa… rosa…") en lugar de muestras de color.
  - Los días no llevan fecha ("mié").
  - Un día con 0 queda vacío.
  - El rosa ahí significa "respaldo", pero en otras pantallas significa error.
  - El "Listo" se repite 5 veces y no aporta nada.
  - La lista dice "en este orden", pero no está numerada.
- **Mejora:**
  - Leyenda con muestras de color.
  - Fechas ("lun 2").
  - Una línea de guía con su valor.
  - El detalle de cada día al pasar el ratón: principal, respaldo y qué modelos.
  - Respaldos numerados (1, 2, 3…).
  - Solo se marca lo raro ("En pausa 9 min", "Casi agotado"), y el ámbar empieza en el 80 %.

### Logs

- **Bien:** los filtros, la búsqueda y la pausa.
- **Mal:**
  - Redibuja todo cada 1,5 s, así que no se puede copiar (fallo 3).
  - Solo se ven las últimas 1.500 líneas. Los archivos rotados (`core.log.1` a `.3`, hasta unos 8 MB) no se pueden
    ver.
  - Las líneas tienen hora pero no fecha.
  - La columna de origen se corta ("faster_whisp…").
  - Los INFO salen en turquesa brillante, con el mismo peso que todo lo demás.
  - Los filtros no dicen cuántas líneas tienen.
  - La búsqueda no resalta lo que encuentra.
- **Mejora:**
  - Añadir solo las líneas nuevas. Rust lee desde la última posición del archivo.
  - "Cargar más antiguas" de 500 en 500, también desde los archivos rotados.
  - Separadores de fecha.
  - INFO en gris, y WARN y ERROR en color.
  - Cuántas líneas tiene cada filtro.
  - Resaltar la búsqueda.
  - Botón "Abrir carpeta de logs".
  - Nunca se borra nada.

### Configuración

- **Bien:** guarda sin perder los comentarios de `config.yaml`, y la API key se puede probar.
- **Mal:**
  - Tarjetas pegadas (fallo 5) y de altos distintos.
  - No marca cuando hay cambios sin guardar, y al irte los pierdes.
  - El atajo se escribe a mano.
  - La contraseña de OBS no tiene "Probar" (la API key sí).
  - El umbral no te dice qué efecto tiene con tus clips.
- **Mejora:**
  - Una sola columna de grupos de ajustes, con separación.
  - Aviso de "Cambios sin guardar", con "Descartar", y una pregunta si te vas sin guardar.
  - El atajo se graba pulsando las teclas.
  - "Probar" para OBS.
  - Bajo el umbral, una frase calculada con tus marcas, por ejemplo: "Con 0,35, 18 de tus 20 llamadas la activan".

### Herramientas

- **Bien:** apagar una herramienta es una sola acción.
- **Mal:**
  - Una lista de 46 de 4.150 px.
  - Se muestra el nombre técnico (`browser_tabs`), y la descripción es el texto que lee Gemini ("action = close |
    activate | reload…"), no para una persona.
  - No están agrupadas.
  - Las píldoras "FRASE LOCAL" y "PIDE CONFIRMACIÓN" parecen filtros, pero no hacen nada.
- **Mejora:**
  - Nombre en español y una frase clara; el nombre técnico, pequeño.
  - Agrupadas por tema: Apps y ventanas, Música y video, Opera, PC, Archivos, Recordatorios y notas, Memoria, OBS,
    Información. Los grupos se pueden plegar.
  - Filtros de verdad: Todas, Locales, Piden confirmación, Apagadas.
  - Aquí no hace falta paginación: con grupos y filtros cabe.

### Funciones

- **Bien:** las frases de ejemplo y la búsqueda.
- **Mal:**
  - Todo el documento en una página de 5.713 px, sin índice.
  - El párrafo de arriba nombra `tools.md`, pero el enlace no funciona.
  - Al buscar se ocultan las filas, pero quedan títulos y tablas vacías.
  - Un clic ejecuta la orden de verdad (fallo 6).
- **Mejora:**
  - Un índice con las secciones del documento y una sección a la vista.
  - La búsqueda junta resultados de todas las secciones y dice de cuál viene cada uno; oculta lo que queda vacío.
  - Cada frase marca si es local o si gasta una petición.
  - Pulsar una frase la deja escrita en un cuadro "Probar con Miku", con un botón "Enviar". Así no se ejecuta nada por
    accidente.

### Recordatorios

- **Bien:** crear y cancelar desde aquí, y los mismos datos que usa Miku.
- **Mal:**
  - Tarjetas pegadas (fallo 5).
  - Redibuja cada 5 s (fallo 4).
  - La lista deja mucho espacio vacío.
  - "Hecho" y "Borrar" parecen hacer lo mismo.
  - Cancelar no se puede deshacer.
- **Mejora:**
  - Cada aviso con la hora relativa y la exacta ("en 12 min · 17:45").
  - Cancelar y Borrar con "Deshacer" durante 5 s.
  - Lo hecho hoy queda tachado debajo, en lugar de desaparecer.
  - Paginación a partir de 10 elementos.

### Memoria

- **Bien:** editar lo que recuerda y releer conversaciones.
- **Mal:**
  - Doble scroll (fallo 7).
  - Solo 14 días (fallo 2).
  - "Editar" y "Borrar" en cada fila hacen ruido.
  - Borrar no se puede deshacer.
  - No se puede buscar en las conversaciones.
  - Textos en español de España.
- **Mejora:**
  - Dos columnas. A la izquierda los días, paginados y agrupados por mes. A la derecha la conversación, a toda la
    altura y con un solo scroll.
  - Buscar en todas las conversaciones.
  - Los datos se editan con un clic sobre el texto, y borrar tiene "Deshacer".
  - Paginación de los datos a partir de 20.

### Palabra clave

- **Bien:** escuchar cada clip y marcarlo, el progreso hacia 60 marcas y el reentrenamiento.
- **Mal:**
  - No se llega a todos los clips (fallo 1).
  - Antes del primer clip hay unos 300 px de cifras y tarjetas, y cada fila mide 70 px: en 800 px solo se ven unos 4
    clips.
  - Marcar 60 clips solo con el ratón es pesado.
  - "Ignorada: silencio" junto a "puntuación 0,459" confunde.
- **Mejora (lo más importante, porque aquí vas a trabajar):**
  - **Paginación**, 20 por página, con "21–40 de 121".
  - Filas compactas (48 px), con lo que oyó en la misma línea.
  - Las cifras del día en una sola línea, y la tarjeta de reentrenar más pequeña.
  - **Modo marcar con teclado:**
    - `Espacio` escucha;
    - `S` = era yo;
    - `N` = no era yo;
    - avanza solo al siguiente clip sin marcar.
  - Para "Ignorada", el texto "Ignorada: era casi silencio" en vez de la puntuación.

### Chat

- **Bien:** solo texto, el indicador de "pensando" y que salgan también los turnos de voz.
- **Mal:**
  - Con Miku apagada se puede escribir; solo cambia el texto de ayuda.
  - Solo muestra hoy.
  - Textos en español de España.
- **Mejora:**
  - Con Miku apagada, la caja de texto se desactiva y se ofrece "Encender".
  - "Cargar días anteriores".
  - Separadores de fecha.

### Primer arranque

- **Bien:** es claro, por pasos, y cabe en 980×640.
- **Mal:** la cifra de "unos 4 GB" (fallo 9).
- **Mejora:** decir el tamaño real según tengas NVIDIA o no ("unos 6,5 GB con tarjeta NVIDIA; unos 2,5 GB sin ella").

## 3. Nuevo apartado: Almacenamiento

Una página nueva en la barra lateral, debajo de Recursos. Esto es lo que ocupa hoy en este PC, en desarrollo:

| Qué | Dónde | Tamaño |
|---|---|---|
| Python y librerías | `core/.venv` (instalado: `%LOCALAPPDATA%\Miku Assistant\runtime`) | 5,1 GB, de ellos PyTorch 4,0 GB |
| Modelos de voz que usa | Caché de Hugging Face: Whisper `small` y ContentVec | 1,2 GB |
| Modelos que Miku ya **no** usa | Caché de Hugging Face: Whisper `base` y `hubert-base` | 0,86 GB |
| Voz de Miku (RVC) y palabra clave | `models/` | 255 MB |
| Clips de la palabra clave | `cache/wake` | 7,6 MB (hasta unos 40 MB con 600 clips) |
| Logs | `cache/*.log*` | 1,2 MB (con la rotación, hasta unos 8 MB) |
| Caché de voz, conversaciones, memoria | `cache/` | menos de 1 MB |
| **Total** | | **unos 6,6 GB** |

**Qué muestra:**

- Una cifra grande con el total y una barra dividida por categoría, con su leyenda.
- Debajo, una fila por categoría: tamaño, carpeta y botón "Abrir carpeta".
- El espacio libre del disco.

**Acciones**, todas con confirmación:

- "Borrar clips ya marcados y viejos".
- "Vaciar caché de voz" (se regenera sola).
- "Borrar modelos que Miku no usa", solo los que Miku conoce.

**Límites:**

- Los logs nunca tienen botón de borrar, por tu regla.
- La caché de Hugging Face la pueden compartir otros programas: solo se cuentan y se ofrecen los modelos de Miku.

**Cómo se mide:**

- Un comando de Rust recorre las carpetas en segundo plano y guarda el resultado con su hora en
  `cache/storage.json`.
- Al abrir la página se ve el último resultado al instante, con un botón "Actualizar".
- Funciona con Miku apagada.
- Recorrer `core/.venv` con `du` tardó más de 3 minutos. Con Rust debería tardar segundos, pero hay que medirlo. Si
  tarda, se muestra el progreso.

## 4. Paginación: un solo componente

En `shared.ts` habrá una pieza común: `‹ 1 2 3 … 7 ›  ·  21–40 de 121`.

- Botones de verdad, que funcionan con teclado.
- Vuelve a la página 1 al cambiar de filtro o de búsqueda.
- Mantiene la página cuando llegan datos nuevos.

**Dónde se usa paginación:** en listas que crecen con el tiempo.

| Lista | Por página |
|---|---|
| Clips de Palabra clave | 20 |
| Días de conversación | 15 |
| Datos de Memoria | 20 |
| Recordatorios y pendientes | 10 |

**Dónde no**, porque otra forma va mejor:

- **Herramientas:** grupos y filtros. Es un catálogo fijo de 46.
- **Funciones:** índice por secciones.
- **Logs y Chat:** "Cargar más antiguas". Son un flujo en el tiempo; numerar páginas que cambian cada segundo
  confunde.

## 5. Fases

Cada fase deja el panel usable y se verifica antes de pasar a la siguiente.

### Fase 0: quitar y arreglar (pequeña)

- Quitar la música:
  - `music.ts`;
  - el botón y su mensaje;
  - el CSS `.eq.music` y `#music`;
  - los comandos de Rust `panel_music` y `open_music_folder`, y `MUSIC_EXT`;
  - las líneas de los docs y del CHANGELOG.
- Fallos 1 y 2: todos los clips y todos los días accesibles. Mientras llega la paginación, con "Mostrar más".
- Fallos 3 y 4: redibujar solo si los datos cambiaron. En Logs, añadir solo las líneas nuevas.
- Fallo 5: la separación de las tarjetas.
- Fallo 6: Funciones deja de enviar con un clic.
- Fallo 8: "Miku no respondió · Reintentar" en lugar de "Cargando…" eterno.
- Fallos 9 y 10: la cifra del primer arranque y el color en Cuotas.
- Pasar los textos al español de aquí ("hablaron", "han hablado").
- `color-scheme: dark` y respetar "menos movimiento" del sistema.

### Fase 1: base común

- El componente de paginación (sección 4).
- Una sola barra de scroll por página. Las páginas con lista llenan el alto de la ventana y solo se desplaza la lista.
- Cabecera compacta:
  - sin la píldora con el nombre;
  - título de 28 px;
  - unos 70 px menos por página.
- Barra lateral agrupada:
  - **Estado:** Inicio, Recursos, Almacenamiento, Cuotas, Logs;
  - **Miku:** Configuración, Herramientas, Funciones, Palabra clave;
  - **Lo tuyo:** Recordatorios, Memoria, Chat.

  El estado de abajo siempre visible.
- Colores con un solo significado cada uno:
  - **turquesa:** bien, Miku;
  - **ámbar:** aviso o pausa;
  - **coral:** error y borrar;
  - **rosa:** solo el acento de la marca;
  - **violeta:** la VRAM.

  Junto al color, siempre un texto o un icono.
- Aviso con "Deshacer" (5 s) para borrar y cancelar.
- Aviso de cambios sin guardar en Configuración y Herramientas.

### Fase 2: gráficos claros

- Una pieza de gráfico común, con:
  - escala visible;
  - guías;
  - eje de tiempo;
  - valor al pasar el ratón;
  - leyenda con muestras de color.
- Recursos y Cuotas pasan a usarla (detalle en la sección 2).
- El backend guarda las últimas 60 muestras de recursos para que el gráfico salga completo al abrir.

### Fase 3: Almacenamiento

La página de la sección 3, con su comando de Rust, el resultado guardado y las acciones con confirmación.

### Fase 4: cada pantalla

Las mejoras de la sección 2, en este orden (primero lo que más usas):

1. **Palabra clave:** paginación, filas compactas y modo marcar con teclado.
2. **Logs:** líneas antiguas, fechas, colores, cuántas hay por filtro y resaltar la búsqueda.
3. **Inicio:** estado en una línea, todo en 800 px, y "Hoy" que lleva a la conversación.
4. **Memoria:** dos columnas, búsqueda y días paginados.
5. **Herramientas:** nombres en español, grupos y filtros.
6. **Funciones:** índice y el cuadro "Probar con Miku".
7. **Recordatorios y Chat.**
8. **Configuración:** atajo grabado con las teclas, "Probar" para OBS y la frase del umbral.

### Fase 5: comprobar

- Capturas de las 13 pantallas a 1240×800 y 980×640, con tus datos reales, como en esta auditoría.
- **Criterios de aceptación:**
  - ninguna página pasa de 1,5 pantallas de alto;
  - una sola barra de scroll por página;
  - se puede copiar texto del log;
  - se llega a todos los clips y a todos los días;
  - nada se ejecuta ni se borra con un solo clic sin aviso o "Deshacer".
- Todos los tests, `npm run build` y `npx tauri build`.

## 6. Qué no cambia

- La identidad visual: oscuro, turquesa y Miku en Live2D.
- Que Logs nunca borra nada.
- Que los ajustes se guardan sin perder los comentarios de `config.yaml`.
- No se instala ninguna librería nueva. Los gráficos, la paginación y la medición de disco se hacen con lo que ya hay
  (SVG, TypeScript y Rust estándar).
