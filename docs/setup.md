# Preparación (lo que hace el usuario, no el agente)

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
   - Revisa qué expresiones trae (archivos `.exp3.json`) y mapéalas en `config.yaml → live2d.expressions`.
2. **Cubism Core**: descarga el "Cubism SDK for Web" de la web oficial de Live2D y copia `live2dcubismcore.min.js` a `app/public/lib/`.
3. **Modelo RVC de Miku** (`.pth` y, si tiene, `.index`) en `models/rvc/`. Fase 6.
   - También hace falta **`models/rvc/rmvpe.pt`** (estimador de tono de RVC). Sin él, RVC falla y Miku usa la voz base de edge-tts.
   - La primera vez que arranca RVC se descargan de Hugging Face **ContentVec** (`lengyue233/content-vec-best`, unos cientos de MB) y el modelo de **Whisper**: el primer uso necesita internet y puede tardar un par de minutos.
4. **(Opcional) Wake word** `hey_miku.onnx` entrenado con el notebook de openWakeWord, en `models/wakeword/`. Fase 7.

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