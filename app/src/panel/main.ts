/**
 * Miku Assistant panel: the sidebar and the "Estado" pages (Inicio, Recursos, Cuotas, Logs); Almacenamiento lives in
 * storage.ts, the rest in manage.ts and voice.ts.
 * Data: the backend over the WebSocket (panel_hello / panel_get), the log and the on/off switch through Rust.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { live2d } from "../live2d";
import { renderSetup } from "./setup";
import { renderStorage } from "./storage";
import { onChatEvent, onWakeKey, renderChat, renderWake } from "./voice";
import { openConversation, refreshReminders, renderConfig, renderFunctions, renderMemory, renderReminders, renderTools } from "./manage";
import {
  MODEL, POWER_ICON, loading, Point, Reply, actions, ask, byId, comma, esc, flushUndo, head, icon, isTauri, lineChart, link, localDay,
  niceMax, noAnswer, offlineNote, paint, size, state,
} from "./shared";

// ---------- sections ----------
interface Section {
  id: string;
  label: string;
  group: string;
  d: string;
  render: () => void;
  refresh?: () => Promise<void>;
  every?: number; // seconds between refreshes while shown
  fill?: boolean; // the page fills the window and only its list scrolls
  onKey?: (ev: KeyboardEvent) => void;
}

const SECTIONS: Section[] = [
  { id: "inicio", group: "ESTADO", label: "Inicio", d: "M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z", render: renderInicio, refresh: refreshInicio, every: 3 },
  { id: "recursos", group: "ESTADO", label: "Recursos", d: "M3 12h4l2.5-6 5 12 2.5-6H21", render: renderRecursos, refresh: async () => paintRecursos(), every: 2 },
  { id: "almacenamiento", group: "ESTADO", label: "Almacenamiento", d: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3", render: renderStorage },
  { id: "cuotas", group: "ESTADO", label: "Cuotas", d: "M12 3v9h9M20.5 15A9 9 0 1 1 9 3.5", render: renderCuotas, refresh: refreshCuotas, every: 10 },
  { id: "logs", group: "ESTADO", label: "Logs", d: "M4 5h16v14H4zM7.5 9.5 10 12l-2.5 2.5M12.5 15h4", render: renderLogs, refresh: refreshLogs, every: 1.5, fill: true },
  { id: "config", group: "MIKU", label: "Configuración", d: "M4 7h10M18 7h2M4 17h4M12 17h8M16 4.5v5M10 14.5v5", render: renderConfig },
  { id: "herramientas", group: "MIKU", label: "Herramientas", d: "M14.7 6.3a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3l8.7-8.7a4 4 0 0 1-2-2z", render: renderTools },
  { id: "funciones", group: "MIKU", label: "Funciones", d: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", render: renderFunctions },
  { id: "palabra", group: "MIKU", label: "Palabra clave", d: "M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21", render: renderWake, onKey: onWakeKey },
  { id: "recordatorios", group: "LO TUYO", label: "Recordatorios", d: "M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0", render: renderReminders, refresh: refreshReminders, every: 5 },
  { id: "memoria", group: "LO TUYO", label: "Memoria", d: "M6 4h12v17l-6-4-6 4z", render: renderMemory },
  { id: "chat", group: "LO TUYO", label: "Chat", d: "M4 5h16v11H9l-5 4z", render: renderChat, fill: true },
];

let current: Section = SECTIONS[0];
let lastRefresh = -Infinity;

function renderNav(): void {
  let group = "";
  byId("nav")!.innerHTML = SECTIONS.map((s) => {
    const label = s.group !== group ? `<div class="nav-group" aria-hidden="true">${(group = s.group)}</div>` : "";
    return `${label}<button type="button" class="nav-btn" data-go="${s.id}"${s === current ? ' aria-current="page"' : ""}>${icon(s.d)}<span>${esc(s.label)}</span></button>`;
  }).join("");
}

async function go(id: string): Promise<void> {
  const next = SECTIONS.find((s) => s.id === id);
  if (!next) return;
  if (actions.leaveGuard?.() && !(await ask("Hay cambios sin guardar", "Si cambias de página se pierden.", "Salir sin guardar", true))) return;
  actions.leaveGuard = null;
  flushUndo(); // a deletion waiting for "Deshacer" happens now
  if (current.id === "inicio" && next.id !== "inicio") live2d.stopTicker();
  current = next;
  renderNav();
  const v = byId("view")!; // each page sets its own handlers
  v.onclick = v.oninput = v.onchange = v.onkeydown = null;
  v.className = `view${current.fill ? " fill" : ""}`;
  v.scrollTop = 0;
  current.render();
  lastRefresh = -Infinity;
  void tick();
}
actions.go = (id) => void go(id);

// ---------- Inicio ----------
let stage: HTMLDivElement | null = null;
let mikuReady = false;
let lastStatus: Reply = null;

function mikuStage(): HTMLDivElement {
  if (stage) return stage;
  stage = document.createElement("div");
  stage.className = "miku-stage";
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-label", "Miku");
  canvas.setAttribute("role", "img");
  stage.appendChild(canvas);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  live2d
    .init(canvas, 196 * dpr, 228 * dpr, 30)
    // A different path string than Miku's window: her saved framing (localStorage, keyed by path) is for 420x620
    .then(() => live2d.loadModel(`/${MODEL.replace(/^\/+/, "")}`, 0))
    .then(() => {
      mikuReady = true;
      live2d.setExpression(state.backendOn ? "happy" : "neutral");
    })
    .catch((err) => console.warn("[Panel] Live2D:", err));
  return stage;
}

function renderInicio(): void {
  const now = new Date().toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" });
  byId("view")!.innerHTML = `
    ${head("Inicio", "", `<span class="meta">${esc(now)}</span>`)}
    <section class="hero" aria-label="Estado de Miku"><div class="hero-in">
      <div id="stage-slot"></div>
      <div class="hero-text">
        <div id="eq" class="eq" aria-hidden="true">${Array.from({ length: 28 }, (_, i) => `<span style="height:${18 + Math.round(Math.abs(Math.sin(i * 1.7)) * 30)}px;animation-delay:${((i % 7) * 0.08).toFixed(2)}s"></span>`).join("")}</div>
        <div><div id="hero-title" class="hero-title"></div><div id="hero-text" class="muted" aria-live="polite"></div></div>
        <button type="button" id="power" class="power"><span id="power-label"></span><span class="ic">${icon(POWER_ICON)}</span></button>
      </div>
    </div></section>
    <div class="grid">
      <section class="card" aria-label="Piezas"><h2>Piezas</h2><div id="tiles" class="pieces"></div></section>
      <section class="card" aria-label="Lo último que le dijiste"><div class="card-head"><h2>Hoy</h2><button type="button" class="chip" data-go="memoria">Conversaciones</button></div><div id="recent"></div></section>
      <section class="card" aria-label="Cuota de Gemini"><div class="card-head"><h2>Cuota de Gemini</h2><button type="button" class="chip" data-go="cuotas">Detalle</button></div><div id="quota-mini" style="display:flex;flex-direction:column;gap:10px"></div></section>
    </div>`;
  byId("stage-slot")!.replaceWith(mikuStage());
  live2d.startTicker();
  paintInicio(lastStatus);
}

async function refreshInicio(): Promise<void> {
  lastStatus = state.backendOn ? await link.request("status") : null;
  if (current.id === "inicio") paintInicio(lastStatus);
}

/** What she is doing right now, from her "state" events. */
function activityText(s: Reply): string {
  if (!state.backendOn) return "No usa micrófono, CPU ni VRAM. Enciéndela cuando quieras.";
  if (!s) return "Arrancando…";
  if (state.activity === "listening") return "Te está escuchando…";
  if (state.activity === "thinking") return "Pensando la respuesta…";
  if (state.activity === "speaking") return "Hablando";
  if (s.fullscreen) return "Hay algo a pantalla completa: te responde solo con voz";
  return `Esperando «Hey Miku» o ${state.hotkey}`;
}

