/** Pieces every panel page uses: the link to the backend, the shared state and small helpers (pagination, dialogs,
 *  "Deshacer", tooltips, charts). */

declare const __APP_CONFIG__: { live2d?: { model?: string } };

export const isTauri = "__TAURI_INTERNALS__" in window;
export const MODEL = (typeof __APP_CONFIG__ !== "undefined" && __APP_CONFIG__.live2d?.model) || "models/miku_official/miku_sample_t04.model3.json";

// ---------- small helpers ----------
export const esc = (v: unknown): string =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
export const byId = (id: string) => document.getElementById(id);
export const comma = (n: number, d = 1) => n.toFixed(d).replace(".", ",");
export const size = (bytes: number) =>
  bytes >= 1024 ** 3 ? `${comma(bytes / 1024 ** 3)} GB` : bytes >= 1024 ** 2 ? `${Math.round(bytes / 1024 ** 2)} MB` : `${Math.max(bytes ? 1 : 0, Math.round(bytes / 1024))} KB`;
export const icon = (d: string, s = 18) =>
  `<svg aria-hidden="true" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"></path></svg>`;
export const POWER_ICON = "M12 3v8M6.4 7.2a8 8 0 1 0 11.2 0";
export const X_ICON = "M6 6l12 12M18 6 6 18";
/** Today (or another date) as YYYY-MM-DD in the PC's own time zone (toISOString is UTC). */
export const localDay = (d = new Date()) =>
  [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
/** "lun 2 nov" (or "hoy", "ayer") for a YYYY-MM-DD day. */
export function dayLabel(day: string, long = false): string {
  const today = localDay();
  const yesterday = localDay(new Date(Date.now() - 86_400_000));
  if (day === today) return "hoy";
  if (day === yesterday) return "ayer";
  return new Date(`${day}T12:00:00`).toLocaleDateString("es", long ? { weekday: "long", day: "numeric", month: "long" } : { weekday: "short", day: "numeric", month: "short" });
}

/** Writes `html` into `el` only if it changed: a refresh that brings the same data keeps the selection, the scroll
 *  and a click in progress. */
const painted = new WeakMap<Element, string>();
export function paint(el: Element | null, html: string): void {
  if (!el || painted.get(el) === html) return;
  painted.set(el, html);
  el.innerHTML = html;
}

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

  /** A plain message to the backend (a phrase or a chat message as text_input). False if not connected. */
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
/** Shared by every page: whether the backend is on, a power change in progress, what Miku is doing, her hotkey. */
export const state = { backendOn: false, powerBusy: false, speaking: false, activity: "idle", hotkey: "Ctrl+Alt+M" };
/** Set by main.ts (pages call them without importing main): power on/off, go to a page, and a check before leaving
 *  a page with unsaved changes. */
export const actions = {
  power: async (): Promise<void> => {},
  go: (_id: string): void => {},
  leaveGuard: null as null | (() => boolean),
};

export function head(title: string, sub: string, right = ""): string {
  return `<header class="head"><div class="head-text"><h1 id="title">${esc(title)}</h1><p class="sub" id="subtitle">${esc(sub)}</p></div>${right}</header>`;
}

export const offlineNote = () =>
  `<div class="offline">Miku está apagada. <button type="button" class="btn small" data-power>Encender Miku</button></div>`;
/** While something loads: Miku's equalizer dancing, and what is being read (never a bare "Cargando…"). */
const EQ_HEIGHTS = [38, 60, 78, 52, 88, 68, 100, 82, 100, 68, 88, 52, 78, 60, 38];
export const loading = (what: string) =>
  `<div class="loading" role="status"><div class="eqload" aria-hidden="true">${EQ_HEIGHTS.map((h, i) =>
    `<i${i === 3 || i === 11 ? ' class="p"' : ""} style="height:${h}%;--d:${[0.9, 1.15, 0.8, 1.3, 1.0][i % 5]}s;--l:${(i * 0.07).toFixed(2)}s"></i>`).join("")}</div>
    <span class="what">${esc(what)}</span></div>`;

/** A request that got no answer (Miku busy or restarting): say so and offer to try again. */
export const noAnswer = () =>
  `<div class="offline">Miku no respondió. <button type="button" class="btn small ghost" data-retry>Reintentar</button></div>`;

// ---------- pagination ----------
export const pageCount = (total: number, per: number) => Math.max(1, Math.ceil(total / per));
export const clampPage = (page: number, total: number, per: number) => Math.min(Math.max(1, page), pageCount(total, per));
export const pageItems = <T>(list: T[], page: number, per: number) => list.slice((page - 1) * per, page * per);

/** "21–40 de 121 · ‹ 1 … 2 3 4 … 7 ›": buttons with data-pager=name and data-page=n. Empty with a single page. */
export function pager(name: string, total: number, page: number, per: number, noun = ""): string {
  if (total <= per) return "";
  const n = pageCount(total, per);
  const nums = [...new Set([1, page - 1, page, page + 1, n])].filter((p) => p >= 1 && p <= n).sort((a, b) => a - b);
  let pages = "";
  let prev = 0;
  for (const p of nums) {
    if (p - prev > 1) pages += `<span class="gap">…</span>`;
    pages += `<button type="button" data-pager="${name}" data-page="${p}"${p === page ? ' aria-current="page"' : ""} aria-label="Página ${p}">${p}</button>`;
    prev = p;
  }
  const btn = (p: number, label: string, text: string) =>
    `<button type="button" data-pager="${name}" data-page="${p}" aria-label="${label}"${p < 1 || p > n ? " disabled" : ""}>${text}</button>`;
  return `<nav class="pager" aria-label="Páginas"><span class="dim num">${(page - 1) * per + 1}–${Math.min(total, page * per)} de ${total}${noun ? ` ${noun}` : ""}</span>
    <div class="pages">${btn(page - 1, "Página anterior", "‹")}${pages}${btn(page + 1, "Página siguiente", "›")}</div></nav>`;
}

// ---------- dialogs and notices ----------
/** A yes/no question over the page; resolves true only on the confirm button. Escape or a click outside: false. */
export function ask(title: string, text: string, ok = "Sí", danger = false): Promise<boolean> {
  return new Promise((resolve) => {
    const m = document.createElement("div");
    m.className = "modal";
    m.setAttribute("role", "dialog");
    m.setAttribute("aria-modal", "true");
    m.setAttribute("aria-label", title);
    m.innerHTML = `<div><h2>${esc(title)}</h2><p>${esc(text)}</p><div class="row"><button type="button" class="btn ghost" data-a="0">Cancelar</button>
      <button type="button" class="btn${danger ? " danger" : ""}" data-a="1">${esc(ok)}</button></div></div>`;
    const back = document.activeElement as HTMLElement | null;
    const done = (yes: boolean) => {
      m.remove();
      document.removeEventListener("keydown", key, true);
      back?.focus();
      resolve(yes);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        done(false);
      }
    };
    m.onclick = (e) => {
      const b = (e.target as HTMLElement).closest<HTMLElement>("[data-a]");
      if (b) done(b.dataset.a === "1");
      else if (e.target === m) done(false);
    };
    document.addEventListener("keydown", key, true);
    document.body.appendChild(m);
    m.querySelector<HTMLButtonElement>('[data-a="1"]')!.focus();
  });
}

