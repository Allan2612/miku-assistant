/**
 * Miku Assistant panel: Inicio, Recursos, Cuotas and Logs (phase 2). The other sections say what they will hold.
 * Data: the backend over the WebSocket (panel_hello / panel_get), the log and the on/off switch through Rust.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { live2d } from "../live2d";
import { onChatEvent, renderChat, renderWake } from "./voice";
import { refreshReminders, renderConfig, renderFunctions, renderMemory, renderReminders, renderTools } from "./manage";
import { MODEL, POWER_ICON, Reply, byId, comma, esc, head, icon, isTauri, link, offlineNote, size, state } from "./shared";


// ---------- sections ----------
interface Section {
  id: string;
  label: string;
  d: string;
  render: () => void;
  refresh?: () => Promise<void>;
  every?: number; // seconds between refreshes while shown
}

const SECTIONS: Section[] = [
  { id: "inicio", label: "Inicio", d: "M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z", render: renderInicio, refresh: refreshInicio, every: 3 },
  { id: "recursos", label: "Recursos", d: "M3 12h4l2.5-6 5 12 2.5-6H21", render: renderRecursos, refresh: refreshRecursos, every: 2 },
  { id: "cuotas", label: "Cuotas", d: "M12 3v9h9M20.5 15A9 9 0 1 1 9 3.5", render: renderCuotas, refresh: refreshCuotas, every: 10 },
  { id: "logs", label: "Logs", d: "M4 5h16v14H4zM7.5 9.5 10 12l-2.5 2.5M12.5 15h4", render: renderLogs, refresh: refreshLogs, every: 1.5 },
  { id: "config", label: "Configuración", d: "M4 7h10M18 7h2M4 17h4M12 17h8M16 4.5v5M10 14.5v5", render: renderConfig },
  { id: "herramientas", label: "Herramientas", d: "M14.7 6.3a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3l8.7-8.7a4 4 0 0 1-2-2z", render: renderTools },
  { id: "funciones", label: "Funciones", d: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", render: renderFunctions },
  { id: "recordatorios", label: "Recordatorios", d: "M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0", render: renderReminders, refresh: refreshReminders, every: 5 },
  { id: "memoria", label: "Memoria", d: "M6 4h12v17l-6-4-6 4z", render: renderMemory },
  { id: "palabra", label: "Palabra clave", d: "M12 4a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21", render: renderWake },
  { id: "chat", label: "Chat", d: "M4 5h16v11H9l-5 4z", render: renderChat },
];

let current: Section = SECTIONS[0];
let lastRefresh = 0;

function renderNav(): void {
  byId("nav")!.innerHTML = SECTIONS.map(
    (s) => `<button type="button" class="nav-btn" data-go="${s.id}"${s === current ? ' aria-current="page"' : ""}>${icon(s.d)}<span>${esc(s.label)}</span></button>`,
  ).join("");
}

function go(id: string): void {
  const next = SECTIONS.find((s) => s.id === id);
  if (!next) return;
  if (current.id === "inicio" && next.id !== "inicio") live2d.stopTicker();
  current = next;
  renderNav();
  const v = byId("view")!; // each page sets its own handlers
  v.onclick = v.oninput = v.onchange = v.onkeydown = null;
  v.scrollTop = 0;
  current.render();
  lastRefresh = 0;
  tick();
}


// ---------- Inicio ----------
let stage: HTMLDivElement | null = null;
let mikuReady = false;

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
    .init(canvas, 240 * dpr, 280 * dpr, 30)
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
    ${head("INICIO", "", "", `<span class="meta">${esc(now)}</span>`)}
    <section class="hero" aria-label="Estado de Miku"><div class="hero-in">
      <div id="stage-slot"></div>
      <div class="hero-text">
        <div id="eq" class="eq" aria-hidden="true">${Array.from({ length: 28 }, (_, i) => `<span style="height:${20 + Math.round(Math.abs(Math.sin(i * 1.7)) * 44)}px;animation-delay:${((i % 7) * 0.13).toFixed(2)}s"></span>`).join("")}</div>
        <div><div id="hero-title" class="hero-title"></div><div id="hero-text" class="muted"></div></div>
        <button type="button" id="power" class="power"><span id="power-label"></span><span class="ic">${icon(POWER_ICON)}</span></button>
      </div>
    </div></section>
    <div class="grid">
      <section class="card" aria-label="Piezas"><h2>Piezas</h2><div id="tiles" class="tiles"></div></section>
      <section class="card" aria-label="Lo último que hizo"><div class="card-head"><h2>Hoy</h2><button type="button" class="chip" data-go="logs">Ver logs</button></div><div id="recent"></div></section>
      <section class="card" aria-label="Cuota de Gemini"><div class="card-head"><h2>Cuota de Gemini</h2><button type="button" class="chip" data-go="cuotas">Detalle</button></div><div id="quota-mini" style="display:flex;flex-direction:column;gap:12px"></div></section>
    </div>`;
  byId("stage-slot")!.replaceWith(mikuStage());
  live2d.startTicker();
  paintPower();
  paintInicio(lastStatus);
}

let lastStatus: Reply = null;

async function refreshInicio(): Promise<void> {
  lastStatus = state.backendOn ? await link.request("status") : null;
  if (current.id === "inicio") paintInicio(lastStatus);
}

function paintPower(): void {
  const on = state.backendOn;
  byId("title") && (byId("title")!.textContent = on ? "Todo en orden" : "Miku está apagada");
  byId("subtitle") &&
    (byId("subtitle")!.textContent = on
      ? "Miku te escucha. Di «Hey Miku» o pulsa Ctrl+Alt+M."
      : "No usa micrófono, CPU ni VRAM. Enciéndela cuando quieras.");
  const btn = byId("power") as HTMLButtonElement | null;
  if (btn) {
    btn.className = `power ${on ? "on" : "off"}`;
    btn.disabled = state.powerBusy;
    byId("power-label")!.textContent = state.powerBusy ? (on ? "Apagando…" : "Encendiendo…") : on ? "Apagar Miku" : "Encender Miku";
  }
  byId("hero-title") && (byId("hero-title")!.textContent = on ? "Encendida" : "Apagada");
  const eq = byId("eq");
  if (eq) eq.className = `eq${on ? (state.speaking ? " speaking" : "") : " off"}`;
  stage?.classList.toggle("off", !on);
  if (mikuReady) live2d.setExpression(on ? "happy" : "neutral");
  byId("side-dot")!.style.background = on ? "#39c5bb" : "#56666a";
  byId("side-dot")!.style.boxShadow = on ? "0 0 10px #39c5bb" : "none";
  byId("side-text")!.textContent = state.powerBusy ? "Cambiando…" : on ? "Encendida" : "Apagada";
}

function paintInicio(s: Reply): void {
  paintPower();
  const on = state.backendOn;
  const heroText = byId("hero-text");
  if (heroText) {
    heroText.textContent = !on
      ? "VRAM liberada · el panel sigue abierto"
      : !s
        ? "Arrancando…"
        : s.fullscreen
          ? "Hay algo a pantalla completa: responde solo con voz"
          : `Escuchando «Hey Miku»${s.rvc?.loaded ? " · voz RVC lista en la GPU" : ""}`;
  }
  const tiles = byId("tiles");
  if (tiles) {
    const g = s?.gemini;
    const primaryWait = g?.cooldowns?.[g.primary];
    const rows: [string, string, string][] = !on || !s
      ? [["Backend", on ? "Arrancando…" : "Detenido", "#56666a"], ["Voz RVC", "—", "#56666a"], ["Palabra clave", "—", "#56666a"], ["Extensión de Opera", "—", "#56666a"], ["OBS", "—", "#56666a"], ["Gemini", "—", "#56666a"]]
      : [
          ["Backend", `Activo · PID ${s.pid}`, "#39c5bb"],
          ["Voz RVC", !s.rvc.enabled ? "Desactivada" : s.rvc.loaded ? "Cargada en la GPU" : "Se carga al hablar", s.rvc.enabled ? "#39c5bb" : "#56666a"],
          ["Palabra clave", !s.wakeword.enabled ? "Desactivada" : s.wakeword.listening ? `Escuchando · umbral ${comma(s.wakeword.threshold, 2)}` : "En pausa mientras conversa", s.wakeword.enabled ? "#39c5bb" : "#56666a"],
          ["Extensión de Opera", s.opera.connected ? `Conectada · ${s.opera.tabs} pestañas` : "Sin conectar", s.opera.connected ? "#39c5bb" : "#56666a"],
          ["OBS", s.obs ? "Abierto" : "Cerrado", s.obs ? "#39c5bb" : "#56666a"],
          ["Gemini", primaryWait ? `Principal en pausa ${Math.ceil(primaryWait / 60)} min` : `En uso: ${g.last_model || g.primary}`, primaryWait ? "#f2b544" : "#39c5bb"],
        ];
    tiles.innerHTML = rows.map(([n, t, c]) => `<div class="tile"><b><span class="dot" style="background:${c}"></span>${esc(n)}</b><span>${esc(t)}</span></div>`).join("");
  }
  const recent = byId("recent");
  if (recent) {
    const turns: any[] = s?.recent ?? [];
    recent.innerHTML = !on
      ? `<span class="dim">Sin actividad mientras está apagada.</span>`
      : !turns.length
        ? `<span class="dim">Todavía nada desde que arrancó.</span>`
        : turns
            .map((t) => `<div class="list-row"><span class="mono dim" style="width:44px">${esc(t.at)}</span><span style="flex:1;font-size:13px;color:var(--soft);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(t.user)}</span><span class="pill ${t.kind === "local" ? "ok" : "gem"}">${t.kind === "local" ? "LOCAL" : "GEMINI"}</span></div>`)
            .join("");
  }
  const q = byId("quota-mini");
  if (q) {
    const g = s?.gemini;
    q.innerHTML = !on || !g
      ? `<span class="dim">Se ve con Miku encendida.</span>`
      : `<div style="display:flex;align-items:baseline;gap:8px"><b class="mono" style="font-size:38px;font-weight:500;color:var(--teal-l)">${g.used}</b><span class="muted">de ${g.limit ?? "?"} peticiones</span></div>
         <div class="bar"><div style="width:${g.limit ? Math.min(100, (g.used / g.limit) * 100) : 0}%"></div></div>
         <span class="dim">Modelo en uso: ${esc(g.last_model || g.primary)}</span>
         ${g.cooldowns?.[g.primary] ? `<span style="font-size:12px;color:var(--amber)">El principal está saturado · vuelve a probar en ${Math.ceil(g.cooldowns[g.primary] / 60)} min</span>` : ""}
         <span class="dim">Se renueva a las ${esc(g.reset)}</span>`;
  }
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
  lastRefresh = 0;
}

// ---------- Recursos ----------
const cpuHist: number[] = [];
const vramHist: number[] = [];

function renderRecursos(): void {
  byId("view")!.innerHTML = `
    ${head("RECURSOS", "Lo que consume Miku", "Los mismos procesos que salen agrupados como «Miku Assistant» en el Administrador de tareas.", `<span class="pill gem">En vivo · cada 2 s</span>`)}
    <div id="res-body" style="display:flex;flex-direction:column;gap:18px"></div>`;
  paintRecursos(null);
}

async function refreshRecursos(): Promise<void> {
  const data = state.backendOn ? await link.request("processes") : null;
  if (data) {
    cpuHist.push(data.total.cpu);
    vramHist.push(data.total.vram);
    for (const h of [cpuHist, vramHist]) if (h.length > 60) h.shift();
  }
  if (current.id === "recursos") paintRecursos(data);
}

function chart(values: number[], color: string, fill: string, label: string): string {
  const max = Math.max(1, ...values) * 1.15;
  const span = Math.max(1, values.length - 1); // the full width from the first samples on
  const pts = values.map((v, i) => `${((i / span) * 300).toFixed(1)},${(90 - (v / max) * 84).toFixed(1)}`).join(" ");
  return `<svg class="chart" role="img" aria-label="${esc(label)}" viewBox="0 0 300 90" preserveAspectRatio="none">
    ${values.length > 1 ? `<polyline points="0,90 ${pts} 300,90" fill="${fill}" stroke="none"></polyline><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"></polyline>` : ""}
  </svg>`;
}

function paintRecursos(d: Reply): void {
  const body = byId("res-body");
  if (!body) return;
  if (!state.backendOn) {
    body.innerHTML = offlineNote();
    return;
  }
  if (!d) {
    body.innerHTML = body.innerHTML || `<span class="dim">Midiendo…</span>`;
    return;
  }
  const gk = d.gpu_known;
  const kpis = [
    ["CPU de Miku", `${comma(d.total.cpu)} %`, "de toda la CPU"],
    ["Memoria", size(d.total.ram), `${d.groups.reduce((n: number, g: any) => n + g.count, 0)} procesos`],
    ["VRAM", gk ? size(d.total.vram) : "—", gk ? "voz RVC y dibujo" : "sin contadores de GPU"],
    ["GPU total", gk ? `${Math.round(d.gpu_total)} %` : "—", "con todo lo que tengas abierto"],
  ];
  const maxRam = Math.max(1, ...d.groups.map((g: any) => g.ram));
  body.innerHTML = `
    <div class="row-wrap">${kpis.map(([l, v, n], i) => `<div class="card kpi"><span class="muted" style="font-size:12px">${l}</span><span class="big" style="color:${i === 2 ? "var(--pink-l)" : "var(--teal-l)"}">${v}</span><span class="dim">${n}</span></div>`).join("")}</div>
    <div class="row-wrap">
      <section class="card" style="flex:3 1 520px;overflow-x:auto" aria-label="Procesos"><h2>Procesos</h2>
        <div class="table">
          <span class="th">PROCESO</span><span class="th">CPU</span><span class="th">MEMORIA</span><span class="th">VRAM</span><span class="th">GPU</span>
          ${d.groups.map((g: any) => `
            <div class="name"><b>${esc(g.name)}${g.count > 1 ? ` <span class="dim">(${g.count})</span>` : ""}</b><span>${esc(g.what)}</span></div>
            <span class="mono">${comma(g.cpu)} %</span>
            <div style="display:flex;align-items:center;gap:10px"><div class="bar" style="flex:1"><div style="width:${(g.ram / maxRam) * 100}%"></div></div><span class="mono" style="width:60px;text-align:right">${size(g.ram)}</span></div>
            <span class="mono" style="color:${g.vram > 0 ? "var(--pink-l)" : "var(--dim)"}">${gk && g.vram > 0 ? size(g.vram) : "—"}</span>
            <span class="mono">${gk ? `${Math.round(g.gpu)} %` : "—"}</span>`).join("")}
        </div>
      </section>
      <div style="flex:2 1 300px;display:flex;flex-direction:column;gap:18px;min-width:0">
        <section class="card" aria-label="CPU"><div class="card-head"><h2>CPU</h2><span class="mono" style="color:var(--teal-l)">${comma(d.total.cpu)} %</span></div>${chart(cpuHist, "#39c5bb", "rgba(57,197,187,0.10)", "CPU de Miku en los últimos 2 minutos")}<span class="dim">Últimos 2 minutos</span></section>
        <section class="card" aria-label="VRAM"><div class="card-head"><h2>VRAM</h2><span class="mono" style="color:var(--pink-l)">${gk ? size(d.total.vram) : "—"}</span></div>${chart(vramHist, "#ff5aaa", "rgba(255,90,170,0.10)", "VRAM de Miku en los últimos 2 minutos")}<span class="dim">Últimos 2 minutos</span></section>
      </div>
    </div>`;
}

// ---------- Cuotas ----------
function renderCuotas(): void {
  byId("view")!.innerHTML = `
    ${head("CUOTAS", "Peticiones a Gemini", "Plan gratuito. Solo cuentan las respuestas: una petición rechazada no gasta cuota.")}
    <div id="q-body" style="display:flex;flex-direction:column;gap:18px"></div>`;
  paintCuotas(null);
}

async function refreshCuotas(): Promise<void> {
  const data = state.backendOn ? await link.request("quota") : null;
  if (current.id === "cuotas") paintCuotas(data);
}

function paintCuotas(d: Reply): void {
  const body = byId("q-body");
  if (!body) return;
  if (!state.backendOn) {
    body.innerHTML = offlineNote();
    return;
  }
  if (!d) {
    body.innerHTML = body.innerHTML || `<span class="dim">Cargando…</span>`;
    return;
  }
  const main = d.models.find((m: any) => m.primary) ?? d.models[0];
  const frac = main.limit ? Math.min(1, main.used / main.limit) : 0;
  const circ = 2 * Math.PI * 80;
  const fmt = (n: number) => n.toLocaleString("es");
  const waitText = (s: number) => (s >= 60 ? `En pausa ${Math.ceil(s / 60)} min` : `En pausa ${s} s`);
  const week = d.week.map((w: any) => {
    const mainN = w.counts[d.primary] ?? 0;
    const backN = Object.entries(w.counts).reduce((n: number, [m, c]) => (m === d.primary ? n : n + (c as number)), 0);
    return { day: w.day, mainN, backN };
  });
  const top = Math.max(1, ...week.map((w: any) => w.mainN + w.backN));
  const dayName = (iso: string, i: number) => (i === 6 ? "hoy" : new Date(`${iso}T12:00:00`).toLocaleDateString("es", { weekday: "short" }));
  body.innerHTML = `
    <div class="row-wrap">
      <section class="card" style="flex:1 1 300px;align-items:center;text-align:center" aria-label="Modelo principal">
        <div class="ring-wrap"><svg width="190" height="190" viewBox="0 0 190 190" role="img" aria-label="${main.used} de ${main.limit ?? "?"} peticiones hoy">
          <circle cx="95" cy="95" r="80" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="12"></circle>
          <circle cx="95" cy="95" r="80" fill="none" stroke="#39c5bb" stroke-width="12" stroke-linecap="round" stroke-dasharray="${(circ * frac).toFixed(1)} ${circ.toFixed(1)}"></circle></svg>
          <div class="ring-num"><b>${fmt(main.used)}</b><span class="muted" style="font-size:13px">de ${main.limit ? fmt(main.limit) : "?"} hoy</span></div></div>
        <b style="font-size:16px;font-weight:600">${esc(main.model)}</b>
        <span class="muted" style="font-size:13px">Modelo principal${main.limit ? ` · quedan ${fmt(Math.max(0, main.limit - main.used))}` : ""}</span>
        ${main.cooldown ? `<span class="pill warn">${waitText(main.cooldown)}</span>` : `<span class="pill ok">Listo</span>`}
        <span class="dim">La cuota se renueva a las ${esc(d.reset)} (medianoche del Pacífico)</span>
      </section>
      <section class="card" style="flex:2 1 440px" aria-label="Modelos de respaldo"><h2>Modelos de respaldo</h2>
        <p class="muted" style="margin:0;font-size:13px">Si el principal falla, Miku dice «Un momento…» y prueba el siguiente, en este orden.</p>
        ${d.models.filter((m: any) => !m.primary).map((m: any) => `
          <div class="list-row" style="flex-direction:column;align-items:stretch;gap:8px;padding:10px 0">
            <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><span style="font-size:14px">${esc(m.model)}</span>
              <span style="display:flex;gap:10px;align-items:center"><span class="mono" style="font-size:13px">${fmt(m.used)} / ${m.limit ? fmt(m.limit) : "?"}</span><span class="pill ${m.cooldown ? "warn" : "ok"}">${m.cooldown ? waitText(m.cooldown) : "Listo"}</span></span></div>
            <div class="bar"><div style="width:${m.limit ? Math.max(1.5, Math.min(100, (m.used / m.limit) * 100)) : 0}%;background:${m.limit && m.used / m.limit > 0.9 ? "var(--amber)" : "var(--teal)"}"></div></div>
          </div>`).join("")}
      </section>
    </div>
    <section class="card" aria-label="Últimos 7 días"><div class="card-head"><h2>Últimos 7 días</h2><span class="dim">Principal (turquesa) y respaldo (rosa)</span></div>
      <div class="week">${week.map((w: any, i: number) => `<div><span class="mono dim" style="font-size:11px">${w.mainN + w.backN}</span>
        <div class="stack" aria-hidden="true"><div style="height:${Math.round((w.backN / top) * 100)}px;border-radius:6px 6px 2px 2px;background:var(--pink)"></div><div style="height:${Math.round((w.mainN / top) * 100)}px;border-radius:2px 2px 6px 6px;background:var(--teal)"></div></div>
        <span style="font-size:12px;color:${i === 6 ? "var(--teal-l)" : "var(--dim)"}">${esc(dayName(w.day, i))}</span></div>`).join("")}</div>
    </section>`;
}

// ---------- Logs ----------
const LOG_FILTERS: [string, string, (l: LogLine) => boolean][] = [
  ["all", "Todo", () => true],
  ["error", "Errores", (l) => l.lvl === "WARNING" || l.lvl === "ERROR"],
  ["gemini", "Gemini", (l) => l.src === "llm"],
  ["wake", "Palabra clave", (l) => l.src === "wakeword"],
  ["tools", "Herramientas", (l) => l.src.startsWith("tools")],
];
interface LogLine { t: string; lvl: string; src: string; msg: string }
let logFilter = "all";
let logQuery = "";
let logPaused = false;
let logLines: LogLine[] = [];

function renderLogs(): void {
  byId("view")!.innerHTML = `
    ${head("LOGS", "Qué está pasando", "cache/core.log en vivo. Solo lectura: el panel nunca borra los logs.")}
    <div class="toolbar">
      <div class="chips" role="group" aria-label="Filtrar">${LOG_FILTERS.map(([id, label]) => `<button type="button" class="chip" data-filter="${id}" aria-pressed="${id === logFilter}">${label}</button>`).join("")}</div>
      <div class="chips"><label for="log-q" class="sr">Buscar en el log</label><input id="log-q" class="search" type="search" placeholder="Buscar…" value="${esc(logQuery)}">
        <button type="button" class="chip" id="log-pause" aria-pressed="${logPaused}">${logPaused ? "Seguir" : "Pausar"}</button></div>
    </div>
    <div id="logbox" class="logbox" aria-live="off"></div>`;
  paintLogs(true);
}

async function refreshLogs(): Promise<void> {
  if (logPaused || !isTauri) return;
  try {
    const text = await invoke<string>("read_log", { lines: 1500 });
    const re = /^(\d\d:\d\d:\d\d(?:\.\d{3})?) \[(\w+)\] ([\w.]+): (.*)$/;
    logLines = text.split(/\r?\n/).map((l) => re.exec(l)).filter(Boolean).map((m) => ({ t: m![1], lvl: m![2], src: m![3].replace(/^miku\./, "").replace(/^websockets\./, "ws."), msg: m![4] }));
  } catch (err) {
    console.warn("[Panel] log:", err);
  }
  if (current.id === "logs") paintLogs(false);
}

function paintLogs(jump: boolean): void {
  const box = byId("logbox");
  if (!box) return;
  const atBottom = jump || box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  const keep = LOG_FILTERS.find(([id]) => id === logFilter)![2];
  const q = logQuery.toLowerCase();
  const shown = logLines.filter((l) => keep(l) && (!q || l.msg.toLowerCase().includes(q))).slice(-400);
  box.innerHTML = shown.length
    ? shown.map((l) => `<div class="logline${l.lvl === "WARNING" ? " warn" : l.lvl === "ERROR" ? " err" : ""}"><span class="dim">${esc(l.t)}</span><span style="color:${l.lvl === "WARNING" ? "var(--amber)" : l.lvl === "ERROR" ? "var(--pink-l)" : "var(--teal-l)"}">${esc(l.lvl === "WARNING" ? "WARN" : l.lvl)}</span><span style="color:#9db3b1">${esc(l.src)}</span><span style="color:var(--soft)">${esc(l.msg)}</span></div>`).join("")
    : `<div class="dim" style="padding:30px 8px">Nada de este tipo en las últimas líneas.</div>`;
  if (atBottom) box.scrollTop = box.scrollHeight;
}

// ---------- loop and events ----------
async function tick(): Promise<void> {
  if (document.hidden || !current.refresh) return;
  const now = performance.now();
  if (now - lastRefresh < (current.every ?? 2) * 1000 - 50) return;
  lastRefresh = now;
  await current.refresh();
}

document.addEventListener("click", (ev) => {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("[data-go],[data-filter],#power,#log-pause");
  if (!el) return;
  if (el.dataset.go) go(el.dataset.go);
  else if (el.dataset.filter) {
    logFilter = el.dataset.filter;
    document.querySelectorAll<HTMLElement>("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filter === logFilter)));
    paintLogs(true);
  } else if (el.id === "power") void togglePower();
  else if (el.id === "log-pause") {
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

// Hidden panel: no polling, no Live2D drawing
document.addEventListener("visibilitychange", () => {
  if (current.id !== "inicio") return;
  if (document.hidden) live2d.stopTicker();
  else live2d.startTicker();
});

link.onEvent = (msg) => {
  onChatEvent(msg);
  if (msg.type === "state") {
    state.speaking = msg.value === "speaking";
    if (current.id === "inicio") paintPower();
  }
};

async function bootstrap(): Promise<void> {
  if (isTauri) {
    state.backendOn = await invoke<boolean>("backend_state").catch(() => false);
    await listen<boolean>("backend-changed", (ev) => {
      state.backendOn = ev.payload;
      if (state.backendOn) link.connect();
      if (current.id === "inicio") paintPower();
      lastRefresh = 0;
    });
  } else {
    state.backendOn = true; // in a plain browser (vite dev or preview) there is no Rust to ask: the WebSocket decides
  }
  if (state.backendOn) link.connect();
  renderNav();
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