function paintPower(): void {
  const on = state.backendOn;
  const btn = byId("power") as HTMLButtonElement | null;
  if (btn) {
    btn.className = `power ${on ? "on" : "off"}`;
    btn.disabled = state.powerBusy;
    byId("power-label")!.textContent = state.powerBusy ? (on ? "Apagando…" : "Encendiendo…") : on ? "Apagar Miku" : "Encender Miku";
  }
  byId("hero-title") && (byId("hero-title")!.textContent = on ? "Encendida" : "Apagada");
  byId("hero-text") && (byId("hero-text")!.textContent = activityText(lastStatus));
  const eq = byId("eq");
  if (eq) eq.className = `eq${on ? (state.speaking ? " speaking" : "") : " off"}`;
  stage?.classList.toggle("off", !on);
  if (mikuReady) live2d.setExpression(on ? "happy" : "neutral");
  byId("side-dot")!.className = `dot${on ? " ok" : ""}`;
  byId("side-text")!.textContent = state.powerBusy ? "Cambiando…" : on ? "Encendida" : "Apagada";
}

function paintInicio(s: Reply): void {
  paintPower();
  const on = state.backendOn;
  const g = s?.gemini;
  const primaryWait = g?.cooldowns?.[g.primary];
  const rows: [string, string, string][] = !on || !s
    ? ["Backend", "Voz RVC", "Palabra clave", "Extensión de Opera", "OBS", "Gemini"].map((n, i) => [n, i ? "—" : on ? "Arrancando…" : "Detenido", ""])
    : [
        ["Backend", `Activo · PID ${s.pid}`, "ok"],
        ["Voz RVC", !s.rvc.enabled ? "Desactivada · solo subtítulos" : s.rvc.loaded ? "Cargada en la GPU" : "Se carga al hablar", s.rvc.enabled ? "ok" : ""],
        ["Palabra clave", !s.wakeword.enabled ? "Desactivada · solo con el atajo" : s.wakeword.listening ? `Escuchando · umbral ${comma(s.wakeword.threshold, 2)}` : "En pausa mientras conversa", s.wakeword.enabled ? "ok" : ""],
        ["Extensión de Opera", s.opera.connected ? `Conectada · ${s.opera.tabs} pestañas` : "Sin conectar · abre Opera con la extensión de Miku", s.opera.connected ? "ok" : "warn"],
        ["OBS", s.obs ? "Abierto · clips y grabación por voz" : "Cerrado", s.obs ? "ok" : ""],
        ["Gemini", primaryWait ? `Principal saturado · vuelve en ${Math.ceil(primaryWait / 60)} min` : `En uso: ${g.last_model || g.primary}`, primaryWait ? "warn" : "ok"],
      ];
  paint(byId("tiles"), rows.map(([n, t, c]) => `<div class="piece"><span class="dot ${c}" aria-hidden="true"></span><b>${esc(n)}</b><span class="ellipsis" title="${esc(t)}">${esc(t)}</span></div>`).join(""));
  const turns: any[] = s?.recent ?? [];
  paint(byId("recent"), !on
    ? `<span class="dim">Sin actividad mientras está apagada.</span>`
    : !turns.length
      ? `<span class="dim">Todavía nada desde que arrancó.</span>`
      : turns.slice(0, 5).map((t) => `<div class="list-row"><button type="button" class="turn" data-turn="${esc(t.at)}" style="display:flex;align-items:center;gap:12px;min-width:0" title="Ver la conversación">
          <span class="mono dim" style="width:40px">${esc(t.at)}</span><span class="ellipsis" style="flex:1;font-size:13px;color:var(--soft)">${esc(t.user)}</span>
          <span class="pill ${t.kind === "local" ? "ok" : "gem"}">${t.kind === "local" ? "LOCAL" : "GEMINI"}</span></button></div>`).join(""));
  paint(byId("quota-mini"), !on || !g
    ? `<span class="dim">Se ve con Miku encendida.</span>`
    : `<div style="display:flex;align-items:baseline;gap:8px"><b class="mono" style="font-size:34px;font-weight:500;color:var(--teal-l)">${g.used}</b><span class="muted">de ${g.limit ?? "?"} peticiones hoy</span></div>
       <div class="bar" role="img" aria-label="${g.used} de ${g.limit ?? "?"}"><div style="width:${g.limit ? Math.min(100, (g.used / g.limit) * 100) : 0}%;${g.limit && g.used / g.limit >= 0.8 ? "background:var(--amber)" : ""}"></div></div>
       <span class="dim">Modelo en uso: ${esc(g.last_model || g.primary)}</span>
       ${primaryWait ? `<span class="msg warn" style="font-size:12px">El principal está saturado · vuelve a probar en ${Math.ceil(primaryWait / 60)} min</span>` : ""}
       <span class="dim">Se renueva a las ${esc(g.reset)}</span>`);
}

