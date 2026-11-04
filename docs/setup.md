# Preparación (lo que hace el usuario, no el agente)

## Instalar Miku en otra PC (instalador)

Para tus PCs y las de amigos de confianza. El instalador lleva la voz MikuDiva y el modelo Live2D, que son de
terceros: no lo publiques.

1. **Generarlo** (en esta PC, con Miku cerrada): en `app/`, `npx tauri build`. Sale en
   `app/src-tauri/target/release/bundle/nsis/Miku Assistant_<versión>_x64-setup.exe` (~220 MB).
2. **Instalarlo:** Windows avisará de "editor desconocido" (no está firmado): *Más información › Ejecutar de todas
   formas*. Se instala para el usuario actual, sin pedir administrador, en `%LOCALAPPDATA%\Programs\Miku Assistant`.
3. **Primer arranque:** el panel revisa la PC («Tu PC»: gráficos, procesador, RAM, disco, micrófono, internet), pide
   la API key de Gemini (puede dejarse para después) y la ciudad, y descarga Python, las librerías y los modelos. Hace
   falta internet esa vez.
   - **Con NVIDIA:** PyTorch con CUDA, unos 4 GB de descarga y unos 6,5 GB en disco. Su voz va en la tarjeta.
   - **Sin NVIDIA** (gráficos integrados): PyTorch para el procesador, unos 2 GB de descarga y unos 3,5 GB en disco.
     Funciona todo, también su voz y reentrenar «Hey Miku», pero cada respuesta tarda unos segundos más.
   - Al final mide la PC (`core/bench.py`): elige Whisper `small` o `base` y dice cuánto tarda su voz. Sin NVIDIA deja
     elegir entre su voz y la voz rápida (la base de edge-tts, al instante).
   - Para probar el camino sin NVIDIA en una PC que la tiene: `MIKU_FORCE_CPU=1` al lanzar `installer/setup.ps1`.
4. **Dónde queda cada cosa:**
   - el programa (código, modelos): la carpeta de instalación;
   - Python y las librerías: `%LOCALAPPDATA%\Miku Assistant\runtime` (se borra al desinstalar);
   - tus datos (ajustes, `.env`, memoria, recordatorios, logs): `%APPDATA%\Miku Assistant` (se conservan al
     desinstalar o actualizar).
5. **Extensión de Opera:** está en la carpeta de instalación, `browser-extension` (ver su README).

En desarrollo (esta carpeta, con `core/.venv`) nada de eso cambia: `start.bat` y `stop.bat` siguen igual, y los datos
siguen en `cache/`, `config.yaml` y `.env` del proyecto.

## Software
- Windows 10/11 con el driver NVIDIA al día (RTX 3050, 8 GB)
- **Python 3.11** (marcar "Add to PATH")
- **Node.js LTS** (20 o superior)
- **Rust** (`rustup`) + **Microsoft C++ Build Tools** (requisito de Tauri). WebView2 ya viene en Windows 11
- **Git**
- Para `faster-whisper`: corre en CPU (`int8`) por defecto para ahorrar VRAM y evitar procesos fantasma de CUDA, por lo que no requiere instalar librerías extra de NVIDIA para la Fase 4.
- Para RVC (Fase 6): PyTorch con CUDA (el agente indicará el comando exacto de instalación).

## Claves
- API key de Gemini: Google AI Studio → "Get API key". Copiar `.env.example` a `.env` y pegarla.
- La capa gratuita tiene límites por minuto y por día; para uso personal suele bastar.

## Recursos que debes conseguir tú (no van al repo)
1. **Modelo Live2D de Miku** en formato Cubism 3/4 (`*.model3.json` con texturas, `.moc3`, motions y expressions). También sirve Cubism 2 (`*.model.json`). Respeta los términos de su autor. Ponlo en `app/public/models/<nombre>/` y ajusta la ruta en `config.yaml`.
   - *Consejo de recursos:* Si las texturas `.png` del modelo miden 4096×4096 px, redimensiónalas a 2048×2048 px para ahorrar hasta 100 MB de RAM en WebView2 sin pérdida visual a tamaño de escritorio.
2. **Cubism Core**: descarga el "Cubism SDK for Web" de la web oficial de Live2D y copia `live2dcubismcore.min.js` a `app/public/lib/`.
3. **Modelo RVC de Miku** (`.pth` y, si tiene, `.index`) en `models/rvc/`. Fase 6.
   - También hace falta **`models/rvc/rmvpe.pt`** (estimador de tono de RVC). Sin él, RVC falla y Miku usa la voz base de edge-tts.
   - La primera vez que arranca RVC se descargan de Hugging Face **ContentVec** (`lengyue233/content-vec-best`, unos cientos de MB) y el modelo de **Whisper**: el primer uso necesita internet y puede tardar un par de minutos.
4. **(Opcional) Wake word** `hey_miku.onnx` entrenado con el notebook de openWakeWord, en `models/wakeword/`. Fase 7.
5. **OBS (opcional):** para clips y grabación por voz, activa en OBS Herramientas → Ajustes del servidor WebSocket y
   pon la contraseña en `.env` como `OBS_PASSWORD=...`. Para los clips, configura el búfer de repetición en Ajustes → Salida.

## Cómo trabajar con Gemini CLI
1. Crea la carpeta `miku-assistant/` y copia dentro `GEMINI.md` (en la raíz) y la carpeta `docs/`.
2. Abre una terminal en esa carpeta y ejecuta `gemini`. Gemini CLI lee `GEMINI.md` automáticamente.
3. Primer mensaje sugerido:
   > Lee GEMINI.md y todos los archivos de docs/. Luego haz la Fase 0 del ROADMAP y dime cómo probarla.
4. Tras cada fase, prueba lo que te indique y responde "funciona, sigue con la siguiente fase" o pégale el error.
5. Si Gemini se pierde en una conversación larga, empieza una sesión nueva con:
   > Lee GEMINI.md, docs/ y CHANGELOG.md, y continúa con la siguiente fase pendiente del ROADMAP.

## Comprobar el consumo
- Administrador de tareas → Rendimiento → GPU (memoria dedicada) y pestaña Procesos.
- `nvidia-smi` en terminal para comprobar que cuando Miku lleva inactiva el tiempo configurado, no hay ningún proceso `python` ocupando VRAM.