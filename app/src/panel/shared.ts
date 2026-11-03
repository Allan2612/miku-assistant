/** Pieces every panel page uses: the link to the backend, the shared state and small helpers. */

declare const __APP_CONFIG__: { live2d?: { model?: string } };

export const isTauri = "__TAURI_INTERNALS__" in window;
export const MODEL = (typeof __APP_CONFIG__ !== "undefined" && __APP_CONFIG__.live2d?.model) || "models/miku_official/miku_sample_t04.model3.json";

// ---------- small helpers ----------
export const esc = (v: unknown): string =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
export const byId = (id: string) => document.getElementById(id);
export const comma = (n: number, d = 1) => n.toFixed(d).replace(".", ",");
export const size = (bytes: number) => (bytes >= 1024 ** 3 ? `${comma(bytes / 1024 ** 3)} GB` : `${Math.round(bytes / 1024 ** 2)} MB`);
export const icon = (d: string, s = 18) =>
  `<svg aria-hidden="true" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"></path></svg>`;
export const POWER_ICON = "M12 3v8M6.4 7.2a8 8 0 1 0 11.2 0";

// ---------- link to the backend ----------
export type Reply = Record<string, any> | null;

export class BackendLink {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, (data: Reply) => void>();
  private retry: number | null = null;
  onEvent: (msg: Record<string, any>) => void = () => {};
  get open(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  connect(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket("ws://127.0.0.1:8765");
    } catch {
      this.later();
      return;
    }
    this.ws.onopen = () => this.ws?.send(JSON.stringify({ type: "panel_hello" }));
    this.ws.onmessage = (ev) => {
      let msg: Record<string, any>;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "panel_reply") {
        this.pending.get(msg.id)?.(msg.data ?? null);
        this.pending.delete(msg.id);
      } else {
        this.onEvent(msg);
      }
    };
    this.ws.onclose = () => {
      this.ws = null;
      for (const resolve of this.pending.values()) resolve(null);
      this.pending.clear();
      this.later();
    };
  }

  private later(): void {
    if (this.retry) return;
    this.retry = window.setTimeout(() => {
      this.retry = null;
      if (state.backendOn) this.connect();
    }, 2000);
  }

  /** A plain message to the backend (the Funciones page sends a phrase as text_input). False if not connected. */
  send(msg: Record<string, unknown>): boolean {
    if (!this.open) return false;
    this.ws!.send(JSON.stringify(msg));
    return true;
  }

  request(what: string, args: Record<string, unknown> = {}): Promise<Reply> {
    if (!this.open) return Promise.resolve(null);
    const id = this.nextId++;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.ws!.send(JSON.stringify({ type: "panel_get", id, what, args }));
      window.setTimeout(() => {
        if (this.pending.delete(id)) resolve(null);
      }, 5000);
    });
  }
}

export const link = new BackendLink();
/** Shared by every page: whether the backend is on, a power change in progress, Miku talking. */
export const state = { backendOn: false, powerBusy: false, speaking: false };

export function head(eyebrow: string, title: string, sub: string, right = ""): string {
  return `<header class="head"><div class="head-text"><span class="eyebrow">${esc(eyebrow)}</span><h1 id="title">${esc(title)}</h1><p class="sub" id="subtitle">${esc(sub)}</p></div>${right}</header>`;
}

export const offlineNote = () => `<div class="offline">Miku está apagada. Enciéndela desde Inicio o desde su icono de la bandeja.</div>`;
