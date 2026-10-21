/**
 * Miku Assistant - Desktop Orchestrator
 * Controls Live2D model, global shortcut, bottom-right window positioning,
 * barge-in interruption, click reactions, and 0% CPU/GPU resource freezing.
 */

import { getCurrentWindow, currentMonitor } from "@tauri-apps/api/window";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { listen } from "@tauri-apps/api/event";
import { register, unregisterAll } from "@tauri-apps/plugin-global-shortcut";
import { live2d } from "./live2d";
import { animations } from "./animations";
import { clickthrough } from "./clickthrough";
import { ws, ServerMessage } from "./ws";
import { ui } from "./ui";

// Compile-time injected config from config.yaml
declare const __APP_CONFIG__: {
  hotkey?: string;
  language?: string;
  window?: {
    width?: number;
    height?: number;
    anchor?: string;
    margin?: number;
    fps_visible?: number;
  };
  behavior?: {
    hide_after_seconds?: number;
    max_record_seconds?: number;
    silence_ms?: number;
    unload_after_minutes?: number;
  };
  live2d?: {
    model?: string;
    scale?: number;
    expressions?: Record<string, string | null>;
  };
};

const config = typeof __APP_CONFIG__ !== "undefined" ? __APP_CONFIG__ : {};
const windowCfg = config.window || {};
const live2dCfg = config.live2d || {};
const behaviorCfg = config.behavior || {};

const WIDTH = windowCfg.width || 420;
const HEIGHT = windowCfg.height || 620;
const MARGIN = windowCfg.margin ?? 12;
const FPS_VISIBLE = windowCfg.fps_visible || 30;
const HOTKEY = config.hotkey || "Ctrl+Alt+M";
const HIDE_AFTER_SECONDS = behaviorCfg.hide_after_seconds || 20;