async function togglePower(): Promise<void> {
  if (state.powerBusy || !isTauri) return;
  state.powerBusy = true;
  paintPower();
  try {
    await invoke(state.backendOn ? "backend_stop" : "backend_start");
  } catch (err) {
    console.warn("[Panel] power:", err);
  }
  state.backendOn = await invoke<boolean>("backend_state");
  state.powerBusy = false;
  if (state.backendOn) link.connect();
  paintPower();
  current.render(); // pages that said "Miku está apagada" load their data now
  lastRefresh = -Infinity;
}
actions.power = togglePower;

// ---------- Recursos: sampled every 2 s while the panel is open, so the charts are already full when opened ----------
const SPAN = 120_000;
const cpuPts: Point[] = [];
const vramPts: Point[] = [];
let res: Reply = null;
let lastSample = 0;

async function sampleResources(): Promise<void> {
  if (!state.backendOn || performance.now() - lastSample < 1950) return;
  lastSample = performance.now();
  res = await link.request("processes");
  if (!res) return;
  const t = Date.now();
  cpuPts.push({ t, v: res.total.cpu });
  vramPts.push({ t, v: res.total.vram });
  for (const pts of [cpuPts, vramPts]) while (pts.length && pts[0].t < t - SPAN - 10_000) pts.shift();
}

