mod backend;

use std::sync::Arc;
use std::time::Duration;

use backend::Backend;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WindowEvent, Wry,
};

/// The backend and the tray item that turns it on and off: shared by the tray and the panel.
struct Power {
    backend: Arc<Backend>,
    item: MenuItem<Wry>,
}

fn backend_on(app: &AppHandle) -> bool {
    app.state::<Power>().backend.running() || backend::port_in_use()
}

/// Blocking: call it from a thread. The frontend asks the backend to close itself (mic and VRAM released).
fn stop_backend(app: &AppHandle) {
    let power = app.state::<Power>();
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit("tray-action", "stop");
    }
    let _ = power.item.set_enabled(false);
    power.backend.wait_or_kill(Duration::from_secs(6));
    let _ = power.item.set_text("Encender Miku");
    let _ = power.item.set_enabled(true);
    let _ = app.emit("backend-changed", false);
}

fn start_backend(app: &AppHandle) -> Result<(), String> {
    let power = app.state::<Power>();
    power.backend.start()?;
    let _ = power.item.set_text("Apagar Miku");
    let _ = app.emit("backend-changed", true);
    Ok(())
}

fn open_panel(app: &AppHandle) {
    if let Some(panel) = app.get_webview_window("panel") {
        let _ = panel.unminimize();
        let _ = panel.show();
        let _ = panel.set_focus(); // the user opened it: taking the focus is what they asked for
    }
}

#[tauri::command]
fn backend_state(app: AppHandle) -> bool {
    backend_on(&app)
}

#[tauri::command]
async fn backend_start(app: AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || start_backend(&app)).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn backend_stop(app: AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || stop_backend(&app)).await.map_err(|e| e.to_string())
}

fn settings(app: &AppHandle, args: &[&str], input: &str) -> Result<String, String> {
    app.state::<Power>().backend.run_module("core.settings", args, input)
}

#[tauri::command]
async fn settings_get(app: AppHandle) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || settings(&app, &["get"], "")).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn settings_set(app: AppHandle, changes: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || settings(&app, &["set"], &changes)).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn settings_tools(app: AppHandle) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || settings(&app, &["tools"], "")).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn settings_inputs(app: AppHandle) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || settings(&app, &["inputs"], "")).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn settings_testobs(app: AppHandle, password: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || settings(&app, &["testobs"], &password)).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn settings_testkey(app: AppHandle, key: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || settings(&app, &["testkey"], &key)).await.map_err(|e| e.to_string())?
}

/// Installed and not set up yet: the panel shows the first-start wizard instead of the sections.
#[tauri::command]
fn setup_state(app: AppHandle) -> serde_json::Value {
    let backend = &app.state::<Power>().backend;
    serde_json::json!({ "installed": backend.installed(), "ready": backend.ready() })
}

/// The first start (installer/setup.ps1): each progress line goes to the panel as a "setup-progress" event; at the
/// end Miku starts.
#[tauri::command]
async fn setup_run(app: AppHandle, api_key: String, city: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let backend = app.state::<Power>().backend.clone();
        backend.run_setup(&api_key, &city, |line| {
            let _ = app.emit("setup-progress", line.to_string());
        })?;
        start_backend(&app)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// After saving settings: the backend reads config.yaml and .env only when it starts.
#[tauri::command]
async fn backend_restart(app: AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        if backend_on(&app) {
            stop_backend(&app);
        }
        start_backend(&app)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// docs/funciones.md, for the Funciones page (only that file).
#[tauri::command]
fn read_functions_doc(app: AppHandle) -> Result<String, String> {
    let root = app.state::<Power>().backend.root().ok_or("No encuentro la carpeta de Miku")?.to_path_buf();
    std::fs::read_to_string(root.join("docs").join("funciones.md")).map_err(|e| e.to_string())
}

// ---------- wake word clips (cache/wake): listen and label them, for retraining "Hey Miku" ----------

const CLIP_FOLDERS: [&str; 3] = ["", "near", "silent"];

fn wake_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    Ok(app.state::<Power>().backend.data().join("cache").join("wake"))
}

/// "20261103-122416_0.984.wav" in a known folder: a clip name from the panel is never a path.
fn clip_key(folder: &str, name: &str) -> Option<String> {
    let b = name.as_bytes();
    let digits = |r: std::ops::Range<usize>| b[r].iter().all(u8::is_ascii_digit);
    let ok = CLIP_FOLDERS.contains(&folder)
        && b.len() == 25
        && digits(0..8)
        && b[8] == b'-'
        && digits(9..15)
        && b[15] == b'_'
        && digits(16..17)
        && b[17] == b'.'
        && digits(18..21)
        && &name[21..] == ".wav";
    ok.then(|| if folder.is_empty() { name.to_string() } else { format!("{folder}/{name}") })
}

fn read_json(path: &std::path::Path) -> serde_json::Map<String, serde_json::Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}

