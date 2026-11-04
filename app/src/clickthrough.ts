/**
 * Click-through management with hit-testing against Live2D model bounds.
 * Complies with docs/architecture.md: ~150ms check only while visible, completely stopped when hidden.
 */

import { getCurrentWindow, cursorPosition } from "@tauri-apps/api/window";
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

  private checking = false;

  /**
   * Cursor in page coordinates. While the window ignores cursor events it receives no
   * mousemove at all, so in Tauri the global cursor position is read instead (H-047).
   */
  private async cursorInPage(): Promise<[number, number]> {
    if (!this.isTauriAvailable) return [this.lastX, this.lastY];
    const win = getCurrentWindow();
    const [cur, pos, scale] = await Promise.all([cursorPosition(), win.innerPosition(), win.scaleFactor()]);
    return [(cur.x - pos.x) / scale, (cur.y - pos.y) / scale];
  }

  private async checkHit(): Promise<void> {
    if (this.checking) return;
    this.checking = true;
    try {
      const [x, y] = await this.cursorInPage();
      if (this.timer === null) return; // stopped while awaiting
      const inside = x >= 0 && y >= 0 && x <= window.innerWidth && y <= window.innerHeight;

      // 1. Cursor over the speech bubble
      const el = inside ? document.elementFromPoint(x, y) : null;
      const hitUI = Boolean(el?.closest(".miku-speech-bubble, .miku-chat"));

      // 2. Cursor over the Live2D model body
      const hit = hitUI || (inside && live2d.hitTest(x, y));

      if (hit && this.isIgnoringCursor) {
        this.setIgnore(false);
      } else if (!hit && !this.isIgnoringCursor) {
        this.setIgnore(true);
      }
    } catch (err) {
      console.warn("[Clickthrough] hit check failed:", err);
    } finally {
      this.checking = false;
    }
  }

  private setIgnore(ignore: boolean): void {
    this.isIgnoringCursor = ignore;
    if (this.isTauriAvailable) {
      getCurrentWindow()
        .setIgnoreCursorEvents(ignore)
        .catch((err) => console.warn("[Clickthrough] Failed to set ignoreCursorEvents:", err));
    }
  }
}

export const clickthrough = new ClickthroughController();