function renderRecursos(): void {
  byId("view")!.innerHTML = `
    ${head("Recursos", "Lo que consume Miku: los mismos procesos que salen agrupados como «Miku Assistant» en el Administrador de tareas.", `<span class="pill ok">En vivo · cada 2 s</span>`)}
    <div id="res-body" class="stack"></div>`;
  paintRecursos();
}

function paintRecursos(): void {
  const body = byId("res-body");
  if (!body) return;
  if (!state.backendOn) return paint(body, offlineNote());
  const d = res;
  if (!d) return paint(body, loading("Midiendo los procesos de Miku…", 5));
  const gk = d.gpu_known;
  const kpi = (label: string, value: string, note: string, color: string) =>
    `<div class="card kpi"><span class="muted" style="font-size:12px">${label}</span><span class="big" style="color:${color}">${value}</span><span class="dim">${note}</span></div>`;
  const cpuMax = niceMax(Math.max(0, ...cpuPts.map((p) => p.v)), [5, 10, 25, 50, 100]);
  const gb = 1024 ** 3;
  const vramMax = d.vram_total || niceMax(Math.max(0, ...vramPts.map((p) => p.v)), [1, 2, 4, 8, 12, 16, 24].map((g) => g * gb));
  const count = d.groups.reduce((n: number, g: any) => n + g.count, 0);
  body.innerHTML = `
    <div class="row-wrap">
      ${kpi("CPU de Miku", `${comma(d.total.cpu)} %`, "de toda la CPU", "var(--teal-l)")}
      ${kpi("Memoria", size(d.total.ram), `de ${size(d.ram_total)} del PC · ${count} procesos`, "var(--teal-l)")}
      ${kpi("VRAM", gk ? size(d.total.vram) : "—", gk ? (d.vram_total ? `de ${size(d.vram_total)} de la tarjeta` : "voz RVC y dibujo") : "sin contadores de GPU", "var(--violet)")}
    </div>
    <section class="card" style="overflow-x:auto" aria-label="Procesos"><div class="card-head"><h2>Procesos</h2>${gk ? `<span class="dim">GPU de todo el PC: ${Math.round(d.gpu_total)} %</span>` : ""}</div>
      <div class="table">
        <span class="th">PROCESO</span><span class="th">CPU</span><span class="th">MEMORIA (DEL PC)</span><span class="th">VRAM</span><span class="th">GPU</span>
        ${d.groups.map((g: any) => `
          <div class="name"><b>${esc(g.name)}${g.count > 1 ? ` <span class="dim">(${g.count})</span>` : ""}</b><span>${esc(g.what)}</span></div>
          <span class="mono">${comma(g.cpu)} %</span>
          <div style="display:flex;align-items:center;gap:10px" title="${comma((g.ram / d.ram_total) * 100)} % de la memoria del PC"><div class="bar" style="flex:1"><div style="width:${Math.max(1, (g.ram / d.ram_total) * 100)}%"></div></div><span class="mono" style="width:64px;text-align:right">${size(g.ram)}</span></div>
          <span class="mono" style="color:${g.vram > 0 ? "var(--violet)" : "var(--dim)"}">${gk && g.vram > 0 ? size(g.vram) : "—"}</span>
          <span class="mono">${gk ? `${Math.round(g.gpu)} %` : "—"}</span>`).join("")}
      </div>
    </section>
    <div class="grid">
      <section class="card" aria-label="CPU"><div class="card-head"><h2>CPU de Miku</h2><span class="mono" style="color:var(--teal-l)">${comma(d.total.cpu)} %</span></div>
        ${lineChart("cpu", cpuPts, { span: SPAN, max: cpuMax, color: "#39c5bb", fill: "rgba(57,197,187,0.10)", fmt: (v) => `${comma(v, v < 10 ? 1 : 0)} %`, label: "CPU de Miku en los últimos 2 minutos" })}</section>
      <section class="card" aria-label="VRAM"><div class="card-head"><h2>VRAM de Miku</h2><span class="mono" style="color:var(--violet)">${gk ? size(d.total.vram) : "—"}</span></div>
        ${lineChart("vram", vramPts, { span: SPAN, max: vramMax, color: "#b59cff", fill: "rgba(181,156,255,0.10)", fmt: (v) => size(v), label: "VRAM de Miku en los últimos 2 minutos" })}</section>
    </div>`;
}

