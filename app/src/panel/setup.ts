/**
 * The first start of an installed Miku: API key, city, then the download of Python, her libraries and models
 * (installer/setup.ps1, run by Rust, its progress coming as "setup-progress" events). Development never sees it.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { byId, esc } from "./shared";

const STEPS = ["Bienvenida", "Tu API key de Gemini", "Tu ciudad", "Descargar componentes", "¡Lista!"];
// What setup.ps1 reports, in order, as the panel names it
const PARTS: [string, string][] = [
  ["data", "Tu carpeta de datos"],
  ["gpu", "Tarjeta gráfica"],
  ["uv", "Instalador de Python (uv)"],
  ["python", "Python 3.14"],
  ["libs", "Librerías de Miku · ~600 MB"],
  ["torch", "PyTorch con CUDA, para la voz · ~2,5 GB"],
  ["models", "Modelos de Whisper y de voz · ~900 MB"],
];

let step = 0;
let apiKey = "";
let city = "San José, Costa Rica";
let pct = 0;
let lastLine = "";
let failed = "";
const parts: Record<string, { state: string; msg: string }> = {};

export function renderSetup(): void {
  document.querySelector<HTMLElement>(".side")!.style.display = "none";
  const v = byId("view")!;
  v.style.alignItems = "center";
  v.style.justifyContent = "center";
  v.onclick = onClick;
  v.onkeydown = (ev) => {
    if (ev.key === "Enter" && (ev.target as HTMLElement).tagName === "INPUT") byId("next")?.click();
  };
  paint();
}

function paint(): void {
  const eq = Array.from({ length: 12 }, (_, i) => `<span style="height:${16 + Math.round(Math.abs(Math.sin(i * 1.3)) * 30)}px;animation-delay:${((i % 6) * 0.14).toFixed(2)}s"></span>`).join("");
  byId("view")!.innerHTML = `
    <div class="hero" style="width:100%;max-width:1000px"><div class="hero-in" style="padding:0;align-items:stretch;gap:0;overflow:hidden">
      <aside aria-label="Pasos" style="flex:1 1 250px;padding:34px 26px;background:var(--side);display:flex;flex-direction:column;gap:26px">
        <div class="brand" style="padding:0"><div class="brand-bars" aria-hidden="true"><span style="height:10px;background:#39c5bb"></span><span style="height:22px;background:#7ff3e8"></span><span style="height:15px;background:#39c5bb"></span><span style="height:8px;background:#ff5aaa"></span></div><div class="brand-name"><b>Miku Assistant</b><small>Primer arranque</small></div></div>
        <ol style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px">
          ${STEPS.map((s, i) => `<li style="display:flex;align-items:center;gap:12px;min-height:44px;padding:0 12px;border-radius:14px;background:${i === step ? "rgba(57,197,187,0.10)" : "transparent"}">
            <span aria-hidden="true" class="mono" style="flex:none;width:26px;height:26px;border-radius:13px;display:flex;align-items:center;justify-content:center;font-size:12px;background:${i < step ? "var(--teal)" : i === step ? "rgba(57,197,187,0.25)" : "rgba(255,255,255,0.06)"};color:${i < step ? "#04201e" : "var(--teal-l)"}">${i < step ? "✓" : i + 1}</span>
            <span style="font-size:14px;color:${i > step ? "#7e9593" : "var(--text)"}">${s}</span></li>`).join("")}
        </ol>
      </aside>
      <section style="flex:999 1 440px;padding:38px 42px;display:flex;flex-direction:column;gap:20px;min-width:0">
        <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap">
          <div style="display:flex;flex-direction:column;gap:10px"><span class="eyebrow">PASO ${step + 1} DE ${STEPS.length}</span><h1 style="font-size:32px">${STEPS[step]}</h1></div>
          <div class="eq${step === 3 && !failed ? " speaking" : ""}" aria-hidden="true" style="height:48px">${eq}</div>
        </div>
        ${body()}
      </section>
    </div></div>`;
}

function body(): string {
  const next = (label: string) => `<div style="display:flex;justify-content:flex-end;gap:10px"><button type="button" id="next" class="power off">${label}<span class="ic">→</span></button></div>`;
  if (step === 0)
    return `<p class="sub">Vamos a dejar a Miku lista en tu PC. Te pido dos datos y luego descargo lo que necesita para escucharte y hablarte: unos 4 GB, una sola vez.</p>
      <p class="dim">Tus datos (ajustes, memoria, recordatorios) se guardan en %APPDATA%\\Miku Assistant y nunca salen de tu PC salvo lo que le preguntas a Gemini.</p>${next("Empezar")}`;
  if (step === 1)
    return `<p class="sub">Miku piensa con Gemini, de Google. Crea una clave gratis en <b class="mono">aistudio.google.com/apikey</b> y pégala aquí.</p>
      <div class="field"><label for="key">API key</label><input id="key" class="input mono" type="password" autocomplete="off" value="${esc(apiKey)}" placeholder="AIza…"></div>
      <span class="dim">Puedes dejarla vacía y ponerla después en Configuración.</span>${next("Siguiente")}`;
  if (step === 2)
    return `<p class="sub">Para el clima: «¿va a llover hoy?».</p>
      <div class="field"><label for="city">Ciudad, País</label><input id="city" class="input" value="${esc(city)}"></div>
      <span class="dim">El micrófono es el predeterminado de Windows.</span>${next("Descargar e instalar")}`;
  if (step === 3) {
    const rows = PARTS.map(([id, label]) => {
      const p = parts[id];
      const st = p?.state ?? "wait";
      const [txt, cls] = st === "done" ? ["Listo", "ok"] : st === "skip" ? ["No hace falta", "off"] : st === "run" ? ["En curso…", "gem"] : ["En cola", "off"];
      const note = id === "gpu" && p?.msg ? (p.msg === "NVIDIA" ? "NVIDIA detectada: voz RVC en la GPU" : "Sin NVIDIA: Miku contestará con subtítulos") : p?.state === "skip" ? p.msg : "";
      return `<div class="list-row" style="min-height:46px"><span class="dot" style="background:${st === "done" ? "var(--teal)" : st === "run" ? "var(--pink)" : "#3a484c"}"></span>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px"><span style="font-size:14px">${esc(label)}</span>${note ? `<span class="dim">${esc(note)}</span>` : ""}</div>
        <span class="pill ${cls}">${txt}</span></div>`;
    }).join("");
    return `<div style="display:flex;justify-content:space-between;align-items:baseline"><b class="mono" style="font-size:28px;font-weight:500;color:var(--teal-l)">${pct} %</b><span class="dim">Puedes seguir usando la PC mientras tanto</span></div>
      <div class="bar" style="height:10px" role="progressbar" aria-label="Progreso" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
      <div>${rows}</div>
      <span class="mono dim" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(lastLine)}</span>
      ${failed ? `<div class="offline" style="color:var(--pink-l)">No se pudo terminar: ${esc(failed)}</div><div style="display:flex;justify-content:flex-end"><button type="button" id="retry" class="power off">Reintentar<span class="ic">↻</span></button></div>` : ""}`;
  }
  return `<p class="sub">Miku está lista. Di «Hey Miku» o pulsa Ctrl+Alt+M para llamarla.</p>${next("Abrir el panel")}`;
}

async function onClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.id === "next") {
    if (step === 1) apiKey = (byId("key") as HTMLInputElement).value.trim();
    if (step === 2) city = (byId("city") as HTMLInputElement).value.trim() || city;
    if (step === 4) {
      location.reload(); // the normal panel, now that Miku is ready
      return;
    }
    step += 1;
    paint();
    if (step === 3) void run();
  } else if (el.id === "retry") {
    void run();
  }
}

let unlisten: (() => void) | null = null;

async function run(): Promise<void> {
  failed = "";
  paint();
  unlisten ??= await listen<string>("setup-progress", (ev) => {
    const line = ev.payload;
    if (!line.startsWith("@@")) {
      lastLine = line.trim();
    } else {
      try {
        const p = JSON.parse(line.slice(2));
        if (p.state === "error") failed = p.msg;
        else {
          parts[p.step] = { state: p.state, msg: p.msg };
          pct = Math.max(pct, p.pct);
          if (p.msg && p.state === "run") lastLine = p.msg;
        }
      } catch {
        lastLine = line;
      }
    }
    if (step === 3) paint();
  });
  try {
    await invoke("setup_run", { apiKey, city });
    step = 4;
  } catch (err) {
    failed ||= String(err);
  }
  paint();
}
