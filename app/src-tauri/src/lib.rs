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

/// The last `lines` lines of cache/core.log, read from the file: the panel shows them with Miku off too.
#[tauri::command]
fn read_log(app: AppHandle, lines: usize) -> Result<String, String> {
    let root = app.state::<Power>().backend.root().ok_or("No encuentro la carpeta de Miku")?.to_path_buf();
    let text = std::fs::read(root.join("cache").join("core.log")).map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&text);
    let all: Vec<&str> = text.lines().collect();
    Ok(all[all.len().saturating_sub(lines.min(2000))..].join("\n"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![backend_state, backend_start, backend_stop, read_log])
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
