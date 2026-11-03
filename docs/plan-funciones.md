# Plan: ocho funciones nuevas (3-nov)

**Estado (3-nov): las ocho hechas, con tests (22 módulos en verde).** Falta probarlas en vivo: OBS con su
servidor WebSocket activado, un juego a pantalla completa y una descarga real en Opera.

Salen de los logs del 20-oct al 3-nov: 311 de 380 frases fueron a Gemini. Lo que más se pide es manejar
ventanas (23), el reproductor de YouTube (19), poner algo en YouTube (16) y abrir webs (13). Whisper confunde nombres
("Bongame Firestarters, the KDA").

Reglas de siempre: no instalar nada, no robar el foco, cuidar la cuota y la VRAM, una sola voz. Cada función lleva
su test. Las frases locales solo actúan si son la frase entera (lección de la auditoría del 3-nov).

## Orden

1. Vocabulario de Whisper (lo más barato, mejora todo lo demás)
2. Más órdenes locales (medios, YouTube, bloqueo, recordatorios)
3. "¿Qué tengo hoy?"
4. Cuota de Gemini
5. Modo pantalla completa (juegos y videos)
6. OBS por voz
7. Clima
8. Aviso de descargas
9. Docs ([funciones.md](funciones.md), [tools.md](tools.md)) y todos los tests

## 1. Vocabulario de Whisper

- **Qué:** las palabras que más dice el usuario van en el `initial_prompt` de Whisper, que hoy está fijo en
  [core/stt.py](../core/stt.py).
- **Cómo:** `stt.vocabulary` en `config.yaml` → `STTConfig.vocabulary` → `STTManager(initial_prompt=...)`. Por
  defecto, el texto de hoy más K/DA, Firestarter, More, Los Tigres del Norte, OBS y Visual Studio.
- **Cuidado (H-035):** solo palabras sueltas, nunca órdenes enteras: Whisper las "oye" en el ruido.
- **Test:** la config se lee y llega al gestor.

## 2. Más órdenes locales

En `_try_fast_path_tool` ([core/llm.py](../core/llm.py)), con regex de frase entera:

| Frases | Herramienta |
|---|---|
| "Siguiente canción", "Pasa la canción", "La siguiente" | `media_control("next")` |
| "Canción anterior", "Pon la anterior" | `media_control("previous")` |
| "Quita el silencio", "Activa el sonido", "Desmutea" | `mute(False)` |
| "Bloquea el PC / la computadora / la pantalla" | `lock_pc()` |
| "¿Qué recordatorios tengo?", "Mis recordatorios" | `list_timers()` |
| "Sube / baja el volumen del video", "Súbele a YouTube" | `youtube_player("volume_up" / "volume_down")` |
| "Volumen del video al 50" | `youtube_player("volume", "50")` |
| "Silencia el video", "Quita el silencio del video" | `youtube_player("mute" / "unmute")` |
| "Siguiente video" | `youtube_player("next")` |
| "Adelanta 30 segundos", "Regresa 10 segundos" | `youtube_player("forward" / "back", N)` |
| "Pon subtítulos", "Quita los subtítulos" | `youtube_player("captions_on" / "captions_off")` |
| "Ponlo en 1080", "Máxima calidad" | `youtube_player("quality", ...)` |
| "Velocidad 1.5", "Velocidad normal" | `youtube_player("speed", ...)` |
| "Repite el video", "Ponlo en bucle" | `youtube_player("loop")` |

`youtube_player` ya elige el video (el que suena, el que abrió Miku, el activo) y dice si no hay ninguno o si falta
la extensión. Cambian tres esperas de [tests/test_language.py](../tests/test_language.py) que hoy mandan a Gemini
"sube el volumen del video", "silencia el video" y "quita el silencio".

## 3. "¿Qué tengo hoy?"

- **Qué:** recordatorios de hoy (con hora) y pendientes, en una frase hablada. Local.
- **Cómo:** `timers.describe_today()` (los que suenan hoy, también los que se repiten) y una herramienta `my_day`
  en [core/tools/notes.py](../core/tools/notes.py), que también puede llamar Gemini ("¿qué me toca?").
- **Frases:** "¿Qué tengo hoy?", "¿Qué tengo para hoy?", "¿Cómo está mi día?", "Resumen del día", "¿Qué me toca hoy?".
- **Saludo de la mañana:** si hay recordatorios hoy, el saludo los añade ("Hoy tienes: …").
- **Test:** recordatorios de hoy, de mañana y repetidos; sin nada.

## 4. Cuota de Gemini

- **Qué:** cuenta las peticiones de hoy por modelo y las guarda en `cache/quota.json` (sobrevive a reinicios). Solo
  cuenta las que respondieron: una rechazada no gasta cuota.
- **Día de Google:** la cuota diaria se renueva a medianoche del Pacífico (1 o 2 a. m. en Costa Rica). Sin `tzdata`
  instalado, el horario de verano de EE. UU. se calcula a mano (segundo domingo de marzo a primer domingo de noviembre).