// ---------- Cuotas ----------
let quotaData: Reply = null;
let quotaAsked = false;

function renderCuotas(): void {
  byId("view")!.innerHTML = `
    ${head("Cuotas", "Peticiones a Gemini en el plan gratuito. Cuenta cada petición enviada, también las que fallan: Google las cuenta igual.")}
    <div id="q-body" class="stack"></div>`;
  quotaAsked = false;
  paintCuotas();
}

async function refreshCuotas(): Promise<void> {
  quotaData = state.backendOn ? await link.request("quota") : null;
  quotaAsked = true;
  if (current.id === "cuotas") paintCuotas();
}

function paintCuotas(): void {
  const body = byId("q-body");
  if (!body) return;
  if (!state.backendOn) return paint(body, offlineNote());
  const d = quotaData;
  if (!d) return paint(body, quotaAsked ? noAnswer() : loading("Leyendo la cuota de hoy…", 4));
  const main = d.models.find((m: any) => m.primary) ?? d.models[0];
  const frac = main.limit ? Math.min(1, main.used / main.limit) : 0;
  const circ = 2 * Math.PI * 70;
  const fmt = (n: number) => n.toLocaleString("es");
  const status = (m: any) => {
    if (m.cooldown) return `<span class="pill warn">En pausa ${m.cooldown >= 60 ? `${Math.ceil(m.cooldown / 60)} min` : `${m.cooldown} s`}</span>`;
    if (m.limit && m.used >= m.limit) return `<span class="pill bad">Agotado hoy</span>`;
    if (m.limit && m.used / m.limit >= 0.8) return `<span class="pill warn">Casi agotado</span>`;
    return "";
  };
  const week = d.week.map((w: any) => {
    const entries = Object.entries(w.counts as Record<string, number>);
    const mainN = w.counts[d.primary] ?? 0;
    const back = entries.filter(([m, c]) => m !== d.primary && c);
    return { day: w.day, mainN, backN: back.reduce((n, [, c]) => n + c, 0), back };
  });
  const top = niceMax(Math.max(1, ...week.map((w: any) => w.mainN + w.backN)), [10, 25, 50, 100, 200, 300, 500, 750, 1000, 2000, 5000]);
  const shortDay = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("es", { weekday: "short", day: "numeric" });
  paint(body, `
    <div class="row-wrap">
      <section class="card" style="flex:1 1 280px;align-items:center;text-align:center" aria-label="Modelo principal">
        <div class="ring-wrap"><svg width="170" height="170" viewBox="0 0 170 170" role="img" aria-label="${main.used} de ${main.limit ?? "?"} peticiones hoy">
          <circle cx="85" cy="85" r="70" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="12"></circle>
          <circle cx="85" cy="85" r="70" fill="none" stroke="${frac >= 0.8 ? "#f2b544" : "#39c5bb"}" stroke-width="12" stroke-linecap="round" stroke-dasharray="${(circ * frac).toFixed(1)} ${circ.toFixed(1)}"></circle></svg>
          <div class="ring-num"><b>${fmt(main.used)}</b><span class="muted" style="font-size:13px">de ${main.limit ? fmt(main.limit) : "?"} hoy</span></div></div>
        <b style="font-size:16px;font-weight:600">${esc(main.model)}</b>
        <span class="muted" style="font-size:13px">Modelo principal${main.limit ? ` · quedan ${fmt(Math.max(0, main.limit - main.used))}` : ""}</span>
        ${status(main) || `<span class="pill ok">Respondiendo</span>`}
        <span class="dim">Se renueva a las ${esc(d.reset)} (medianoche del Pacífico)</span>
      </section>
      <section class="card" style="flex:2 1 420px" aria-label="Modelos de respaldo"><h2>Modelos de respaldo</h2>
        <p class="muted" style="margin:0;font-size:13px">Si el principal falla, Miku dice «Un momento…» y prueba el siguiente, en este orden.</p>
        ${d.models.filter((m: any) => !m.primary).map((m: any, i: number) => {
          const f = m.limit ? m.used / m.limit : 0;
          return `<div class="list-row" style="flex-direction:column;align-items:stretch;gap:8px;padding:9px 0">
            <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center"><span style="display:flex;align-items:center;gap:10px;font-size:14px"><span class="order">${i + 1}</span>${esc(m.model)}</span>
              <span style="display:flex;gap:10px;align-items:center">${status(m)}<span class="mono" style="font-size:13px">${fmt(m.used)} / ${m.limit ? fmt(m.limit) : "?"}</span></span></div>
            <div class="bar"><div style="width:${m.used ? Math.max(1.5, Math.min(100, f * 100)) : 0}%;background:${f >= 0.8 ? "var(--amber)" : "var(--blue)"}"></div></div></div>`;
        }).join("")}
      </section>
    </div>
    <section class="card" aria-label="Últimos 7 días"><div class="card-head"><h2>Últimos 7 días</h2>
      <div class="legend"><span><i class="swatch" style="background:var(--teal)"></i>Principal</span><span><i class="swatch" style="background:var(--blue)"></i>Respaldo</span></div></div>
      <div class="bars">
        <div class="y" style="display:flex;flex-direction:column;justify-content:space-between;height:140px;font-family:var(--mono);font-size:10.5px;color:var(--dim);text-align:right"><span>${fmt(top)}</span><span>${fmt(top / 2)}</span><span>0</span></div>
        <div class="cols"><div class="guide" style="top:0"></div><div class="guide" style="top:50%"></div>
          ${week.map((w: any) => {
            const tip = `${shortDay(w.day)}\nPrincipal: ${w.mainN}\nRespaldo: ${w.backN}${w.back.length ? `\n${w.back.map(([m, c]: [string, number]) => `  ${m}: ${c}`).join("\n")}` : ""}`;
            return `<div class="col" data-tip="${esc(tip)}" tabindex="0" aria-label="${esc(tip.replace(/\n/g, ", "))}"><span class="mono dim" style="font-size:11px">${w.mainN + w.backN}</span>
              <div style="height:${((w.backN / top) * 100).toFixed(1)}%;border-radius:5px 5px 0 0;background:var(--blue)"></div>
              <div style="height:${((w.mainN / top) * 100).toFixed(1)}%;border-radius:${w.backN ? "0" : "5px 5px"} 0 0;background:var(--teal)"></div></div>`;
          }).join("")}
        </div>
        <div class="days">${week.map((w: any, i: number) => `<span style="${i === 6 ? "color:var(--teal-l)" : ""}">${i === 6 ? "hoy" : esc(shortDay(w.day))}</span>`).join("")}</div>
      </div>
    </section>`);
}