#[tauri::command]
fn wake_clips(app: AppHandle) -> Result<serde_json::Value, String> {
    let dir = wake_dir(&app)?;
    let labels = read_json(&dir.join("labels.json"));
    let heard = read_json(&dir.join("heard.json"));
    let suggested = read_json(&dir.join("suggested.json")); // how each activation turned out (core/pipeline.py)
    let mut clips = Vec::new();
    for folder in CLIP_FOLDERS {
        let Ok(entries) = std::fs::read_dir(if folder.is_empty() { dir.clone() } else { dir.join(folder) }) else { continue };
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if let Some(key) = clip_key(folder, &name) {
                clips.push(serde_json::json!({
                    "folder": folder, "name": name,
                    "label": labels.get(&key).cloned().unwrap_or(serde_json::Value::Null),
                    "heard": heard.get(&key).cloned().unwrap_or(serde_json::Value::Null),
                    "suggest": suggested.get(&key).cloned().unwrap_or(serde_json::Value::Null),
                }));
            }
        }
    }
    clips.sort_by(|a, b| b["name"].as_str().cmp(&a["name"].as_str())); // newest first
    Ok(serde_json::json!({ "clips": clips }))
}

/// The clip's WAV bytes, as an ArrayBuffer for the panel's audio player.
#[tauri::command]
fn wake_clip_audio(app: AppHandle, folder: String, name: String) -> Result<tauri::ipc::Response, String> {
    clip_key(&folder, &name).ok_or("Clip no válido")?;
    let dir = wake_dir(&app)?;
    let path = if folder.is_empty() { dir.join(&name) } else { dir.join(&folder).join(&name) };
    std::fs::read(path).map(tauri::ipc::Response::new).map_err(|e| e.to_string())
}

/// "yes" (it was the user), "no" (it was not), or nothing to clear the mark. Kept in cache/wake/labels.json.
#[tauri::command]
fn wake_label(app: AppHandle, folder: String, name: String, label: Option<String>) -> Result<(), String> {
    let key = clip_key(&folder, &name).ok_or("Clip no válido")?;
    let path = wake_dir(&app)?.join("labels.json");
    let mut labels = read_json(&path);
    match label.as_deref() {
        Some(l @ ("yes" | "no")) => labels.insert(key, serde_json::Value::String(l.to_string())),
        _ => labels.remove(&key),
    };
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, serde_json::Value::Object(labels).to_string()).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, &path).map_err(|e| e.to_string())
}

/// Whether there are enough marks (and PyTorch) to retrain "Hey Miku": {"ready", "yours", "marks", "torch"}.
#[tauri::command]
async fn wake_train_state(app: AppHandle) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || app.state::<Power>().backend.run_module("core.train_wakeword", &["--check"], ""))
        .await
        .map_err(|e| e.to_string())?
}

/// Retrains "Hey Miku" with the marks ("train-progress" events); a running Miku restarts to load the new model.
#[tauri::command]
async fn wake_train(app: AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let backend = app.state::<Power>().backend.clone();
        backend.run_train(|line| {
            let _ = app.emit("train-progress", line.to_string());
        })?;
        if backend_on(&app) {
            stop_backend(&app);
            start_backend(&app)?;
        }
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

// ---------- Logs: read by Rust, so they show with Miku off too; never written or deleted here ----------

/// core.log and its rotated copies, oldest first (core.log.3 … core.log).
fn log_files(app: &AppHandle) -> Vec<std::path::PathBuf> {
    let cache = app.state::<Power>().backend.data().join("cache");
    (1..=3).rev().map(|i| cache.join(format!("core.log.{i}"))).chain([cache.join("core.log")]).filter(|p| p.is_file()).collect()
}

/// `lines` lines of the log ending `skip` lines before its end, across the rotated copies: the panel opens with
/// the newest and asks for older ones on demand. `offset` is where log_tail goes on from.
#[tauri::command]
fn read_log(app: AppHandle, lines: usize, skip: usize) -> Result<serde_json::Value, String> {
    let files = log_files(&app);
    let mut all = String::new();
    for f in &files {
        all.push_str(&String::from_utf8_lossy(&std::fs::read(f).map_err(|e| e.to_string())?));
    }
    let every: Vec<&str> = all.lines().collect();
    let end = every.len().saturating_sub(skip);
    let start = end.saturating_sub(lines.min(5000));
    let offset = files.last().and_then(|f| f.metadata().ok()).map_or(0, |m| m.len());
    Ok(serde_json::json!({ "text": every[start..end].join("\n"), "more": start > 0, "offset": offset }))
}

/// What core.log gained since `offset` (whole lines only). `reset`: the log rotated, read it again from the end.
#[tauri::command]
fn log_tail(app: AppHandle, offset: u64) -> Result<serde_json::Value, String> {
    use std::io::{Read, Seek, SeekFrom};
    let path = app.state::<Power>().backend.data().join("cache").join("core.log");
    let mut file = std::fs::File::open(&path).map_err(|e| e.to_string())?;
    let len = file.metadata().map_err(|e| e.to_string())?.len();
    if len < offset {
        return Ok(serde_json::json!({ "reset": true }));
    }
    file.seek(SeekFrom::Start(offset)).map_err(|e| e.to_string())?;
    let mut bytes = Vec::new();
    file.take(4 * 1024 * 1024).read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    let whole = bytes.iter().rposition(|&b| b == b'\n').map_or(0, |i| i + 1); // a half-written line waits
    Ok(serde_json::json!({ "text": String::from_utf8_lossy(&bytes[..whole]), "offset": offset + whole as u64 }))
}

// ---------- Almacenamiento (core/storage.py) and opening Miku's folders ----------

#[tauri::command]
async fn storage_scan(app: AppHandle) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || app.state::<Power>().backend.run_module("core.storage", &["scan"], ""))
        .await
        .map_err(|e| e.to_string())?
}

