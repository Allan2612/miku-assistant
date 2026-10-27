# Plan de expresiones y animación de Miku (27-oct)

Objetivo: que Miku se sienta viva y con personalidad: que reaccione a lo que pasa (escuchar, pensar, hablar, acertar,
equivocarse, despedirse) con movimientos fluidos y naturales, sin seguir el mouse.

## 1. Qué hay hoy (revisado en el código y renderizando el modelo)

**Modelo en uso:** `miku_official/miku_sample_t04` (la muestra oficial de Live2D). Se renderizó parámetro por
parámetro y cada uno de sus 8 movimientos fotograma a fotograma en un navegador sin ventana.

| Puede mover | Parámetros | Cómo se ve |
|---|---|---|
| Cabeza (3 ejes) y cuerpo (3 ejes) | `ParamAngleX/Y/Z`, `ParamBodyAngleX/Y/Z` | Bien, rango amplio |
| Ojos: abrir, sonreír, mirada | `ParamEyeL/ROpen`, `ParamEyeL/RSmile`, `ParamEyeBallX/Y` | Bien; los ojos sonrientes se notan |
| Cejas: altura, ángulo, forma | `ParamBrowL/RY`, `ParamBrowL/RAngle`, `ParamBrowL/RForm` | Sutil |
| Boca: abrir y forma (sonrisa / mueca) | `ParamMouthOpenY`, `ParamMouthForm` | Sin formas de vocales |
| Rubor | `ParamCheek` | Sutil |
| **Brazos** | `ParamArmL`, `ParamArmR` | Solo giran hacia fuera (~45°) o se pegan al cuerpo. **No hay manos ni codos** |
| Respiración, pelo, falda, corbata | `ParamBreath` y física | Automáticos |

Sus 8 movimientos son suaves y parecidos entre sí: inclinar la cabeza, cerrar o sonreír con los ojos, abrir un poco
los brazos (01, 02, 04, 07), mirar arriba (06), timidez con rubor (05), balanceo largo (08). **Ninguno es un saludo
con la mano.** No trae archivos de expresiones.

**Consecuencia:** con este modelo se puede dar mucha más vida a la cabeza, la mirada, la cara, el cuerpo y los brazos
(abrirlos de alegría, pegarlos al pensar, levantarlos), pero **no** gestos de manos de verdad: mano a la barbilla,
saludar moviendo la mano, aplaudir. Eso pide otro modelo (fase 7).

**Lo que hace el frontend (`app/src/live2d.ts`, `clickthrough.ts`, `animations.ts`):**
- Movimientos de reposo del modelo al azar (grupo Idle: 01, 04, 07) más un gesto aleatorio cada 5-9 s (inclinar,
  mirar a un lado, mirar arriba). Siempre los mismos tres, sin relación con lo que pasa.
- 5 emociones (feliz, pensativa, sorprendida, triste, enojada) como desplazamientos suaves de cejas, ojos y rubor.
  Ya existe un buen mecanismo de "objetivos con suavizado" que se suma al movimiento del modelo.
- Labios: solo abrir y cerrar la boca según el volumen del audio.
- **Sigue el mouse** con ojos y cabeza (`clickthrough.ts` llama a `live2d.focus`): lo que no te gusta.
- Al hacer clic: movimiento Tap y rubor.
- Aparecer y desaparecer: animación CSS de 0,24 s (salta y crece; encoge y se va). Sin gesto propio.
- Estados escuchando / pensando / hablando: solo cambian la burbuja de texto, no el cuerpo.

**El otro modelo instalado, `RetrynowMiku`, no es Miku:** es otro personaje (pelo oscuro, uniforme negro), con una
marca de agua de su autor (呜哔x慈善小霓) que el código intenta ocultar sin éxito. Tiene buenas poses (mano en el
pecho, brazos abiertos, manos a la espalda) y caras (ojos de estrella, gota de sudor, puchero), pero no sirve.
Propuesta: borrarlo y quitar su código de `live2d.ts`.

**Licencia:** el modelo oficial es de las muestras de Live2D, cuyo uso libre excluye a Hatsune Miku: la rige la
licencia de personaje de Crypton (PCL), que permite obras de fans **no comerciales**. Para un asistente personal
está bien; venderlo o monetizarlo pediría permiso a Crypton.

## 2. Qué hace que una animación parezca viva (investigación)

- **Capas, no clips sueltos.** Los sistemas de animación "de ambiente" separan: respiración, parpadeo, mirada,
  micromovimientos de cabeza, y encima los gestos con intención. Cada capa con su propio ritmo; así nunca se repite
  igual ni se congela.
- **Parpadeo con variación:** cierre rápido, apertura más lenta, intervalos al azar (2-6 s) y a veces doble parpadeo.
  Parpadear al cambiar de mirada y al terminar una frase.
- **Mirada con intención, no ruido:** los ojos saltan en pequeños movimientos rápidos (sacadas) y se quedan quietos
  entre saltos. Añadir ruido continuo a los ojos da una mirada "de zombi" (Ken Perlin).