let isVisible = false;
let autoHideTimer: number | null = null;
const isTauri =
  typeof window !== "undefined" &&
  Boolean((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__);

if (isTauri) {
  document.body.classList.add("tauri");
}

/**
 * Anchor the window perfectly to the bottom-right corner of the desktop work area
 * (excluding the Windows taskbar so Miku is never clipped or hidden behind it).
 */
async function positionWindow(): Promise<void> {
  if (!isTauri) return;
  try {
    const currentWin = getCurrentWindow();
    const monitor = await currentMonitor();
    if (monitor) {
      const scaleFactor = monitor.scaleFactor || 1;

      // Use workArea if available: exactly reflects usable desktop excluding taskbar/docks
      const workX = monitor.workArea ? monitor.workArea.position.x : monitor.position.x;
      const workY = monitor.workArea ? monitor.workArea.position.y : monitor.position.y;
      const workW = monitor.workArea ? monitor.workArea.size.width : monitor.size.width;
      const workH = monitor.workArea ? monitor.workArea.size.height : monitor.size.height;

      // Get exact physical dimensions of the window
      const winSize = await currentWin.outerSize();
      const physicalW = winSize.width > 0 ? winSize.width : Math.round(WIDTH * scaleFactor);
      const physicalH = winSize.height > 0 ? winSize.height : Math.round(HEIGHT * scaleFactor);

      const marginPx = Math.round(MARGIN * scaleFactor);

      // Anchor to bottom-right corner within work area
      const posX = Math.round(workX + workW - physicalW - marginPx);
      const posY = Math.round(workY + workH - physicalH - marginPx);

      await currentWin.setPosition(new PhysicalPosition(posX, posY));
      console.log(
        `[Window] Positioned bottom-right at (${posX}, ${posY}) within workArea (${workW}x${workH}, scale: ${scaleFactor})`
      );
    }
  } catch (err) {
    console.warn("[Window] Could not position window automatically:", err);
  }
}

export function resetAutoHideTimer(): void {
  if (autoHideTimer) {
    clearTimeout(autoHideTimer);
    autoHideTimer = null;
  }
  if (!isVisible) {
    return;
  }
  autoHideTimer = window.setTimeout(() => {
    console.log(`[Auto-hide] ${HIDE_AFTER_SECONDS}s of inactivity reached. Auto-hiding Miku.`);
    hideMiku();
  }, HIDE_AFTER_SECONDS * 1000);
}

export function clearAutoHideTimer(): void {
  if (autoHideTimer) {
    clearTimeout(autoHideTimer);
    autoHideTimer = null;
  }
}

function handleServerMessage(msg: ServerMessage): void {
  switch (msg.type) {
    case "show":
      showMiku();
      break;
    case "hide":
      hideMiku();
      break;
    case "stop_speaking":
      live2d.stopSpeaking();
      ui.clearSubtitle();
      break;
    case "state":
      if (msg.value === "listening") {
        clearAutoHideTimer();
        ui.showListening();
      } else if (msg.value === "thinking") {
        clearAutoHideTimer();
        ui.showThinking();
      } else if (msg.value === "idle") {
        resetAutoHideTimer();
      }
      break;
    case "expression":
      live2d.setExpression(msg.name);
      break;
    case "subtitle":
      ui.showSubtitle(msg.who, msg.text, msg.who === "user" ? 3500 : 10000);
      resetAutoHideTimer();
      break;
    case "speak":
      clearAutoHideTimer();
      ui.showSubtitle("miku", msg.text, 15000);
      live2d.setExpression(msg.emotion);
      live2d
        .speak(msg.audio_b64, msg.mime)
        .then((completed) => {
          // Interrupted (barge-in, hide, newer speak): the backend already moved on
          if (!completed) return;
          ws.send({ type: "speak_done" });
          resetAutoHideTimer();
        })
        .catch((err) => {
          console.warn("[Speak] Playback error:", err);
          ws.send({ type: "speak_done" });
          resetAutoHideTimer();
        });
      break;
  }
}

/**
 * Show Miku with appear animation and resume rendering
 */
// A show/hide that arrives mid-animation is applied when the animation ends, not dropped (H-044)
let pendingVisibility: "show" | "hide" | null = null;

function applyPendingVisibility(): void {
  const next = pendingVisibility;
  pendingVisibility = null;
  if (next === "show") showMiku();
  else if (next === "hide") hideMiku();
}

export async function showMiku(): Promise<void> {
  if (animations.isAnimating) {
    pendingVisibility = "show";
    return;
  }
  if (isVisible) return;

  const appEl = document.querySelector<HTMLDivElement>("#app");
  if (!appEl) return;

  if (isTauri) {
    try {
      await positionWindow();
      // No setFocus(): the window is always-on-top, and stealing focus sent type_text
      // into Miku instead of the user's app (H-044)
      await getCurrentWindow().show();
    } catch (err) {
      console.warn("[Window] show error:", err);
    }
  }

  // Resume Pixi ticker (capped at 30 FPS)
  live2d.startTicker();

  // Run appear animation (~600ms)
  await animations.appear(appEl);

  // Activate click-through hit-test loop
  clickthrough.start();
  isVisible = true;

  resetAutoHideTimer();
  console.log("[Miku Assistant] Miku is visible at bottom-right.");
  applyPendingVisibility();
}

/**
 * Hide Miku with disappear animation and completely stop ticker (0% CPU / 0% GPU)
 */
export async function hideMiku(): Promise<void> {
  if (animations.isAnimating) {
    pendingVisibility = "hide";
    return;
  }
  if (!isVisible) return;

  clearAutoHideTimer();
  ui.clearSubtitle();
  live2d.stopSpeaking();

  const appEl = document.querySelector<HTMLDivElement>("#app");
  if (!appEl) return;

  // Immediately stop click-through interval
  clickthrough.stop();

  // Run disappear animation (~500ms)
  await animations.disappear(appEl);

  // Completely freeze Pixi rendering to guarantee 0% GPU usage in background
  live2d.stopTicker();

  if (isTauri) {
    try {
      await getCurrentWindow().hide();
    } catch (err) {
      console.warn("[Window] hide error:", err);
    }
  }

  isVisible = false;
  console.log("[Miku Assistant] Miku is now hidden. Render ticker frozen (0% GPU).");
  applyPendingVisibility();
}

let lastActivateTime = 0;

export async function toggleMiku(): Promise<void> {
  const now = Date.now();
  if (now - lastActivateTime < 800) {
    return;
  }
  lastActivateTime = now;

  // Instant barge-in: stop any active speech immediately
  live2d.stopSpeaking();
  ui.clearSubtitle();

  if (isVisible) {
    ws.send({ type: "activate" });
  } else {
    await showMiku();
    ws.send({ type: "activate" });
  }
}

/**
 * Setup global hotkey (Ctrl+Alt+M) and tray events
 */
async function setupShortcutsAndTray(): Promise<void> {
  if (isTauri) {
    try {
      await unregisterAll();
      await register(HOTKEY, (event) => {
        if (event.state === "Pressed") {
          toggleMiku();
        }
      });
      console.log(`[Hotkey] Registered global shortcut: ${HOTKEY}`);
    } catch (err) {
      console.warn(`[Hotkey] Could not register global shortcut "${HOTKEY}":`, err);
    }

    try {
      await listen<string>("tray-action", (event) => {
        switch (event.payload) {
          case "show":
            showMiku();
            break;
          case "hide":
            hideMiku();
            break;
          case "toggle":
            toggleMiku();
            break;
          case "quit":
            // Stop the Python backend too, or it keeps the mic open after "Salir" (H-050)
            ws.send({ type: "shutdown" });
            break;
        }
      });
    } catch (err) {
      console.warn("[Tray] Could not register tray listener:", err);
    }
  }

  // Fallback keyboard shortcut for browser testing
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "m") {
      e.preventDefault();
      toggleMiku();
    }
  });
}