/// Frees the voice cache or the speech models Miku no longer uses: core/storage.py refuses anything else.
#[tauri::command]
async fn storage_clean(app: AppHandle, what: String) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || app.state::<Power>().backend.run_module("core.storage", &["clean", &what], ""))
        .await
        .map_err(|e| e.to_string())?
}

/// Opens one of Miku's folders in Explorer, by name: the panel never passes a path.
#[tauri::command]
fn open_folder(app: AppHandle, which: String) -> Result<(), String> {
    let backend = &app.state::<Power>().backend;
    let data = backend.data().to_path_buf();
    let root = backend.root().map(|r| r.to_path_buf()).ok_or("No encuentro la carpeta de Miku")?;
    let hub = std::env::var_os("HF_HUB_CACHE").map(std::path::PathBuf::from).unwrap_or_else(|| {
        std::env::var_os("HF_HOME").map(std::path::PathBuf::from).unwrap_or_else(|| {
            std::path::PathBuf::from(std::env::var_os("USERPROFILE").unwrap_or_default()).join(".cache").join("huggingface")
        }).join("hub")
    });
    let dir = match which.as_str() {
        "data" => data,
        "logs" => data.join("cache"),
        "wake" => data.join("cache").join("wake"),
        "voice" => data.join("cache").join("voice"),
        "models" => root.join("models"),
        "program" => root,
        "runtime" => backend.runtime(),
        "speech" | "unused" => hub,
        _ => return Err("Carpeta desconocida".into()),
    };
    if !dir.is_dir() {
        return Err("Esa carpeta no existe todavía".into());
    }
    std::process::Command::new("explorer").arg(&dir).spawn().map(|_| ()).map_err(|e| e.to_string())
}

// ---------- one Miku at a time ----------

/// A second miku.exe (opened again by hand, or autostart plus start.bat) asks the first one to open its panel and
/// leaves: two tray icons and two backends fighting for the port helped nobody.
const INSTANCE_PORT: u16 = 8766;
const INSTANCE_HELLO: &[u8] = b"miku-panel\n";
const INSTANCE_OK: &[u8] = b"ok";

/// The listener when this is the first Miku; exits the process when another one answered.
fn single_instance() -> Option<std::net::TcpListener> {
    use std::io::{Read, Write};
    match std::net::TcpListener::bind(("127.0.0.1", INSTANCE_PORT)) {
        Ok(listener) => Some(listener),
        Err(_) => {
            // The port is taken: only leave if it really is Miku that answers (another program could use it)
            if let Ok(mut s) = std::net::TcpStream::connect(("127.0.0.1", INSTANCE_PORT)) {
                let _ = s.set_read_timeout(Some(Duration::from_secs(1)));
                let mut reply = [0u8; 2];
                if s.write_all(INSTANCE_HELLO).is_ok() && s.read_exact(&mut reply).is_ok() && reply == INSTANCE_OK {
                    std::process::exit(0);
                }
            }
            None
        }
    }
}

fn serve_instance(app: AppHandle, listener: std::net::TcpListener) {
    use std::io::{Read, Write};
    std::thread::spawn(move || {
        for mut stream in listener.incoming().flatten() {
            let mut hello = [0u8; 11];
            let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
            if stream.read_exact(&mut hello).is_ok() && hello == INSTANCE_HELLO {
                let _ = stream.write_all(INSTANCE_OK);
                open_panel(&app);
            }
        }
    });
}

