# Runbook para un agente: preparar una PC nueva para desarrollar Miku

Eres un agente de programación (por ejemplo, Claude Code) en una PC con Windows 10/11. El usuario quiere seguir
desarrollando Miku Assistant aquí y te pide que lo dejes todo listo, de principio a fin, sin que él tenga que hacer
nada técnico. Sigue los pasos en orden. Cada paso trae cómo comprobar que salió bien: no pases al siguiente si falla.

Al terminar, lee [docs/handoff.md](handoff.md) para tener el contexto del proyecto.

## Reglas

- Háblale al usuario en **español**, con lenguaje sencillo. Dile qué haces en cada paso, en una línea.
- **Instalaciones autorizadas:** el usuario autoriza, solo para esta preparación, instalar con `winget` los programas
  del paso 1 y las librerías de los pasos 4 a 6. Nada más sin preguntarle.
- **Secretos:** el archivo `.env` tiene la API key de Gemini y la contraseña de OBS. **Nunca** muestres su contenido,
  ni lo copies a otro sitio que no sea la carpeta del proyecto, ni lo subas a git (ya está en `.gitignore`).
- **No borres nunca** `cache/core.log*` ni `cache/rvc_worker.log`.
- **No hagas commits ni push** en esta preparación: solo instala y comprueba.
- **Miku apagada por defecto:** enciéndela solo para la prueba del paso 8 y apágala después.
- **Usa PowerShell.** Si un comando falla, lee el error, prueba la solución de la sección «Problemas» y, si no sale,
  para y explícaselo al usuario.

## Datos

- **Repositorio:** https://github.com/Allan2612/miku-assistant, rama **`develop`**.
- **Carpeta del proyecto en esta PC:** `$HOME\Documents\miku-assistant`. Si el usuario quiere otra, usa la suya.
- **Carpeta de traspaso `miku-traspaso`:** la trajo el usuario en una USB o en el Escritorio. Trae:
  - `archivos-del-proyecto\` (`.env`, `config.yaml`, `models\`, `cache\`, `app\public\models\`, `app\public\lib\`);
  - `claude-memory\`;
  - `miku-assistant.bundle` (copia del repositorio, por si no hay acceso a GitHub).

  Búscala así:

  ```powershell
  Get-PSDrive -PSProvider FileSystem | ForEach-Object { Get-ChildItem "$($_.Root)" -Directory -Filter miku-traspaso -ErrorAction SilentlyContinue }
  Get-ChildItem ([Environment]::GetFolderPath('Desktop')) -Directory -Filter miku-traspaso
  ```

  Si no aparece, pregúntale al usuario dónde está. En los pasos de abajo se llama `$T`:

  ```powershell
  $T = 'E:\miku-traspaso'   # la ruta real
  $P = "$HOME\Documents\miku-assistant"
  ```

## 1. Programas

Comprueba qué falta y instala solo eso:

```powershell
foreach ($c in 'git', 'node', 'npm', 'cargo', 'rustup', 'uv') { "{0,-7} {1}" -f $c, [bool](Get-Command $c -ErrorAction SilentlyContinue) }
```

| Falta | Instalar |
|---|---|
| git | `winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements` |
| node / npm | `winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements` |
| rustup / cargo | `winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements` |
| uv | `winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements` |
| Compilador de C++ (lo necesita Rust) | `winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"` |

Para saber si falta el compilador de C++: si `cargo build` del paso 6 falla con `link.exe not found`, instálalo y repite.
WebView2 ya viene con Windows 11. En Windows 10, si la app no abre: `winget install --id Microsoft.EdgeWebView2Runtime -e`.

Después de instalar, **abre una PowerShell nueva**, para que se carguen las rutas.

**Comprobación:** los seis comandos de la tabla dan `True`. Además, `rustup default stable` y `cargo --version`
responden.

## 2. Código

```powershell
if (Test-Path "$P\.git") { git -C $P checkout develop; git -C $P pull } else { git clone -b develop https://github.com/Allan2612/miku-assistant.git $P }
```

Si no hay acceso a GitHub:

```powershell
git clone -b develop "$T\miku-assistant.bundle" $P
git -C $P remote set-url origin https://github.com/Allan2612/miku-assistant.git
```

**Comprobación:** `git -C $P log --oneline -1` muestra `c381665` o un commit más nuevo, y `git -C $P branch --show-current`
dice `develop`.

## 3. Archivos que git no guarda

```powershell
robocopy "$T\archivos-del-proyecto" $P /E /NFL /NDL /NJH /NP
```

`robocopy` devuelve 1 cuando copió archivos: eso es correcto, no un error.

**Comprobación:** existen estos archivos (sin abrir `.env`):

