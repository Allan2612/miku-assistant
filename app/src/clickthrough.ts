/**
 * Click-through management with hit-testing against Live2D model bounds.
 * Complies with ARCHITECTURE.md: ~150ms check only while visible, completely stopped when hidden.
 */

import { getCurrentWindow } from "@tauri-apps/api/window";
import { live2d } from "./live2d";

export class ClickthroughController {
  private timer: number | null = null;
  private isIgnoringCursor: boolean = false;
  private lastX: number = -1;
  private lastY: number = -1;
  private isTauriAvailable: boolean = false;

  constructor() {
    this.isTauriAvailable =
      typeof window !== "undefined" &&
      Boolean((window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__);

    // Track mouse coordinate within viewport for hit-testing
    window.addEventListener(
      "mousemove",
      (e) => {
        this.lastX = e.clientX;
        this.lastY = e.clientY;
      },
      { passive: true }
    );
  }

  /**
   * Start 150ms polling interval. Only runs while Miku is visible.
   */
  start(): void {
    if (this.timer !== null) return;

    // Default to ignoring cursor outside model
    this.setIgnore(true);

    this.timer = window.setInterval(() => {
      this.checkHit();
    }, 150);
  }

  /**
   * Stop polling interval completely when Miku is hidden (0% CPU impact).
   */
  stop(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    // Release ignore cursor state when hidden
    this.setIgnore(false);
  }

  private checkHit(): void {
    if (this.lastX < 0 || this.lastY < 0) return;

    // 1. Check if cursor is over interactive HTML UI elements (speech bubble, chat input, toggle button)
    let hitUI = false;
    try {
      const el = document.elementFromPoint(this.lastX, this.lastY);
      if (el) {
        hitUI = Boolean(
          el.closest(
            ".miku-speech-bubble, .miku-input-bar, .miku-chat-toggle-btn, button, input"
          )
        );
      }
    } catch (_) {}

    // 2. Check if cursor is over Live2D model body
    const hitModel = live2d.hitTest(this.lastX, this.lastY);
    const hit = hitUI || hitModel;

    if (hit && this.isIgnoringCursor) {
      // Cursor is over Miku or UI -> enable clicks
      this.setIgnore(false);
    } else if (!hit && !this.isIgnoringCursor) {
      // Cursor is in empty space -> pass-through clicks to Windows desktop
      this.setIgnore(true);
    }
  }

  private setIgnore(ignore: boolean): void {
    this.isIgnoringCursor = ignore;
    if (this.isTauriAvailable) {
      try {
        getCurrentWindow().setIgnoreCursorEvents(ignore);
      } catch (err) {
        console.warn("[Clickthrough] Failed to set ignoreCursorEvents:", err);
      }
    }
  }
}

export const clickthrough = new ClickthroughController();
