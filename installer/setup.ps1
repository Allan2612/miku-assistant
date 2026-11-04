# Miku Assistant - first start. Downloads Python, Miku's libraries and models into the runtime folder
# (%LOCALAPPDATA%\Miku Assistant\runtime) and prepares the user's data folder (%APPDATA%\Miku Assistant).
# Run by miku.exe (setup_run), which shows the progress in the panel: every "@@{json}" line is one step.
#
# Environment: MIKU_PROGRAM (install folder), MIKU_HOME (data), MIKU_RUNTIME (runtime), MIKU_API_KEY, MIKU_CITY.
# MIKU_DRY_RUN=1: checks the folders, the GPU and the download URLs, and installs nothing.
# MIKU_FORCE_CPU=1: as if there were no NVIDIA card (to test the CPU install on a PC that has one).
# Windows PowerShell 5.1 (the one every Windows has).

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest's progress bar makes it many times slower
$utf8 = New-Object Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8                   # text piped into python.exe (the city may have accents)

$program = $env:MIKU_PROGRAM
$data = $env:MIKU_HOME
$runtime = $env:MIKU_RUNTIME
$dry = $env:MIKU_DRY_RUN -eq '1'
$venv = Join-Path $runtime '.venv'
$py = Join-Path $venv 'Scripts\python.exe'
$uvDir = Join-Path $runtime 'uv'
$uv = Join-Path $uvDir 'uv.exe'
$uvUrl = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
$env:UV_CACHE_DIR = Join-Path $runtime 'uv-cache'
$env:UV_LINK_MODE = 'copy'
$env:PYTHONPATH = $program
$env:PYTHONIOENCODING = 'utf-8'

function Say([string]$step, [string]$state, [int]$pct, [string]$msg) {
  $o = [ordered]@{ step = $step; state = $state; pct = $pct; msg = $msg }
  [Console]::Out.WriteLine('@@' + ($o | ConvertTo-Json -Compress))
}

# A native program, its output passed on as log lines. Its stderr (uv's progress) must not stop the script:
# with 'Stop', Windows PowerShell 5.1 turns the first stderr line into an error
function Run([string]$step, [string]$exe, [string[]]$argList) {
  $ErrorActionPreference = 'Continue'
  & $exe @argList 2>&1 | ForEach-Object { [Console]::Out.WriteLine([string]$_) }
  if ($LASTEXITCODE -ne 0) { throw "${step}: $([IO.Path]::GetFileName($exe)) terminó con el código $LASTEXITCODE" }
}

function Text($response) {
  $c = $response.Content
  if ($c -is [byte[]]) { return [Text.Encoding]::ASCII.GetString($c) }
  return [string]$c
}