// ---------- Logs: only new lines are added (text stays selectable); older ones load on demand ----------
const LOG_RE = /^(?:(\d{4}-\d{2}-\d{2}) )?(\d\d:\d\d:\d\d(?:\.\d{3})?) \[(\w+)\] ([\w.]+): (.*)$/;
const LOG_FILTERS: [string, string, (l: LogLine) => boolean][] = [
  ["all", "Todo", () => true],
  ["error", "Avisos y errores", (l) => l.lvl === "WARNING" || l.lvl === "ERROR" || l.lvl === "CRITICAL"],
  ["gemini", "Gemini", (l) => l.src === "llm"],
  ["wake", "Palabra clave", (l) => l.src === "wakeword"],
  ["tools", "Herramientas", (l) => l.src.startsWith("tools")],
];
interface LogLine { d: string; t: string; lvl: string; src: string; msg: string }
const log = { lines: [] as LogLine[], raw: 0, offset: 0, more: false, loaded: false, busy: false };
let logFilter = "all";
let logQuery = "";
let logPaused = false;

/** Parses log text; a line that is not a new entry (a traceback) belongs to the entry before it. */
function parseLog(text: string, prev?: LogLine): LogLine[] {
  const out: LogLine[] = [];
  for (const line of text.split(/\r?\n/)) {
    const m = LOG_RE.exec(line);
    if (m) out.push({ d: m[1] ?? "", t: m[2], lvl: m[3], src: m[4].replace(/^miku\./, "").replace(/^websockets\./, "ws."), msg: m[5] });
    else if (line.trim() && (out[out.length - 1] ?? prev)) (out[out.length - 1] ?? prev)!.msg += `\n${line}`;
  }
  return out;
}

const logKeep = (l: LogLine) => LOG_FILTERS.find(([id]) => id === logFilter)![2](l) && (!logQuery || l.msg.toLowerCase().includes(logQuery.toLowerCase()));