- **Ruido suave para el cuerpo:** pequeñas oscilaciones lentas y aleatorias de cabeza y cuerpo (ruido tipo Perlin)
  evitan que parezca una estatua; cambios de peso cada 8-15 s.
- **Mirada y conversación:** al empezar a hablar o al pensar se aparta la mirada; al terminar una frase se mira al
  interlocutor. Al escuchar: asentimientos pequeños en las pausas del que habla. Esto hace que el usuario hable con
  más fluidez y perciba al agente como más eficiente (estudios con agentes conversacionales).
- **Cabeza al hablar:** la cabeza no para mientras se habla; pequeños golpes de cabeza en las sílabas fuertes.
- **Principios de animación:** anticipación (un pequeño movimiento contrario antes del gesto), continuidad (el pelo
  y la ropa siguen: ya lo hace la física), tiempos variados, evitar la simetría perfecta (un brazo un poco antes que
  el otro, una ceja más que la otra).

## 3. El plan

Todo es procedural, en `app/src/live2d.ts` y archivos nuevos del frontend, sobre el mecanismo de objetivos con
suavizado que ya existe. Sin dependencias nuevas, 30 FPS como ahora, y Miku sigue sin consumir nada oculta.

### Fase 1: quitar lo que molesta (pequeña)
- **No seguir el mouse:** quitar la llamada a `focus` de `clickthrough.ts`. La mirada pasa a la capa de mirada de la
  fase 2: mira al frente (a ti) y aparta la vista con intención.
- **Borrar RetrynowMiku** (archivos y su código de "sanitizar parámetros" en `live2d.ts`).
- Desactivar los movimientos de reposo del modelo que abren los brazos al azar (04 y 07): se usarán a propósito.

### Fase 2: motor de capas (la base de todo, mediana)
Un sistema de capas que se suman cada fotograma, en este orden:
1. **Movimiento del modelo** (los 8 clips, usados como gestos, no al azar).
2. **Ambiente:** respiración (ya existe en el modelo), micro-oscilación de cabeza y cuerpo con ruido suave,
   cambio de peso cada 8-15 s.
3. **Parpadeo propio:** variación, dobles parpadeos, parpadeo al cambiar de mirada; menos parpadeo al sorprenderse.
4. **Mirada:** sacadas pequeñas con pausas, mirar al frente por defecto, apartar la vista a un punto (arriba a un
   lado al pensar, abajo al estar tímida).
5. **Emoción:** la cara de fondo (cejas, ojos, boca, rubor) según la emoción actual, que cambia suave.
6. **Gestos:** una cola de gestos con nombre, cada uno una pequeña coreografía de parámetros con curvas
   (anticipación, movimiento, rebote, vuelta): `asentir`, `negar`, `inclinar_curiosa`, `mirar_arriba_pensando`,
   `rebote_feliz`, `abrir_brazos`, `pegar_brazos` (nerviosa / pensando), `encoger_hombros`, `reverencia`,
   `saludo` (levantar brazo y balancear), `suspiro`, `saltito` (mueve todo el modelo, no solo parámetros).
7. **Labios** (fase 5).

Para revisarlo sin depender del ojo en vivo: un modo de pruebas con teclas que disparan cada gesto, y capturas o
video automáticos con el mismo navegador sin ventana usado en este estudio.

### Fase 3: que reaccione a lo que pasa (mediana)
El backend ya envía los estados; el frontend los convierte en conducta:

| Momento | Qué hace |
|---|---|
| Aparece | Salto pequeño de entrada, mira hacia ti, sonrisa, quizá saludo con el brazo |
| Escuchando | Atenta: mirada al frente, cabeza un poco inclinada, asentimientos pequeños en tus pausas (el backend ya detecta silencios con el VAD: se envía un aviso al frontend) |
| Pensando | Aparta la mirada arriba a un lado, cejas pensativas, cabeza inclinada, brazos pegados; si tarda (cambio de modelo, "un momento…") cambia de postura o suspira |
| Hablando | Mira al frente al terminar frases, golpecitos de cabeza en las palabras (edge-tts ya da los tiempos de cada palabra: se mandan con el audio), emoción de la respuesta |
| Hizo algo bien | Rebote feliz, ojos sonrientes, brazos abiertos un instante |
| Algo falló | Cejas tristes, cabeza baja, encoge hombros |
| Recordatorio | Se asoma con un gesto de "¡oye!": cejas arriba, brazos un poco arriba |
| Despedida | Sonrisa con ojos cerrados, brazo arriba balanceándose (lo más parecido a decir adiós que permite el modelo), pequeña reverencia; después se va |
| Mucho rato en reposo | Mira alrededor, se balancea, a veces un bostezo o tararea (cabeza al ritmo) |
| Clic encima | Sorpresa, rubor, risita (ya existe en parte) |

