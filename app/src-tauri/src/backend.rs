//! The Python backend as a child of miku.exe, so Task Manager groups it under "Miku Assistant".
//!
//! No Job Object: one that holds the real interpreter (the venv's pythonw.exe is only a launcher, and killing it
//! leaves the interpreter running) would also kill every app Miku opened for the user when she closes. Instead the
//! backend watches this process (MIKU_PARENT_PID) and shuts itself down when it is gone; the RVC worker exits when
//! the backend's pipe closes.

use std::net::{SocketAddr, TcpStream};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const PORT: u16 = 8765;

pub struct Backend {
    root: Option<PathBuf>,
    child: Mutex<Option<Child>>,
}

/// The project folder: the first ancestor of miku.exe that holds core/__main__.py.
fn find_root() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    exe.ancestors().find(|dir| dir.join("core").join("__main__.py").is_file()).map(Path::to_path_buf)
}

pub fn port_in_use() -> bool {
    TcpStream::connect_timeout(&SocketAddr::from(([127, 0, 0, 1], PORT)), Duration::from_millis(300)).is_ok()
}

impl Backend {
    pub fn new() -> Self {
        Backend { root: find_root(), child: Mutex::new(None) }
    }

    /// Ours and still alive.
    pub fn running(&self) -> bool {
        let mut child = self.child.lock().unwrap();
        match child.as_mut().map(|c| c.try_wait()) {
            Some(Ok(None)) => true,
            _ => {
                *child = None;
                false
            }
        }
    }

    /// Starts the backend unless one is already serving the port (started by hand with start.bat, for example).
    pub fn start(&self) -> Result<(), String> {
        if self.running() || port_in_use() {
            return Ok(());
        }
        let root = self.root.as_ref().ok_or("No encuentro la carpeta de Miku (core/__main__.py)")?;
        let python = root.join("core").join(".venv").join("Scripts").join("pythonw.exe");
        let child = Command::new(&python)
            .args(["-m", "core"])
            .current_dir(root)
            .env("PYTHONPATH", root)
            .env("MIKU_PARENT_PID", std::process::id().to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("No pude lanzar {}: {e}", python.display()))?;
        *self.child.lock().unwrap() = Some(child);
        Ok(())
    }

    /// Waits up to `timeout` for the backend to exit after it was asked to (the frontend sends "shutdown").
    /// Still alive: kills the interpreter itself (its PID is in cache/core.pid), never its children, so the apps
    /// Miku opened stay open; the RVC worker exits on its own when the pipe closes.
    pub fn wait_or_kill(&self, timeout: Duration) {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if !self.running() && !port_in_use() {
                return;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        // Only while a backend still serves the port: it wrote core.pid when it started, so the PID is its own
        // (a stale file from a crash could name any other program)
        if let (Some(root), true) = (&self.root, port_in_use()) {
            if let Ok(pid) = std::fs::read_to_string(root.join("cache").join("core.pid")) {
                let _ = Command::new("taskkill")
                    .args(["/PID", pid.trim(), "/F"])
                    .creation_flags(CREATE_NO_WINDOW)
                    .status();
            }
        }
        if let Some(mut child) = self.child.lock().unwrap().take() {
            let _ = child.kill(); // the venv launcher
            let _ = child.wait();
        }
    }
}
