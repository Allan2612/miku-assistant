use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            // Position main window bottom-right on desktop
            if let Some(window) = app.get_webview_window("main") {
                if let Ok(Some(monitor)) = window.current_monitor() {
                    let mon_pos = monitor.position();
                    let mon_size = monitor.size();
                    let scale = monitor.scale_factor();
                    let win_w = (420.0 * scale) as i32;
                    let win_h = (620.0 * scale) as i32;
                    let margin = (12.0 * scale) as i32;
                    let x = mon_pos.x + mon_size.width as i32 - win_w - margin;
                    let y = mon_pos.y + mon_size.height as i32 - win_h - margin;
                    let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition::new(x, y)));
                }
            }

            // Build Tray Menu: Mostrar / Ocultar / Salir
            let show_i = MenuItem::with_id(app, "show", "Mostrar", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "Ocultar", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &hide_i, &quit_i])?;

            let default_icon = app.default_window_icon().cloned();
            let mut tray_builder = TrayIconBuilder::new().menu(&menu).show_menu_on_left_click(false);
            if let Some(icon) = default_icon {
                tray_builder = tray_builder.icon(icon);
            }

            let tray = tray_builder
                .on_menu_event(|app, event| match event.id.as_ref() {
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
                    "quit" => {
                        std::process::exit(0);
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