let undoing: { timer: number; run: () => Promise<void> } | null = null;

function toastBox(): HTMLDivElement {
  byId("toast")?.remove();
  const el = document.createElement("div");
  el.id = "toast";
  el.setAttribute("role", "status");
  document.body.appendChild(el);
  return el;
}

/** Deletes in 5 s unless the user presses "Deshacer": `hide` hides the item now, `run` deletes it, `undo` shows it again.
 *  A second one makes the first happen at once. */
export function undoable(text: string, run: () => Promise<void>, undo: () => void): void {
  flushUndo();
  const el = toastBox();
  el.className = "toast";
  el.innerHTML = `<span>${esc(text)}</span><button type="button" class="btn small ghost">Deshacer</button>`;
  const timer = window.setTimeout(flushUndo, 5000);
  undoing = { timer, run };
  el.querySelector("button")!.onclick = () => {
    clearTimeout(timer);
    undoing = null;
    el.remove();
    undo();
  };
}

export function flushUndo(): void {
  const u = undoing;
  if (!u) return;
  undoing = null;
  clearTimeout(u.timer);
  byId("toast")?.remove();
  void u.run();
}

export function toast(text: string): void {
  if (undoing) flushUndo();
  const el = toastBox();
  el.className = "toast plain";
  el.textContent = text;
  window.setTimeout(() => el.isConnected && el.remove(), 3500);
}