async function bootstrap(): Promise<void> {
  const canvas = document.querySelector<HTMLCanvasElement>("#live2d-canvas");
  const statusEl = document.querySelector<HTMLDivElement>("#status-indicator");

  if (!canvas) {
    console.error("Canvas element #live2d-canvas not found!");
    return;
  }

  try {
    if (statusEl) statusEl.textContent = "Conectando con Miku Core...";

    // 1. Connect WebSocket to Core backend immediately
    ws.onMessage(handleServerMessage);
    ws.connect();

    // 2. Position window at bottom-right of desktop
    await positionWindow();

    // 3. Initialize Pixi application
    await live2d.init(canvas, WIDTH, HEIGHT, FPS_VISIBLE);

    // 4. Resolve model path from config
    let modelPath = live2dCfg.model || "models/miku_official/miku_sample_t04.model3.json";
    if (!modelPath.startsWith("/") && !modelPath.startsWith("http")) {
      modelPath = "/" + modelPath;
    }

    const scale = live2dCfg.scale || 0.25;
    if (statusEl) statusEl.textContent = "Cargando modelo Live2D...";

    // 5. Load Live2D model with safe-framing
    await live2d.loadModel(modelPath, scale);

    // 6. Setup shortcuts & tray
    await setupShortcutsAndTray();

    // 7. Initialize UI overlay (speech bubble)
    const appEl = document.querySelector<HTMLDivElement>("#app");
    if (appEl) {
      ui.init(appEl);
    }

    // 8. Interactive tap reaction (Fase 8)
    // Clicking Miku triggers a cute reaction motion & smile without distracting text boxes
    let pointerDownPos = { x: 0, y: 0 };
    canvas.addEventListener("pointerdown", (e) => {
      pointerDownPos = { x: e.clientX, y: e.clientY };
    });
    canvas.addEventListener("pointerup", (e) => {
      const dist = Math.hypot(e.clientX - pointerDownPos.x, e.clientY - pointerDownPos.y);
      if (dist < 8 && isVisible) {
        live2d.onTapReaction();
        resetAutoHideTimer();
      }
    });

    // 9. Start visible with appear animation
    await showMiku();

    if (statusEl) {
      statusEl.style.opacity = "0";
      setTimeout(() => statusEl.remove(), 400);
    }

    console.log("[Miku Assistant] Initialized successfully in clean voice-only mode.");
  } catch (err) {
    console.error("[Miku Assistant] Initialization error:", err);
    if (statusEl) {
      statusEl.classList.add("error");
      statusEl.textContent = "Error al iniciar Miku: " + (err instanceof Error ? err.message : String(err));
    }
  }
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}
