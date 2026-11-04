# Handoff: retomar en una conversación nueva (4-nov)

## El proyecto en pocas líneas

Miku es una asistente de voz para Windows con un personaje Live2D de Hatsune Miku.

- **Backend:** Python asyncio en [core/](../core/).
  1. Oye la palabra clave «Hey Miku» (openWakeWord).
  2. Transcribe con faster-whisper en el procesador.
  3. Pide la respuesta a Gemini, con un bucle de agente sobre 46 herramientas del PC ([core/tools/](../core/tools/)).
  4. Habla con edge-tts convertido a la voz de Miku por RVC, en un subproceso: [core/rvc_worker.py](../core/rvc_worker.py).
     Usa la GPU si hay NVIDIA, si no, el procesador.
- **App:** `miku.exe`, hecha con Tauri v2, Rust y TypeScript ([app/](../app/)). Tiene dos ventanas:
  - **Miku en Live2D**, transparente, en la esquina de la pantalla elegida;
  - el **panel de control**, con las páginas Inicio, Recursos, Almacenamiento, Cuotas, Logs, Configuración,
    Herramientas, Funciones, Palabra clave, Recordatorios, Memoria y Chat.
- **Comunicación:**
  - `miku.exe` lanza el backend como proceso hijo.
  - Todo habla por WebSocket en `ws://127.0.0.1:8765`.
  - Una extensión de Opera maneja las pestañas.
- **Instalador NSIS:** para otras PCs. En el primer arranque revisa la PC, descarga Python y las librerías y mide la
  velocidad.
- **Usuarios:** el usuario en su PC, y algunos amigos con el instalador.

Para empezar, lee el [README.md](../README.md), [docs/architecture.md](architecture.md) y
[docs/funciones.md](funciones.md) (todo lo que Miku sabe hacer). Si existe `graphify-out/`, usa `graphify query|path|explain`.

## Preferencias del usuario (siempre)

- Responder en **español**, con lenguaje sencillo.
- **No robar el foco:** suele estar jugando. No abrir ventanas ni reiniciar Miku sin que lo pida.
- **No instalar nada sin que lo pida:** ni paquetes, ni pip, ni npm nuevos.
- **No borrar nunca los logs** (`cache/core.log*`, `cache/rvc_worker.log`): se trabaja con ellos.
- **Commits en `develop`. Push solo cuando lo pida.** Los commits van en inglés (`fix:` / `feat:` / `style:`), con un
  cuerpo que explica el caso real y la línea `Co-Authored-By`.
- **Miku apagada por defecto:** encenderla solo para probar algo y apagarla después (`stop.bat`). Si el usuario la
  tiene abierta, no cerrarla: para recompilar, renombrar el `miku.exe` en uso a `miku.old.exe` y compilar al lado
  (`stop.bat` borra esa copia después).
- **Una sola voz:** con RVC encendido, si la voz falla, la respuesta sale solo como subtítulo, nunca con otra voz.
  Con RVC apagado en la config, habla con la voz base de edge-tts.
- Ahorrar la cuota gratuita de Gemini. La VRAM importa; la RAM no.
- Para lanzar Miku en segundo plano desde una herramienta, usar WMI `Win32_Process Create`: un proceso lanzado desde
  la herramienta muere con la llamada.
- No mencionar el contenido de los títulos de ventanas privadas del navegador que salgan en los logs.
- Las claves (`.env`) nunca se imprimen ni van al instalador.

## Estado (4-nov)

- **Rama `develop`, al día en GitHub.** El último commit es `c381665`, con los ajustes del usuario: pantalla 1 y
  umbral 0,2.
- **Pruebas y compilación:** los 28 módulos de test pasan. `npm run build` y `npx tauri build` compilan, y el instalador
  está en `app/src-tauri/target/release/bundle/nsis/`.
