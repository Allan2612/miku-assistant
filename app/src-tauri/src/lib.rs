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
    app.state::<Power>().backend.run_settings(args, input)
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

/// The last `lines` lines of cache/core.log, read from the file: the panel shows them with Miku off too.
#[tauri::command]
fn read_log(app: AppHandle, lines: usize) -> Result<String, String> {
    let text = std::fs::read(app.state::<Power>().backend.data().join("cache").join("core.log")).map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&text);
    let all: Vec<&str> = text.lines().collect();
    Ok(all[all.len().saturating_sub(lines.min(2000))..].join("\n"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            backend_state, backend_start, backend_stop, backend_restart, read_log, read_functions_doc,
            settings_get, settings_set, settings_tools, settings_testkey, wake_clips, wake_clip_audio, wake_label,
            setup_state, setup_run
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