// ---------- tooltips: any element with data-tip, and the charts ----------
function tipBox(): HTMLDivElement {
  let el = byId("tip") as HTMLDivElement | null;
  if (!el) {
    el = document.createElement("div");
    el.id = "tip";
    el.className = "tip";
    el.hidden = true;
    document.body.appendChild(el);
  }
  return el;
}

export function showTip(text: string, x: number, y: number): void {
  const el = tipBox();
  el.textContent = text;
  el.hidden = false;
  const w = el.offsetWidth;
  el.style.left = `${Math.min(window.innerWidth - w - 8, Math.max(8, x - w / 2))}px`;
  el.style.top = `${Math.max(8, y - el.offsetHeight - 12)}px`;
}

export const hideTip = () => {
  const el = byId("tip");
  if (el) el.hidden = true;
};

// ---------- line chart: a fixed scale, guides, a time axis and the value under the mouse ----------
export interface Point { t: number; v: number }
const charts = new Map<string, { pts: Point[]; from: number; span: number; fmt: (v: number) => string }>();

/** The smallest of `steps` that holds `top` with some room: the scale only changes in big, readable jumps. */
export const niceMax = (top: number, steps: number[]) => steps.find((s) => s >= top * 1.1) ?? steps[steps.length - 1];

export function lineChart(id: string, pts: Point[], o: { span: number; max: number; color: string; fill: string; fmt: (v: number) => string; label: string }): string {
  const now = Date.now();
  const from = now - o.span;
  const shown = pts.filter((p) => p.t >= from);
  charts.set(id, { pts: shown, from, span: o.span, fmt: o.fmt });
  const X = (t: number) => (((t - from) / o.span) * 100).toFixed(2);
  const Y = (v: number) => (100 - Math.min(1, Math.max(0, v / o.max)) * 100).toFixed(2);
  // A gap of more than 6 s (panel hidden, Miku off) stays a gap: the line never joins over time it did not measure
  const runs: Point[][] = [];
  for (const p of shown) {
    const run = runs[runs.length - 1];
    if (!run || p.t - run[run.length - 1].t > 6000) runs.push([p]);
    else run.push(p);
  }
  const lines = runs
    .filter((r) => r.length > 1)
    .map((r) => {
      const line = r.map((p) => `${X(p.t)},${Y(p.v)}`).join(" ");
      return `<polyline points="${X(r[0].t)},100 ${line} ${X(r[r.length - 1].t)},100" fill="${o.fill}" stroke="none"></polyline>
        <polyline points="${line}" fill="none" stroke="${o.color}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linejoin="round"></polyline>`;
    })
    .join("");
  const guide = (y: number) => `<line x1="0" x2="100" y1="${y}" y2="${y}" stroke="rgba(255,255,255,0.07)" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"></line>`;
  const minutes = Math.round(o.span / 60_000);
  return `<div class="chart" role="img" aria-label="${esc(o.label)}">
    <div class="y"><span>${esc(o.fmt(o.max))}</span><span>${esc(o.fmt(o.max / 2))}</span><span>0</span></div>
    <div class="plot" data-chart="${id}"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${guide(0.5)}${guide(50)}${lines}</svg>
      ${shown.length < 2 ? `<div class="empty">Midiendo… el gráfico se llena en ${minutes} min</div>` : ""}</div>
    <div class="x"><span>hace ${minutes} min</span><span>hace ${minutes / 2} min</span><span>ahora</span></div></div>`;
}

document.addEventListener("mousemove", (ev) => {
  const target = ev.target as HTMLElement;
  const plot = target.closest<HTMLElement>("[data-chart]");
  const tipped = target.closest<HTMLElement>("[data-tip]");
  if (plot) {
    const c = charts.get(plot.dataset.chart!);
    const r = plot.getBoundingClientRect();
    if (!c?.pts.length) return hideTip();
    const t = c.from + ((ev.clientX - r.left) / r.width) * c.span;
    const near = c.pts.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
    if (Math.abs(near.t - t) > 6000) return hideTip();
    const ago = Math.round((Date.now() - near.t) / 1000);
    showTip(`${c.fmt(near.v)}\n${ago < 3 ? "ahora" : `hace ${ago} s`}`, ev.clientX, r.top + 8);
  } else if (tipped) {
    const r = tipped.getBoundingClientRect();
    showTip(tipped.dataset.tip!, r.left + r.width / 2, r.top);
  } else hideTip();
});