try {
  foreach ($v in @('MIKU_PROGRAM', 'MIKU_HOME', 'MIKU_RUNTIME')) {
    if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue)) { throw "Falta la variable $v" }
  }

  Say 'data' 'run' 2 'Preparando tu carpeta de datos'
  New-Item -ItemType Directory -Force -Path $data, (Join-Path $data 'cache'), $runtime | Out-Null
  $cfg = Join-Path $data 'config.yaml'
  if (-not (Test-Path $cfg)) { Copy-Item (Join-Path $program 'config.default.yaml') $cfg }
  if ($env:MIKU_API_KEY) {
    $envFile = Join-Path $data '.env'
    $lines = @()
    if (Test-Path $envFile) { $lines = @(Get-Content $envFile | Where-Object { $_ -notmatch '^GEMINI_API_KEY=' }) }
    $lines += "GEMINI_API_KEY=$($env:MIKU_API_KEY)"
    [IO.File]::WriteAllLines($envFile, [string[]]$lines, $utf8)  # no BOM: python-dotenv would read it as part of the name
  }
  Say 'data' 'done' 4 ''

  $nvidia = [bool](Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' }) -and $env:MIKU_FORCE_CPU -ne '1'
  Say 'gpu' 'done' 5 $(if ($nvidia) { 'NVIDIA' } else { 'none' })
  # Without an NVIDIA card her voice and the wake word retraining run on the CPU: the CPU build of PyTorch, so
  # nothing is lost (3-nov: a 4 s phrase took 2.9 s on an 8-core CPU)
  $torchIndex = if ($nvidia) { 'cu126' } else { 'cpu' }

  if ($dry) {
    Say 'uv' 'run' 6 'Comprobando las descargas'
    $sum = (Text (Invoke-WebRequest -Uri "$uvUrl.sha256" -UseBasicParsing)).Trim()
    $torch = Invoke-WebRequest -Uri "https://download.pytorch.org/whl/$torchIndex/torch/" -UseBasicParsing -Method Head
    Say 'done' 'done' 100 "dry run: uv sha256 $($sum.Substring(0, 12))..., PyTorch $torchIndex $($torch.StatusCode)"
    exit 0
  }

  if (-not (Test-Path $uv)) {
    Say 'uv' 'run' 6 'Descargando el instalador de Python (uv)'
    $zip = Join-Path $runtime 'uv.zip'
    Invoke-WebRequest -Uri $uvUrl -OutFile $zip -UseBasicParsing
    $expected = ((Text (Invoke-WebRequest -Uri "$uvUrl.sha256" -UseBasicParsing)).Trim() -split '\s+')[0]
    if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $expected.ToUpper()) { throw 'uv: la descarga no coincide con su suma SHA-256' }
    Expand-Archive -Force $zip $uvDir
    Remove-Item $zip
  }
  Say 'uv' 'done' 10 ''

  if (-not (Test-Path $py)) {
    Say 'python' 'run' 12 'Descargando Python 3.14'
    Run 'python' $uv @('venv', $venv, '--python', '3.14')
  }
  Say 'python' 'done' 18 ''

  Say 'libs' 'run' 20 'Instalando las librerías de Miku (Whisper, Gemini, audio)'
  $req = Join-Path $runtime 'requirements.txt'
  # The exact versions of the working setup, minus PyTorch (only for the voice, and from its own index)
  Get-Content (Join-Path $program 'core\requirements.lock') | Where-Object { $_ -notmatch '^(torch|torchaudio)==' } |
    Set-Content -Encoding ASCII $req
  Run 'libs' $uv @('pip', 'install', '--python', $py, '-r', $req)
  Say 'libs' 'done' 45 ''

  $torchMsg = 'Instalando PyTorch para el procesador: su voz y reentrenar «Hey Miku» (unos 200 MB)'
  if ($nvidia) { $torchMsg = 'Instalando PyTorch con CUDA para la voz de Miku (unos 2,5 GB)' }
  Say 'torch' 'run' 47 $torchMsg
  try {
    Run 'torch' $uv @('pip', 'install', '--python', $py, 'torch', 'torchaudio', '--index-url', "https://download.pytorch.org/whl/$torchIndex")
  } catch {
    # No stable build for this Python yet: the nightly one, like the development setup
    Say 'torch' 'run' 47 'Probando la versión nightly de PyTorch'
    Run 'torch' $uv @('pip', 'install', '--python', $py, '--pre', 'torch', 'torchaudio', '--index-url', "https://download.pytorch.org/whl/nightly/$torchIndex")
  }
  Say 'torch' 'done' 85 ''

  Say 'models' 'run' 87 'Descargando los modelos de voz y de escucha'
  Run 'models' $py @('-m', 'core.setup_models', '--voice')
  Say 'models' 'done' 94 ''

  # The wizard's choices, through the same code the panel uses (it checks them and keeps the comments)
  $changes = @{ rvc_enabled = $true }
  if ($env:MIKU_CITY) { $changes.weather_city = $env:MIKU_CITY }
  $result = ($changes | ConvertTo-Json -Compress) | & $py -m core.settings set
  if ($result -notmatch '"ok": true') { throw "Ajustes: $result" }

  # How fast this PC is: picks the Whisper model and tells the wizard what to expect. Never stops the install
  try { Run 'bench' $py @('-m', 'core.bench') } catch { Say 'bench' 'skip' 99 'No pude medir la velocidad: Miku usa los ajustes normales' }
  Say 'done' 'done' 100 ''
  exit 0
} catch {
  Say 'error' 'error' 0 $_.Exception.Message
  exit 1
}
