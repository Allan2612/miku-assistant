# Plan: panel de Miku e instalador (3-nov)

## Qué se pide

Del boceto del usuario:

- Una **ventana de Miku** (panel) con una **barra lateral** de secciones y un **área de contenido** a la derecha.
- Las secciones del boceto: configuración (API key, entorno…), cuotas, logs, uso de recursos (estilo dashboard),
  herramientas, funciones, recordatorios y la memoria de lo que recuerda.
- **Encender y apagar a Miku** desde ahí.
- **Estilo Hatsune Miku**, con música y ritmo ("beat").
- En el **Administrador de tareas**, todo lo de Miku bajo un solo nombre, con lo que consume cada proceso.
- Un **instalador**.

Todo es posible. Lo único realmente pesado es el instalador, porque Miku necesita Python y unos 7 GB entre librerías y
modelos (detalles abajo).

## Cómo está hoy

- `start.bat` lanza dos programas sueltos: el backend (`pythonw -m core`) y la app de escritorio
  (`app.exe`). Por eso, en el Administrador de tareas aparecen como "Python", "Python (2)" y la app aparte, sin
  relación entre ellos.
- La app solo tiene la ventana flotante de Miku (transparente, sin bordes) y el icono de la bandeja.
- Todo vive en la carpeta del proyecto: `.env`, `config.yaml`, `cache/` (logs, recordatorios, memoria, cuota).

Tamaños medidos:

| Pieza | Tamaño |
|---|---|
| Python con sus librerías (`core/.venv`) | 5,1 GB (4,1 GB son PyTorch con CUDA, solo para la voz RVC) |
| Modelos de Miku (`models/`: voz RVC, rmvpe, palabra clave) | 255 MB |
| Caché de Hugging Face (Whisper, ContentVec) | 2,0 GB |
| Modelo Live2D | 4 MB |

## La idea

### 1. Un solo programa, "Miku Assistant"

`miku.exe` (la app Tauri, renombrada y con icono propio) pasa a ser el jefe:

- **Lanza el backend como proceso hijo**, sin `start.bat`, dentro de un *Job Object* de Windows: si la app se
  cierra o se cuelga, Windows cierra también el backend y el worker de RVC. Nunca más un Python huérfano con el
  micrófono abierto.
- **Administrador de tareas:** al ser hijos de `miku.exe`, todos salen agrupados como **"Miku Assistant (N)"**: la
  ventana, WebView2, el backend y el worker de RVC, cada uno con su CPU, memoria, disco y GPU. Dentro del grupo
  Python seguirá llamándose "Python" (es el nombre que trae su ejecutable), pero colgando de Miku.
- **Encender / apagar** desde el panel y desde la bandeja: apagar detiene el backend y libera la VRAM; el panel sigue
  abierto. "Salir" lo cierra todo.

### 2. El panel

Una segunda ventana normal (con bordes, en la barra de tareas), además de la Miku flotante. Se abre desde la
bandeja, al abrir `miku.exe` y con un atajo. Habla con el backend por el mismo WebSocket (mensajes nuevos de
consulta); con el backend apagado, lee los archivos directamente (configuración, logs).

Secciones (las del boceto, más las marcadas ★, que propongo):

| Sección | Qué muestra y qué deja hacer |
|---|---|
| ★ **Inicio** | Encender/apagar, estado de cada pieza (backend, voz, palabra clave, extensión de Opera, OBS), modelo de Gemini en uso y si está saturado, últimas cosas que hizo |
| **Configuración** | API key de Gemini (oculta, con botón "probar"), contraseña de OBS, ciudad del clima, palabras de Whisper, atajo, sensibilidad de la palabra clave, voz RVC sí/no, modelos. Guardar reinicia el backend solo |
| **Cuotas** | Peticiones de hoy por modelo contra su límite, hora de renovación, modelos en enfriamiento o saturados (504), historial de 7 días |
| **Logs** | En vivo, con filtros (errores, Gemini, palabra clave, herramientas) y buscador. Solo lectura: nunca borra |
| **Recursos** (dashboard) | CPU, RAM y VRAM de cada proceso de Miku, gráficas de los últimos minutos, GPU total |
| **Herramientas** | Las 46, con su descripción, si son locales o de Gemini, y un interruptor para desactivar alguna |
| **Funciones** | Lo de [funciones.md](funciones.md) con buscador: qué decir para cada cosa, y botón "probar" que se la manda a Miku |
| **Recordatorios** | Lista con cuándo suenan, crear, cancelar; pendientes de notas |
| **Memoria** | Lo que recuerda de ti (editar, borrar) y las conversaciones por día |
| ★ **Palabra clave** | Activaciones de hoy, falsas y "casi disparos", con botón para escuchar cada clip y marcarlo "era yo / no era yo". Con eso se arma, sin grabarte aparte, el material para reentrenar el modelo de "Hey Miku" |
| ★ **Chat** | Escribirle a Miku cuando no puedes hablar (la ventana flotante es solo de voz) |

### 3. Estilo Miku