function logRow(l: LogLine): string {
  let msg = esc(l.msg);
  if (logQuery) {
    const parts = l.msg.split(new RegExp(`(${logQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "i"));
    msg = parts.map((p, i) => (i % 2 ? `<mark>${esc(p)}</mark>` : esc(p))).join("");
  }
  const cls = l.lvl === "WARNING" ? " warn" : l.lvl === "ERROR" || l.lvl === "CRITICAL" ? " err" : "";
  return `<div class="logline${cls}"><span>${esc(l.t)}</span><span class="lv">${esc(l.lvl === "WARNING" ? "WARN" : l.lvl)}</span><span title="${esc(l.src)}">${esc(l.src)}</span><span>${msg}</span></div>`;
}

/** The rows of `lines`, with a separator each time the day changes (`lastDay`: the day of the row before them). */
function logRows(lines: LogLine[], lastDay: string): string {
  let html = "";
  for (const l of lines) {
    if (!logKeep(l)) continue;
    if (l.d && l.d !== lastDay) html += `<div class="logday">${esc(dayLabelLog(l.d))}</div>`;
    if (l.d) lastDay = l.d;
    html += logRow(l);
  }
  return html;
}
const dayLabelLog = (d: string) => (d === localDay() ? "Hoy" : new Date(`${d}T12:00:00`).toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" }));
let logLastDay = "";

function renderLogs(): void {
  byId("view")!.innerHTML = `
    ${head("Logs", "cache/core.log en vivo. Solo lectura: el panel nunca borra los logs.")}
    <div class="toolbar">
      <div class="chips" role="group" aria-label="Filtrar">${LOG_FILTERS.map(([id, label]) => `<button type="button" class="chip" data-filter="${id}" aria-pressed="${id === logFilter}">${label}<span class="n" id="n-${id}"></span></button>`).join("")}</div>
      <div class="chips"><label for="log-q" class="sr">Buscar en el log</label><input id="log-q" class="search" type="search" placeholder="Buscar…" value="${esc(logQuery)}">
        <button type="button" class="chip" id="log-pause" aria-pressed="${logPaused}">${logPaused ? "Seguir" : "Pausar"}</button>
        <button type="button" class="chip" data-open="logs">Abrir carpeta</button></div>
    </div>
    <div id="logbox" class="logbox grow" aria-live="off">${loading("Leyendo cache/core.log…", 10)}</div>`;
  if (log.loaded) paintLogs(true);
}

function paintCounts(): void {
  for (const [id, , keep] of LOG_FILTERS) paint(byId(`n-${id}`), String(log.lines.filter(keep).length));
}

function paintLogs(jump: boolean, keepFromBottom?: number): void {
  const box = byId("logbox");
  if (!box) return;
  const html = logRows(log.lines, "");
  const more = log.more ? `<div class="logmore"><button type="button" class="btn small ghost" id="log-older">Cargar líneas más antiguas</button></div>` : "";
  box.innerHTML = more + (html || `<div class="dim" style="padding:30px 8px">Nada de este tipo en lo cargado.${log.more ? " Prueba a cargar líneas más antiguas." : ""}</div>`);
  logLastDay = [...log.lines].reverse().find((l) => l.d)?.d ?? "";
  if (keepFromBottom !== undefined) box.scrollTop = box.scrollHeight - keepFromBottom;
  else if (jump) box.scrollTop = box.scrollHeight;
  paintCounts();
}

async function loadLog(): Promise<void> {
  const r = await invoke<{ text: string; more: boolean; offset: number }>("read_log", { lines: 1500, skip: 0 });
  log.lines = parseLog(r.text);
  log.raw = r.text ? r.text.split("\n").length : 0;
  log.more = r.more;
  log.offset = r.offset;
  log.loaded = true;
  if (current.id === "logs") paintLogs(true);
}

async function loadOlder(): Promise<void> {
  const box = byId("logbox");
  const fromBottom = box ? box.scrollHeight - box.scrollTop : 0;
  const r = await invoke<{ text: string; more: boolean }>("read_log", { lines: 2000, skip: log.raw });
  log.lines = [...parseLog(r.text), ...log.lines];
  log.raw += r.text ? r.text.split("\n").length : 0;
  log.more = r.more;
  if (current.id === "logs") paintLogs(false, fromBottom);
}

async function refreshLogs(): Promise<void> {
  if (!isTauri || log.busy) return;
  log.busy = true;
  try {
    if (!log.loaded) await loadLog();
    else if (!logPaused) {
      const r = await invoke<{ text?: string; offset?: number; reset?: boolean }>("log_tail", { offset: log.offset });
      if (r.reset) {
        log.loaded = false; // the log rotated: read it again from the end
        await loadLog();
      } else if (r.text) {
        const prev = log.lines[log.lines.length - 1];
        const before = prev ? prev.msg.length : 0;
        const fresh = parseLog(r.text, prev);
        log.offset = r.offset!;
        log.raw += r.text.replace(/\n$/, "").split("\n").length;
        log.lines.push(...fresh);
        const box = byId("logbox");
        if (current.id === "logs" && box) {
          if (prev && prev.msg.length !== before) paintLogs(false, box.scrollHeight - box.scrollTop); // a traceback grew
          else {
            const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
            const html = logRows(fresh, logLastDay);
            if (html) {
              box.querySelector(":scope > .dim")?.remove();
              box.insertAdjacentHTML("beforeend", html);
            }
            logLastDay = [...fresh].reverse().find((l) => l.d)?.d ?? logLastDay;
            if (atBottom) box.scrollTop = box.scrollHeight;
            paintCounts();
          }
        }
      }
    }
  } catch (err) {
    console.warn("[Panel] log:", err);
  } finally {
    log.busy = false;
  }
}

// ---------- loop and events ----------
async function tick(): Promise<void> {
  if (document.hidden) return;
  void sampleResources();
  if (!current.refresh) return;
  const now = performance.now();
  if (now - lastRefresh < (current.every ?? 2) * 1000 - 50) return;
  lastRefresh = now;
  await current.refresh();
}

document.addEventListener("click", (ev) => {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("[data-go],[data-filter],[data-power],[data-retry],[data-open],[data-turn],#power,#log-pause,#log-older");
  if (!el) return;
  if (el.dataset.go) void go(el.dataset.go);
  else if (el.dataset.filter) {
    logFilter = el.dataset.filter;
    document.querySelectorAll<HTMLElement>("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filter === logFilter)));
    paintLogs(true);
  } else if (el.id === "power" || el.dataset.power !== undefined) void togglePower();
  else if (el.dataset.retry !== undefined) current.render();
  else if (el.dataset.open) invoke("open_folder", { which: el.dataset.open }).catch((err) => console.warn("[Panel] folder:", err));
  else if (el.dataset.turn) {
    openConversation(localDay(), el.dataset.turn);
    void go("memoria");
  } else if (el.id === "log-older") {
    (el as HTMLButtonElement).disabled = true;
    void loadOlder();
  } else if (el.id === "log-pause") {
    logPaused = !logPaused;
    el.setAttribute("aria-pressed", String(logPaused));
    el.textContent = logPaused ? "Seguir" : "Pausar";
  }
});

document.addEventListener("input", (ev) => {
  const el = ev.target as HTMLInputElement;
  if (el.id === "log-q") {
    logQuery = el.value;
    paintLogs(true);
  }
});

document.addEventListener("keydown", (ev) => {
  const tag = (ev.target as HTMLElement).tagName;
  if (current.onKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") current.onKey(ev);
});

// Hidden panel: no polling, no Live2D drawing
document.addEventListener("visibilitychange", () => {
  if (current.id !== "inicio") return;
  if (document.hidden) live2d.stopTicker();
  else live2d.startTicker();
});

link.onEvent = (msg) => {
  onChatEvent(msg);
  if (msg.type === "state") {
    state.activity = String(msg.value);
    state.speaking = msg.value === "speaking";
    if (current.id === "inicio") paintPower();
  }
};

async function bootstrap(): Promise<void> {
  if (isTauri) {
    // Installed and never set up: the first-start wizard instead of the panel
    const setup = await invoke<{ installed: boolean; ready: boolean }>("setup_state").catch(() => ({ installed: false, ready: true }));
    if (setup.installed && !setup.ready) {
      renderSetup();
      return;
    }
    state.backendOn = await invoke<boolean>("backend_state").catch(() => false);
    await listen<boolean>("backend-changed", (ev) => {
      state.backendOn = ev.payload;
      if (state.backendOn) link.connect();
      if (current.id === "inicio") paintPower();
      lastRefresh = -Infinity;
    });
    await listen<string>("hotkey-changed", (ev) => (state.hotkey = ev.payload));
    invoke<string>("settings_get").then((t) => (state.hotkey = JSON.parse(t).hotkey || state.hotkey)).catch(() => {});
  } else {
    state.backendOn = true; // in a plain browser (vite dev or preview) there is no Rust to ask: the WebSocket decides
  }
  if (state.backendOn) link.connect();
  renderNav();
  byId("view")!.className = "view";
  current.render();
  window.setInterval(() => void tick(), 500);
  // The backend can be started or stopped from elsewhere (start.bat, stop.bat): check now and then
  window.setInterval(async () => {
    if (!isTauri || state.powerBusy) return;
    const on = await invoke<boolean>("backend_state").catch(() => state.backendOn);
    if (on !== state.backendOn) {
      state.backendOn = on;
      if (on) link.connect();
      if (current.id === "inicio") paintPower();
    }
  }, 5000);
}

void bootstrap();
