//! The Python backend as a child of miku.exe, so Task Manager groups it under "Miku Assistant".
//!
//! No Job Object: one that holds the real interpreter (the venv's pythonw.exe is only a launcher, and killing it
//! leaves the interpreter running) would also kill every app Miku opened for the user when she closes. Instead the
//! backend watches this process (MIKU_PARENT_PID) and shuts itself down when it is gone; the RVC worker exits when
//! the backend's pipe closes.
//!
//! Two layouts. Development: the project folder holds the code, core/.venv and the data (config.yaml, .env,
//! cache/). Installed: the install folder holds the code and the models; Python and the libraries go to
//! %LOCALAPPDATA%\Miku Assistant\runtime (downloaded on the first start, installer/setup.ps1) and the user's data to
//! %APPDATA%\Miku Assistant, so updating or uninstalling the program never touches them (MIKU_HOME).

use std::io::{BufRead, BufReader};
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
    /// config.yaml, .env and cache/
    data: PathBuf,
    /// The virtualenv with Python and Miku's libraries
    venv: PathBuf,
    installed: bool,
    child: Mutex<Option<Child>>,
}

/// The program folder: an ancestor of miku.exe that holds core/__main__.py. One with core/.venv wins: a build copies
/// the code next to target/release/miku.exe too, and that copy must not hide the project folder (it would look like
/// an install that was never set up).
fn find_root() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let with_code: Vec<&Path> = exe.ancestors().filter(|dir| dir.join("core").join("__main__.py").is_file()).collect();
    with_code
        .iter()
        .find(|dir| dir.join("core").join(".venv").is_dir())
        .or_else(|| with_code.first())
        .map(|dir| dir.to_path_buf())
}

fn env_dir(name: &str) -> PathBuf {
    std::env::var_os(name).map(PathBuf::from).unwrap_or_default().join("Miku Assistant")
}

pub fn port_in_use() -> bool {
    TcpStream::connect_timeout(&SocketAddr::from(([127, 0, 0, 1], PORT)), Duration::from_millis(300)).is_ok()
}

impl Backend {
    pub fn new() -> Self {
        let root = find_root();
        let dev_venv = root.as_ref().map(|r| r.join("core").join(".venv"));
        let (installed, data, venv) = match (&root, &dev_venv) {
            (Some(r), Some(v)) if v.join("Scripts").join("pythonw.exe").is_file() => (false, r.clone(), v.clone()),
            _ => (true, env_dir("APPDATA"), env_dir("LOCALAPPDATA").join("runtime").join(".venv")),
        };
        Backend { root, data, venv, installed, child: Mutex::new(None) }
    }

    pub fn root(&self) -> Option<&Path> {
        self.root.as_deref()
    }

    /// Python and the libraries: the virtualenv in development, the whole runtime folder once installed.
    pub fn runtime(&self) -> PathBuf {
        if self.installed { self.venv.parent().map_or_else(|| self.venv.clone(), Path::to_path_buf) } else { self.venv.clone() }
    }

    pub fn data(&self) -> &Path {
        &self.data
    }

    pub fn installed(&self) -> bool {
        self.installed
    }

    /// Python and the libraries are there (installed: after the first start's setup).
    pub fn ready(&self) -> bool {
        self.venv.join("Scripts").join("pythonw.exe").is_file()
    }

    fn python(&self, root: &Path, exe: &str) -> Command {
        let mut cmd = Command::new(self.venv.join("Scripts").join(exe));
        cmd.current_dir(root)
            .env("PYTHONPATH", root)
            .env("PYTHONIOENCODING", "utf-8")
            .env("MIKU_HOME", &self.data)
            .creation_flags(CREATE_NO_WINDOW);
        cmd
    }

    /// `python -m <module> <args>` as a short process (works with Miku off): JSON in on stdin, JSON out.
    /// python.exe, not pythonw.exe: pythonw has no stdout to read the answer from.
    pub fn run_module(&self, module: &str, args: &[&str], input: &str) -> Result<String, String> {
        use std::io::Write;
        let root = self.root.as_ref().ok_or("No encuentro la carpeta de Miku")?;
        if !self.ready() {
            return Err("Miku todavía no está preparada (primer arranque)".into());
        }
        let mut child = self
            .python(root, "python.exe")
            .args(["-m", module])
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("No pude lanzar Python: {e}"))?;
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(input.as_bytes());
        }
        let out = child.wait_with_output().map_err(|e| e.to_string())?;
        if !out.status.success() {
            let err = String::from_utf8_lossy(&out.stderr);
            return Err(err.lines().last().unwrap_or("error de Python").to_string());
        }
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    }

    /// The first start: installer/setup.ps1, its "@@{json}" progress lines passed to `on_line` as they come.
    pub fn run_setup(&self, api_key: &str, city: &str, mut on_line: impl FnMut(&str)) -> Result<(), String> {
        let root = self.root.as_ref().ok_or("No encuentro la carpeta de Miku")?;
        let runtime = self.venv.parent().ok_or("Carpeta de Python no válida")?;
        let child = Command::new("powershell.exe")
            .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
            .arg(root.join("installer").join("setup.ps1"))
            .env("MIKU_PROGRAM", root)
            .env("MIKU_HOME", &self.data)
            .env("MIKU_RUNTIME", runtime)
            .env("MIKU_API_KEY", api_key) // in the environment, never on a command line other programs can read
            .env("MIKU_CITY", city)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null()) // errors come as "@@" lines on stdout; an unread pipe could block the script
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("No pude lanzar PowerShell: {e}"))?;
        follow(child, &mut on_line, "La preparación falló")
    }

    /// Retrains "Hey Miku" (core/train_wakeword.py), its "@@{json}" progress lines passed to `on_line`.
    pub fn run_train(&self, mut on_line: impl FnMut(&str)) -> Result<(), String> {
        let root = self.root.as_ref().ok_or("No encuentro la carpeta de Miku")?;
        let child = self
            .python(root, "python.exe")
            .args(["-m", "core.train_wakeword"])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("No pude lanzar Python: {e}"))?;
        follow(child, &mut on_line, "El entrenamiento falló")
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
        if !self.ready() {
            return Err("Miku todavía no está preparada: termina el primer arranque en el panel".into());
        }
        let child = self
            .python(root, "pythonw.exe")
            .args(["-m", "core"])
            .env("MIKU_PARENT_PID", std::process::id().to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("No pude lanzar Python: {e}"))?;
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
        if port_in_use() {
            if let Ok(pid) = std::fs::read_to_string(self.data.join("cache").join("core.pid")) {
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

/// Reads a child's "@@{json}" progress lines as they come; its last error line is the error if it fails.
fn follow(mut child: std::process::Child, on_line: &mut impl FnMut(&str), failed: &str) -> Result<(), String> {
    let mut last_error = String::new();
    if let Some(out) = child.stdout.take() {
        for line in BufReader::new(out).lines().map_while(Result::ok) {
            if line.contains("\"state\":\"error\"") || line.contains("\"state\": \"error\"") {
                last_error = line.clone();
            }
            on_line(&line);
        }
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err(if last_error.is_empty() { format!("{failed} ({status})") } else { last_error })
    }
}