- `$P\.env`
- `$P\models\rvc\miku_diva.pth`
- `$P\models\rvc\rmvpe.pt`
- `$P\models\wakeword\hey_miku.onnx`
- `$P\app\public\lib\live2dcubismcore.min.js`
- `$P\app\public\models\` con el modelo Live2D
- `$P\cache\memory.json`

## 4. Python y librerías

Elige la versión de PyTorch según la tarjeta:

```powershell
cd $P
$nvidia = [bool](Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' })
$idx = if ($nvidia) { 'cu126' } else { 'cpu' }
"NVIDIA: $nvidia -> PyTorch $idx"
uv venv core\.venv --python 3.14
(Get-Content core\requirements.lock) | Where-Object { $_ -notmatch '^(torch|torchaudio)==' } | Set-Content $env:TEMP\req.txt
uv pip install --python core\.venv\Scripts\python.exe -r $env:TEMP\req.txt
uv pip install --python core\.venv\Scripts\python.exe torch torchaudio --index-url "https://download.pytorch.org/whl/$idx"
```

Si el último comando falla porque no hay versión para Python 3.14, usa la nightly:

```powershell
uv pip install --python core\.venv\Scripts\python.exe --pre torch torchaudio --index-url "https://download.pytorch.org/whl/nightly/$idx"
```

**Comprobación:**

```powershell
core\.venv\Scripts\python.exe -c "import torch, faster_whisper, openwakeword, google.genai; print('ok', torch.__version__, torch.cuda.is_available())"
```

Sin NVIDIA es normal que diga `False` al final.

## 5. Modelos de voz y adaptación a esta PC

```powershell
core\.venv\Scripts\python.exe -m core.setup_models --voice
core\.venv\Scripts\python.exe -m core.bench
```

- `setup_models` descarga Whisper y ContentVec, unos 1,2 GB.
- `core.bench` mide la PC y elige el Whisper adecuado. Anota lo que dice su última línea (`"@@{…}"`), que trae:
  - `audio_s`: lo que dura la frase de prueba;
  - `whisper.seconds`: cuánto tarda Whisper en entenderla;
  - `voice.device` y `voice.seconds`: dónde corre la voz y cuánto tarda;
  - `voice.extra_s`: cuántos segundos más tarda cada respuesta.

  Se lo dirás al usuario.

**Comprobación:** existe `cache\bench.json` y `core.bench` termina con un `"state": "done"`.

## 6. App de escritorio

```powershell
cd $P\app
npm install
npx tauri build --no-bundle
cd $P
```

La primera vez tarda unos 10 minutos: Rust descarga y compila todo.

**Comprobación:** existe `$P\app\src-tauri\target\release\miku.exe`.

## 7. Tests

```powershell
cd $P
$fail = 0
foreach ($t in Get-ChildItem tests\test_*.py) {
  $last = core\.venv\Scripts\python.exe -m "tests.$($t.BaseName)" 2>&1 | Select-Object -Last 1
  if ("$last" -ne 'ok') { $fail++; "FALLA $($t.BaseName): $last" }
}
"fallos: $fail"
cd app; npx tsc --noEmit; cd ..
```

**Comprobación:** `fallos: 0` y `tsc` no muestra errores. El 4-nov pasaban los 28 en la PC original. Si alguno falla,
anota cuál y el error para el usuario. No cambies código para que pase.

## 8. Prueba de humo (y volver a apagarla)

```powershell
cd $P
cmd /c start.bat
Start-Sleep -Seconds 40
Select-String -Path cache\core.log -Pattern 'Miku Core is active|WakeWord listener started|ERROR' | Select-Object -Last 5
cmd /c stop.bat
```

**Comprobación:**

- el log muestra `Miku Core is active` y `WakeWord listener started` de esta hora, sin `ERROR` nuevos;
- después de `stop.bat` no queda `miku.exe` (`Get-Process miku -ErrorAction SilentlyContinue` no devuelve nada).

## 9. Memoria de Claude Code

Si eres Claude Code, tu carpeta de proyecto ya existe: `%USERPROFILE%\.claude\projects\` tiene una subcarpeta
terminada en `-miku-assistant`. Copia la memoria allí:

```powershell
$proj = Get-ChildItem "$HOME\.claude\projects" -Directory | Where-Object { $_.Name -like '*miku-assistant' } | Select-Object -First 1
New-Item -ItemType Directory -Force "$($proj.FullName)\memory" | Out-Null
Copy-Item "$T\claude-memory\*" "$($proj.FullName)\memory\" -Force
```

**Comprobación:** existe `memory\MEMORY.md` en esa carpeta.

## 10. Informe al usuario

Dile, en español y en pocas líneas:

1. Qué instalaste.
2. El resultado de los tests.
3. Los números de `core.bench`: cuánto tarda en entender y cuántos segundos más tarda su voz por respuesta.
4. Lo que le toca a él:
   - **Panel › Configuración:**
     - elegir el **micrófono** de esta PC;
     - revisar la **pantalla** de Miku;
     - revisar el **umbral** de «Hey Miku». Viene en 0,2, muy sensible; para usarla con gente alrededor, 0,35–0,5.
   - **Extensión de Opera:** cargarla desde `browser-extension\` (ver su README), si usa Opera en esta PC.
   - **«Hey Miku» reentrenado:** si lo reentrenó en la otra PC, copiar `cache\wake\hey_miku.onnx` desde allá.
   - **Trabajar en las dos PCs:**
     - el código va por git en `develop` (`git pull` al empezar; commit y push al terminar);
     - los datos (`.env`, `cache\`, `models\`) no van por git.
   - **La memoria USB:** borrar de ella la carpeta `miku-traspaso`, porque lleva la API key.

## Problemas

| Síntoma | Solución |
|---|---|
| `winget` no existe | Instalar «App Installer» desde Microsoft Store, o descargar los programas de sus webs |
| `uv venv` no encuentra Python 3.14 | `uv python install 3.14` y repetir |
| PyTorch: `No matching distribution` | Usar el comando nightly del paso 4 |
| `link.exe not found` al compilar | Instalar las Build Tools de C++ (tabla del paso 1) y abrir una PowerShell nueva |
| `npx tauri build`: «Acceso denegado» al renombrar `app.exe` | `miku.exe` está abierto: `cmd /c stop.bat` y repetir |
| `start.bat`: «el puerto 8765 está ocupado» | `cmd /c stop.bat` y repetir |
| La app abre en blanco | Faltan `app\public\models\` o `app\public\lib\`: repetir el paso 3 y el paso 6 |
| `setup_models` muy lento o se corta | Repetirlo: retoma lo descargado |
| Un test falla por algo de esta PC (micrófono, monitores) | Anotarlo para el usuario, no tocar el código |