// ---------- start with Windows ----------

const RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
const RUN_NAME: &str = "Miku Assistant";

/// The Startup-folder shortcut install_autostart.bat used to make (development): replaced by the Run entry.
fn old_startup_shortcut() -> Option<std::path::PathBuf> {
    std::env::var_os("APPDATA").map(|a| {
        std::path::PathBuf::from(a).join(r"Microsoft\Windows\Start Menu\Programs\Startup\MikuAssistant.lnk")
    })
}

fn reg(args: &[&str]) -> bool {
    use std::os::windows::process::CommandExt;
    std::process::Command::new("reg")
        .args(args)
        .creation_flags(0x0800_0000)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

#[tauri::command]
fn autostart_get() -> bool {
    reg(&["query", RUN_KEY, "/v", RUN_NAME]) || old_startup_shortcut().is_some_and(|p| p.is_file())
}

/// On: Windows starts this miku.exe with --tray (only the tray icon) at sign-in. Off: removes it.
#[tauri::command]
fn autostart_set(enabled: bool) -> Result<bool, String> {
    if let Some(old) = old_startup_shortcut() {
        let _ = std::fs::remove_file(old);
    }
    if enabled {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let value = format!("\"{}\" --tray", exe.display());
        if !reg(&["add", RUN_KEY, "/v", RUN_NAME, "/t", "REG_SZ", "/d", &value, "/f"]) {
            return Err("Windows no dejó guardar el arranque automático".into());
        }
    } else {
        reg(&["delete", RUN_KEY, "/v", RUN_NAME, "/f"]);
    }
    Ok(autostart_get())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let instance = single_instance();
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            backend_state, backend_start, backend_stop, backend_restart, read_log, log_tail, read_functions_doc,
            settings_get, settings_set, settings_tools, settings_testkey, wake_clips, wake_clip_audio, wake_label, wake_train_state, wake_train,
            setup_state, setup_run, autostart_get, autostart_set, settings_inputs, settings_testobs, storage_scan, storage_clean, open_folder
        ])
        .setup(|app| {
            // The frontend positions the window (positionWindow in main.ts) using the work area

            // Build Tray Menu: Panel / Mostrar / Ocultar / Apagar-Encender / Salir
            let panel_i = MenuItem::with_id(app, "panel", "Abrir panel", true, None::<&str>)?;
            let show_i = MenuItem::with_id(app, "show", "Mostrar", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "Ocultar", true, None::<&str>)?;
            let power_i = MenuItem::with_id(app, "power", "Apagar Miku", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&panel_i, &show_i, &hide_i, &power_i, &quit_i])?;

            // The backend runs as our child: Task Manager groups it under "Miku Assistant"
            app.manage(Power { backend: Arc::new(Backend::new()), item: power_i });
            {
                let app = app.handle().clone();
                std::thread::spawn(move || {
                    if let Err(e) = start_backend(&app) {
                        eprintln!("[Backend] {e}");
                    }
                });
            }

            // The panel hides instead of closing: Miku keeps running in the tray
            if let Some(panel) = app.get_webview_window("panel") {
                let hidden = panel.clone();
                panel.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = hidden.hide();
                    }
                });
                // Opened by hand: the panel shows. Started with Windows (--tray): only the tray icon
                if !std::env::args().any(|a| a == "--tray") {
                    open_panel(app.handle());
                }
            }

            let default_icon = app.default_window_icon().cloned();
            let mut tray_builder = TrayIconBuilder::new().menu(&menu).show_menu_on_left_click(false);
            if let Some(icon) = default_icon {
                tray_builder = tray_builder.icon(icon);
            }

            let tray = tray_builder
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "panel" => open_panel(app),
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                            let _ = window.emit("tray-action", "show");
                        }
                    }
                    "hide" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("tray-action", "hide");
                        }
                    }
                    "power" => {
                        let app = app.clone();
                        std::thread::spawn(move || {
                            if backend_on(&app) {
                                stop_backend(&app);
                            } else if let Err(e) = start_backend(&app) {
                                eprintln!("[Backend] {e}");
                            }
                        });
                    }
                    "quit" => {
                        // Let the frontend tell the backend to shut down before we exit (H-050)
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("tray-action", "quit");
                        }
                        let backend = app.state::<Power>().backend.clone();
                        std::thread::spawn(move || {
                            backend.wait_or_kill(Duration::from_secs(5));
                            std::process::exit(0);
                        });
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("tray-action", "toggle");
                        }
                    }
                })
                .build(app)?;

            app.manage(tray);
            if let Some(listener) = instance {
                serve_instance(app.handle().clone(), listener);
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event {
                api.prevent_exit();
            }
        });
}
