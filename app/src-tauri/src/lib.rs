mod backend;

use std::sync::Arc;
use std::time::Duration;

use backend::Backend;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            // The frontend positions the window (positionWindow in main.ts) using the work area

            // The backend runs as our child: Task Manager groups it under "Miku Assistant"
            let backend = Arc::new(Backend::new());
            {
                let backend = backend.clone();
                std::thread::spawn(move || {
                    if let Err(e) = backend.start() {
                        eprintln!("[Backend] {e}");
                    }
                });
            }

            // Build Tray Menu: Mostrar / Ocultar / Apagar-Encender / Salir
            let show_i = MenuItem::with_id(app, "show", "Mostrar", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "Ocultar", true, None::<&str>)?;
            let power_i = MenuItem::with_id(app, "power", "Apagar Miku", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &hide_i, &power_i, &quit_i])?;

            let default_icon = app.default_window_icon().cloned();
            let mut tray_builder = TrayIconBuilder::new().menu(&menu).show_menu_on_left_click(false);
            if let Some(icon) = default_icon {
                tray_builder = tray_builder.icon(icon);
            }

            let tray = tray_builder
                .on_menu_event(move |app, event| match event.id.as_ref() {
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
                        let (backend, power_i) = (backend.clone(), power_i.clone());
                        if backend.running() || backend::port_in_use() {
                            // The frontend asks the backend to close itself (releases the mic and the VRAM)
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.emit("tray-action", "stop");
                            }
                            let _ = power_i.set_enabled(false);
                            std::thread::spawn(move || {
                                backend.wait_or_kill(Duration::from_secs(6));
                                let _ = power_i.set_text("Encender Miku");
                                let _ = power_i.set_enabled(true);
                            });
                        } else {
                            std::thread::spawn(move || {
                                match backend.start() {
                                    Ok(()) => {
                                        let _ = power_i.set_text("Apagar Miku");
                                    }
                                    Err(e) => eprintln!("[Backend] {e}"),
                                }
                            });
                        }
                    }
                    "quit" => {
                        // Let the frontend tell the backend to shut down before we exit (H-050)
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("tray-action", "quit");
                        }
                        let backend = backend.clone();
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