- **Otra PC, sin NVIDIA:** el usuario va a seguir desarrollando allí.
  - En su Escritorio está `miku-traspaso\`, con lo que git ignora (`.env`, `models/`, `cache/`, Live2D) y la memoria
    de Claude Code.
  - El runbook para que un agente prepare esa PC es [docs/agente-nueva-pc.md](agente-nueva-pc.md).

### Qué se hizo el 3 y 4 de noviembre

- **Panel e instalador:** fases 1 a 5 de [docs/plan-panel-instalador.md](plan-panel-instalador.md), y además:
  - una sola instancia (TCP 127.0.0.1:8766);
  - arrancar con Windows (HKCU Run, `--tray`);
  - atajo y micrófono desde el panel;
  - pantalla de Miku (`window.monitor`);
  - cuadro de texto bajo Miku (`window.chat`, apagado por defecto).
- **Rediseño de UI/UX del panel** ([docs/plan-panel-ux.md](plan-panel-ux.md)):
  - paginación y una sola barra de scroll por página;
  - gráficos con escala, eje de tiempo y valor al pasar el ratón;
  - página Almacenamiento ([core/storage.py](../core/storage.py));
  - la pantalla de carga es el ecualizador de Miku;
  - la barra de guardar flota y solo aparece con cambios;
  - «Deshacer» al borrar;
  - aviso de cambios sin guardar;
  - sin música.
- **Cuota de Gemini:**
  - **Google cuenta también las peticiones que fallan**, así que se cuenta cada envío ([core/quota.py](../core/quota.py)).
  - Los modelos agotados se saltan.
  - Gemma (14.400 al día) va antes que los de 20 al día ([config.yaml](../config.yaml)).
  - Una acción sencilla que sale bien no pide una segunda petición (`FINAL_TOOLS` en [core/llm.py](../core/llm.py)).
  - El tiempo de espera es 10 s, **el mínimo que acepta la API**: con 8 s fallaba todo, y un test lo vigila.
- **Activaciones falsas de «Hey Miku»:**
  - **El modelo es débil.** En el log, de 186 activaciones solo 52 traían «Miku», y la puntuación no separa las reales
    de las falsas. Subir el umbral no lo arregla.
  - Cada activación anota si fue real o falsa en `cache/wake/suggested.json` ([core/pipeline.py](../core/pipeline.py),
    `_wake_was_real`), y Palabra clave las ofrece como marcas.
  - «Adiós», «No» o «Nada» después de un clip sin «Miku» la ocultan en silencio.
  - Botón «Reentrenar» ([core/train_wakeword.py](../core/train_wakeword.py)): instala el modelo nuevo en
    `cache/wake/hey_miku.onnx` solo si es mejor.
    - Probado con los clips reales en modo prueba: llamadas detectadas de 4/6 a 5/6, falsas de 18/40 a 2/40.
    - **Falta que el usuario acepte las sugerencias y pulse Reentrenar.**
  - El micrófono del usuario graba bajo (unos −27 dB): el panel sube los clips al reproducirlos.
- **Instalador para PCs sin NVIDIA:**
  - el asistente revisa la PC ([installer/check.ps1](../installer/check.ps1));
  - instala PyTorch para procesador, así que su voz y reentrenar funcionan;
  - mide la velocidad al final ([core/bench.py](../core/bench.py)) y elige Whisper `small` o `base`;
  - deja elegir su voz o la voz rápida.
  - Medido aquí con la tarjeta oculta: la voz en procesador tarda 2,9 s para una frase de 3,9 s.
  - Con `MIKU_FORCE_CPU=1`, [installer/setup.ps1](../installer/setup.ps1) hace como si no hubiera NVIDIA.
- **Otros cambios:**
  - `core.log` lleva la fecha en cada línea (`2026-11-03 17:21:28.359 [INFO] …`);
  - los recordatorios suenan aunque el PC se haya suspendido.

## Cómo se trabaja aquí

- **Tests:** `core\.venv\Scripts\python.exe -m tests.<módulo>`, que imprime `ok`. Todos de una vez (bash):
  `for f in tests/test_*.py; do core/.venv/Scripts/python.exe -m tests.$(basename $f .py) 2>&1 | tail -1; done`
- **Frontend:** `cd app && npx tsc --noEmit && npm run build`. Para la app: `npx tauri build` (o `--no-bundle` sin el
  instalador).
- **Revisar el panel sin la app real:**
  - `npx vite preview --port 4173` y `playwright-cli` (Edge, sin ventana);
  - con `page.routeWebSocket` para simular el backend y `__TAURI_INTERNALS__` para simular `invoke`;
  - capturas a 1240×800 y 980×640.
- **Frase mal entendida en un log:** se corrige en [core/intent.py](../core/intent.py) y se añade una línea a la tabla
  de [tests/test_intent.py](../tests/test_intent.py).
- **Logs:**
  - `cache/core.log`: las peticiones salen como `--> [GEMINI REQ #n] Model: ...`;
  - `cache/wake/`: clips, `labels.json` (marcas del usuario), `suggested.json` y `heard.json`.
- **CHANGELOG.md:** cada cambio lleva una línea en `[Unreleased]`, en español.

### Trampas conocidas

- **No hacer grep recursivo sobre `core/`:** entra en `core/.venv` y se cuelga. Acotar o excluir `.venv`.
- **Barras invertidas en ediciones con heredoc o Python:** se convierten en caracteres reales (`\b` pasa a ser el byte
  0x08, `\n` un salto de línea). Para líneas con `\` usar Edit, y después buscar caracteres de control.
- **En Windows, una variable de entorno vacía equivale a no tenerla.** Para ocultar la GPU en una prueba:
  `CUDA_VISIBLE_DEVICES=-1`.
- **`npx tauri build` falla con «Acceso denegado» al renombrar `app.exe`:** `miku.exe` está en uso. Renombrar el que
  corre a `miku.old.exe` y compilar de nuevo.
- **`location.reload` no se puede sustituir** en las pruebas del panel.
- **En los mocks de `settings_get` hay que incluir todos los campos** (`monitor`, `window_chat`, …). Si falta uno, el
  panel cree que hay cambios sin guardar y frena la navegación.

## Pendiente / ideas para seguir

- **Lo hace el usuario:**
  - aceptar las sugerencias en Palabra clave y reentrenar;
  - probar el instalador en la PC sin NVIDIA y anotar los números de `bench`;
  - revisar en la app real lo que solo se probó simulado: pantalla de Miku, cuadro de texto, Almacenamiento y
    «Liberar», marcado con teclado, pantallas de carga;
  - subir el nivel del micrófono en Windows.
- **El umbral 0,2 está en el repo**, así que los instaladores nuevos salen con él: es muy sensible. Valorar volver a
  0,35 cuando el modelo esté reentrenado.
- **Partes que ninguna auditoría revisó:**
  - `rvc_worker.py`, `infer_pack/` y `rmvpe.py`;
  - `stt.py`, `state.py` y `screen.py`;
  - `motion.ts`, `behavior.ts` y `animations.ts`.
- **Fase E** de [docs/plan-siguiente.md](plan-siguiente.md): prueba en vivo de la herramienta `windows`.
- **Siguiente ronda de logs:** frases mal clasificadas, órdenes perdidas, activaciones falsas tras reentrenar.