- Paleta turquesa (#39C5BB) sobre fondo oscuro, con rosa de acento, brillos suaves y tipografía limpia.
- Barra lateral con iconos que se ilumina en la sección activa.
- **"Beat":** un ecualizador de barras que se mueve con la voz de Miku cuando habla, y late suave en reposo.
- **Música:** opcional y apagada por defecto, con un archivo que pongas tú. No puedo incluir canciones de Miku por
  derechos de autor.
- Sin logos oficiales de Crypton: estilo inspirado, no copia de su marca.

### 4. El instalador

Tauri genera un instalador `.exe` (NSIS) con desinstalador, accesos directos y la opción de arrancar con Windows.
El problema es Python: 5 GB de librerías más 2 GB de modelos de Hugging Face. Opciones:

| Opción | Instalador | Pros | Contras |
|---|---|---|---|
| **A. Descarga al primer arranque** (recomendada) | ~60 MB + modelos | Instalador pequeño; el panel muestra el progreso ("Preparando a Miku… 2,3 GB") e instala la versión de PyTorch que toca según la GPU | La primera vez necesita internet y unos 10–20 min |
| B. Todo dentro | 4–6 GB | Funciona sin internet | NSIS no acepta archivos de más de 2 GB: habría que partirlo; compilarlo tarda mucho |
| C. Congelar Python (PyInstaller) | 3–4 GB | Un solo ejecutable del backend | Frágil con PyTorch y el código de RVC; difícil de mantener |

Cambios que necesita cualquier opción:

- **Los datos del usuario se mudan a `%APPDATA%\Miku Assistant`** (`.env`, `config.yaml`, `cache/`): un programa
  instalado en Archivos de programa no puede escribir en su propia carpeta. Al primer arranque se copian los actuales,
  sin borrar nada.
- **Asistente de primera vez:** pide la API key de Gemini (nunca va dentro del instalador), el micrófono y la ciudad.
- **Sin firma digital**, Windows SmartScreen avisará de "editor desconocido" (un certificado cuesta dinero al año).
- **Licencias de los modelos:** el modelo Live2D de muestra y la voz MikuDiva son de terceros. Para tu PC no hay
  problema; para repartir el instalador hay que revisar sus licencias o que cada uno ponga los suyos.

## Diseño aprobado (3-nov)

Maquetas: [Panel de Miku Assistant](https://claude.ai/artifact/KcbsiSFW37d8Qd5aY2MR5n) (lienzo privado, 7 pantallas).
Al usuario le gusta todo. Cambios pedidos:

- **Sin tarjetas dentro de tarjetas:** cada bloque, una sola superficie; el doble borde solo en el bloque principal de
  cada pantalla.
- **Miku dibujada:** el propio modelo Live2D de Miku, animado, en Inicio (saluda, parpadea, reacciona al encender y
  apagar) y en el primer arranque. Sin dibujos de terceros.

## Fase 1 en detalle

1. **`miku.exe` lanza el backend** (`core\.venv\Scripts\pythonw.exe -m core`, sin consola) al abrirse, si el puerto
   8765 está libre. Si ya hay un backend (por ejemplo, lanzado a mano para probar), se conecta a ese.
2. **Job Object** con "matar al cerrar": el backend, el worker de RVC y sus hijos mueren con la app, aunque se cuelgue.
   Con `windows-sys` 0.61.2, que ya está en la caché de Cargo.
3. **Bandeja:** Encender / Apagar Miku. Apagar le pide al backend que se cierre solo (mensaje `shutdown`), espera hasta
   6 s y, si sigue vivo, lo mata con el Job Object. Al apagar, la Miku flotante se oculta.
4. **Nombre:** `productName` "Miku Assistant" y ejecutable `miku.exe`, que es lo que muestra el Administrador de tareas.
5. **`start.bat` y `stop.bat`** solo abren y cierran `miku.exe` (el backend va dentro). Siguen sirviendo de respaldo.

## Fases

Cada fase deja algo usable por sí mismo.

| Fase | Qué | Tamaño |
|---|---|---|
| 1 | `miku.exe` lanza y controla el backend (Job Object), procesos agrupados en el Administrador de tareas, encender/apagar en la bandeja, nombre e icono | Medio |
| 2 | Panel con barra lateral, estilo Miku e Inicio, Logs, Recursos y Cuotas (solo lectura) | Grande |
| 3 | Configuración, Recordatorios, Memoria, Herramientas, Funciones (lectura y escritura) | Grande |
| 4 | Palabra clave (escuchar y etiquetar clips), Chat, ecualizador | Medio |
| 5 | Datos a `%APPDATA%`, asistente de primera vez, instalador NSIS con descarga de Python | Grande |

## Decisiones del usuario (3-nov)

1. **Para quién:** sus PCs y las de amigos de confianza. Asistente de primera vez completo; los modelos de
   terceros (voz MikuDiva, Live2D de muestra) van dentro, pero el instalador no se publica.
2. **Python:** opción A, descarga al primer arranque, con barra de progreso en el panel.
3. **Descargas para compilar:** autorizadas solo las crates de Rust del Job Object y NSIS de Tauri. Nada de pip
   ni npm nuevos.

Consecuencias para el plan:

- Como va a otras PCs, la fase 5 detecta la GPU: con NVIDIA instala PyTorch con CUDA; sin ella, Miku funciona sin
  la voz RVC (solo subtítulos, la regla de una sola voz).
- El micrófono y la ciudad del clima se eligen en el asistente de primera vez, porque cambian de una PC a otra.