- **Límites:** los de [mejoras.md](mejoras.md) (500 al día los flash-lite, 20 los flash, 14 400 Gemma).
- **Aviso:** al llegar al 90 % del modelo principal, la respuesta termina con un aviso, una vez al día.
- **Frases (local):** "¿Cuánta cuota me queda?", "¿Cuántas peticiones llevas?", "¿Cómo va la cuota?". También
  herramienta `quota_status`.
- **Archivo nuevo:** `core/quota.py`. **Test:** día del Pacífico en las fechas de cambio de hora, conteo, aviso
  una sola vez, cambio de día.

## 5. Modo pantalla completa

- **Qué:** con un juego o un video a pantalla completa delante, Miku no aparece (mostrar una ventana encima puede
  minimizar un juego en pantalla completa exclusiva). Sigue escuchando y responde solo con voz.
- **Detección:** `SHQueryUserNotificationState` de Windows (lo mismo que usa "No molestar" de Windows): ocupado por
  pantalla completa, juego Direct3D o modo presentación. Una llamada de microsegundos, sin instalar nada.
- **Cambios:**
  - `pipeline._show()` no manda "show" en ese modo (activación, recordatorios).
  - El saludo de inicio se salta.
  - Frontend: el atajo con Miku oculta ya no la muestra por su cuenta; pide "activate" y el backend decide
    ([app/src/main.ts](../app/src/main.ts)). Sin conexión, la muestra como antes.
- **Test:** con la detección simulada, una activación y un recordatorio no mandan "show" y sí hablan.

## 6. OBS por voz

- **Qué:** clips del replay buffer, grabar, parar y cambiar de escena, por el servidor WebSocket que trae OBS 28+
  (protocolo v5). Con `websockets` (ya instalado), cliente síncrono porque las herramientas corren en hilos.
- **Configuración:** contraseña en `.env` como `OBS_PASSWORD` (nunca en `config.yaml`); `OBS_URL` opcional
  (por defecto `ws://127.0.0.1:4455`).
- **Herramienta `obs(action, scene)`:** `clip` (si el replay buffer está apagado lo enciende y lo dice: el pasado
  no se puede guardar), `record_start`, `record_stop`, `scene` (busca la escena por nombre aproximado).
- **Errores hablados:** OBS cerrado o servidor apagado (y dónde activarlo), contraseña mala, replay buffer no
  configurado, ya estaba grabando, no estaba grabando.
- **Frases (local):** "Guarda eso", "Guarda el clip", "Clip", "Clipéalo"; "Graba", "Empieza a grabar"; "Para la
  grabación", "Deja de grabar"; "Cambia a la escena X".
- **Archivo nuevo:** `core/tools/obs.py`. **Test:** un OBS falso (servidor WebSocket local con contraseña) que
  comprueba la autenticación y las peticiones.

## 7. Clima

- **Qué:** Open-Meteo (gratis, sin clave): ahora, hoy y mañana (temperatura, máxima y mínima, probabilidad de lluvia,
  estado del cielo en español). Ciudad por defecto en `config.yaml → tools.weather_city` ("San José, Costa Rica");
  otra ciudad por Gemini ("¿qué clima hace en Tokio?").
- **Cómo:** `urllib` de la librería estándar, timeout de 4 s; la ciudad se geocodifica una vez por sesión.
- **Frases (local):** "¿Cómo está el clima?", "¿Va a llover hoy?", "¿Qué temperatura hace?", "¿Cómo estará el
  clima mañana?", "¿Va a llover mañana?".
- **Archivo nuevo:** `core/tools/weather.py`. **Test:** respuesta de la API simulada → frase; sin internet → error
  hablado.

## 8. Aviso de descargas

- **Qué:** "Avísame cuando termine la descarga": mira en Descargas los archivos temporales de Opera
  (`.opdownload`), Chrome/Edge (`.crdownload`) y Firefox (`.part`). Cuando desaparece uno, avisa como un
  recordatorio: "¡Terminó la descarga de X!", o "se canceló" si el archivo final no está.
- **Cómo:** un hilo que mira cada 2 s, hasta 4 h. El aviso va por el mismo camino que los recordatorios
  (`timers.announce`), así que respeta el modo pantalla completa y no abre el micrófono.
- **Archivo nuevo:** `core/tools/downloads.py`. **Test:** carpeta temporal con un `.opdownload` que se renombra
  (terminada) y otro que se borra (cancelada).

## Lo que no entra

- Iniciar o parar directos de OBS (un error de Whisper no debe empezar un directo).
- Un modo juego manual: la detección de Windows basta; se añade si falla en la práctica.
- Descargas fuera de la carpeta Descargas.

## Riesgos

- Algunos juegos en ventana sin bordes podrían no marcar a Windows como "ocupado": entonces Miku aparece como hoy.
- Los nombres de los límites de cuota cambian cuando Google cambia de modelos: se ajustan en `core/quota.py`.
- La ciudad del clima es una suposición (Costa Rica): se cambia en `config.yaml`.