### Fase 4: más emociones y personalidad (pequeña-mediana)
- Nuevas caras además de las 5 actuales: **tímida** (rubor, mirada abajo), **emocionada** (ojos muy abiertos,
  brazos arriba, rebotes), **confundida** (cabeza ladeada, una ceja arriba), **orgullosa** (barbilla arriba, ojos
  sonrientes), **traviesa** (guiño: un ojo cerrado), **cansada** (ojos medio cerrados, de noche o tras mucho rato).
- Gemini elige la emoción en cada respuesta (ya lo hace con 6 etiquetas): se amplía la lista en el prompt.
- Las emociones combinan cara y gesto: "emocionada" no es solo una cara, también rebota.

### Fase 5: labios más naturales (mediana)
- Hoy la boca solo abre y cierra según el volumen. Con los tiempos de cada palabra de edge-tts: cerrar la boca entre
  palabras, abrir más en las sílabas fuertes, variar la forma de la boca (`ParamMouthForm`) para que no sea siempre
  la misma "o". El modelo no tiene formas de vocales, así que no habrá "a-e-i-o-u" exactas.
- Parpadear y mirar al frente al terminar cada frase.

### Fase 6: entrada y salida (pequeña)
- Sustituir el salto CSS de 0,24 s por una entrada dentro del modelo (aparece, sube un poco, mira, sonríe) y una
  salida tras la despedida (saludo, reverencia, se desvanece). Si hablas mientras se va, vuelve.

### Fase 7 (opcional, grande): gestos de manos de verdad
Para "mano en la barbilla al pensar", "decir adiós con la mano" o "aplaudir" hace falta **otro modelo de Miku con
brazos y manos articulados**. Opciones:
- Comprar uno hecho por fans (BOOTH, nizima): revisar que su licencia permita el uso personal y que no tenga marca
  de agua. Los paquetes de gestos de manos suelen venderse aparte o con el modelo.
- Encargarlo a un artista (Fiverr y similares ofrecen gestos de manos como extra).
- No se pueden añadir manos al modelo oficial: solo tenemos el archivo compilado, no el original editable.

Las fases 1 a 6 sirven igual con un modelo nuevo: el motor de capas usa los nombres estándar de parámetros de Live2D.

**Estado (27-oct): fases 1 a 6 hechas.** Motor en `app/src/motion.ts`, conducta en `app/src/behavior.ts`, labios en
`app/src/live2d.ts`; tiempos de palabra de edge-tts en `core/tts.py`. Para probar gestos: abrir la app con `?anim` (o
`localStorage.mikuDebug = "1"`), teclas `1`-`0`, `q`-`p`, `n`, `m` = gestos (con Mayúscula, en espejo) y `a`-`l`, `;`,
`z`, `x` = emociones. Hallazgo al implementarlo: los valores por defecto del modelo no son una pose de reposo (brazo
izquierdo abierto, derecho pegado, sonrisa al máximo); el reposo se fija en `REST` de `motion.ts`.

## 4. Orden y esfuerzo

| Fase | Qué | Esfuerzo |
|---|---|---|
| 1 | Sin seguir el mouse, borrar RetrynowMiku | Pequeño |
| 2 | Motor de capas: ambiente, parpadeo, mirada, emoción, gestos | Mediano: la base |
| 3 | Conducta por estado (escuchar, pensar, hablar, despedirse...) | Mediano |
| 4 | Más emociones y personalidad | Pequeño-mediano |
| 5 | Labios con tiempos de palabra | Mediano |
| 6 | Entrada y salida | Pequeño |
| 7 | Modelo con manos (opcional) | Grande / comprar o encargar |

Recomendado: 1 → 2 → 3 (aquí ya se nota muchísimo) → 6 → 4 → 5. La 7 solo si tras la 3 sigue faltando.

## Fuentes
- pixi-live2d-display, movimientos y expresiones: https://guansss.github.io/pixi-live2d-display/motions_expressions
- Prioridades y movimientos en paralelo: https://github.com/RaSan147/pixi-live2d-display/blob/master/README.md
- Ken Perlin, ruido y mirada: https://blog.kenperlin.com/?p=7650
- Capas de ambiente en personajes (Idle Weaver): https://forums.unrealengine.com/t/araz-creates-idle-weaver-procedural-npc-motion-and-behaviour-system/2839748
- Parpadeo y respiración (Life Spark): https://www.renderhub.com/oldhiccup/life-spark
- Cabeza y asentimientos al hablar (AAMAS): https://ifaamas.csc.liv.ac.uk/Proceedings/aamas2009/pdf/01_Full%20Papers/05_25_FP_0592.pdf
- Mirada y turnos de palabra (MIT): https://www.media.mit.edu/gnl/publications/cassell_torres_prevost_97.pdf
- Retroalimentación no verbal del oyente: https://www.cs.utep.edu/nigel/feedback/pdf/P15novick.pdf
- Labios por vocales (CRI LipSync en Live2D): https://blog.criware.com/?p=4745
- Términos de las muestras de Live2D: https://www.live2d.com/en/learn/sample/model-terms/
- Licencia de personaje de Crypton (resumen): https://otakumode.com/otapedia/vocaloid/hatsune_miku/piapro
