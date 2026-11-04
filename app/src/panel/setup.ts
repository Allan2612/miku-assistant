/**
 * The first start of an installed Miku: a look at the PC, API key, city, then the download of Python, her libraries
 * and models (installer/setup.ps1, run by Rust, its progress coming as "setup-progress" events), a speed test, and
 * what to expect on this PC. Development never sees it.
 *
 * No NVIDIA card is not "Miku a medias": her voice and the retraining run on the CPU (CPU PyTorch), a bit slower.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { byId, comma, esc, loading, size } from "./shared";

const STEPS = ["Bienvenida", "Tu PC", "Tu API key de Gemini", "Tu ciudad", "Instalar", "¡Lista!"];
const INSTALL = 4;
// What setup.ps1 reports, in order, as the panel names it
const PARTS: [string, string][] = [
  ["data", "Tu carpeta de datos"],
  ["gpu", "Tarjeta gráfica"],
  ["uv", "Instalador de Python (uv)"],
  ["python", "Python 3.14"],
  ["libs", "Librerías de Miku · ~600 MB"],
  ["torch", "PyTorch: su voz y reentrenar «Hey Miku»"],
  ["models", "Modelos de Whisper y de voz · ~900 MB"],
  ["bench", "Prueba de velocidad de tu PC"],
];

interface Check { gpus: string[]; nvidia: boolean; cpu: string; cores: number; threads: number; ram: number; free: number; drive: string; mics: string[]; internet: boolean; battery: boolean }
interface Bench { audio_s: number; whisper: { model: string; seconds: number }; voice: { device: string; seconds: number; extra_s: number } }

let step = 0;
let apiKey = "";
let city = "San José, Costa Rica";
let pct = 0;
let lastLine = "";
let failed = "";
let pc: Check | null = null;
let checkError = "";
let bench: Bench | null = null;
let fastVoice = false;
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
          <div class="eq${step === INSTALL && !failed ? " speaking" : ""}" aria-hidden="true" style="height:48px">${eq}</div>
        </div>
        ${body()}
      </section>
    </div></div>`;
}

const next = (label: string, disabled = false) =>
  `<div style="display:flex;justify-content:flex-end;gap:10px"><button type="button" id="next" class="power off"${disabled ? " disabled" : ""}>${label}<span class="ic">→</span></button></div>`;

/** One line of the "Tu PC" step: ok, a note (works, with a cost) or a stop (cannot install like this). */
const row = (kind: "ok" | "note" | "stop", title: string, detail: string) =>
  `<div class="list-row" style="min-height:52px;align-items:flex-start;padding:10px 0"><span class="dot ${kind === "ok" ? "ok" : kind === "note" ? "warn" : "bad"}" style="margin-top:6px" aria-hidden="true"></span>
    <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:3px"><span style="font-size:14px">${title}</span><span class="dim">${detail}</span></div>
    <span class="pill ${kind === "ok" ? "ok" : kind === "note" ? "warn" : "bad"}">${kind === "ok" ? "Bien" : kind === "note" ? "Funciona" : "Falta"}</span></div>`;

/** Disk Miku needs: with CUDA PyTorch ~6.5 GB, with the CPU one ~3.5 GB; some room on top. */
const needDisk = (c: Check) => (c.nvidia ? 8 : 5) * 1024 ** 3;

function pcRows(c: Check): { html: string; blocked: boolean } {
  const gb = (n: number) => `${comma(n / 1024 ** 3, 0)} GB`;
  const gpu = c.gpus.join(", ") || "sin datos";
  const lines = [
    c.nvidia
      ? row("ok", `Gráficos: ${esc(gpu)}`, "Su voz va en la tarjeta: responde al instante.")
      : row("note", `Gráficos: ${esc(gpu)}`, "Sin NVIDIA su voz va por el procesador: todo funciona, cada respuesta tarda unos segundos más. Al final se mide cuánto."),
    c.cores >= 4
      ? row("ok", `Procesador: ${esc(c.cpu)}`, `${c.cores} núcleos, ${c.threads} hilos.`)
      : row("note", `Procesador: ${esc(c.cpu)}`, `${c.cores} núcleos: Miku tardará más en entenderte y en hablar.`),
    c.ram >= 8 * 1024 ** 3 ? row("ok", `Memoria: ${gb(c.ram)}`, "Miku usa unos 2–3 GB.") : row("note", `Memoria: ${gb(c.ram)}`, "Justa: cierra otros programas mientras la usas."),
    c.free >= needDisk(c)
      ? row("ok", `Disco ${esc(c.drive)} · ${size(c.free)} libres`, `Necesita unos ${gb(needDisk(c))}.`)
      : row("stop", `Disco ${esc(c.drive)} · ${size(c.free)} libres`, `Necesita unos ${gb(needDisk(c))}: libera espacio y vuelve a revisar.`),
    c.mics.length
      ? row("ok", "Micrófono", esc(c.mics.join(" · ")))
      : row("note", "Micrófono: ninguno", "Conecta uno para «Hey Miku». Mientras, puedes escribirle."),
    c.internet ? row("ok", "Internet", "Para descargar sus componentes y para Gemini.") : row("stop", "Internet: sin conexión", "Hace falta para instalar y para que Miku piense. Conéctate y vuelve a revisar."),
  ];
  if (c.battery) lines.push(row("note", "Funcionando con batería", "Conecta el cargador: con batería el procesador va más lento."));
  return { html: lines.join(""), blocked: c.free < needDisk(c) || !c.internet };
}

function body(): string {
  if (step === 0)
    return `<p class="sub">Vamos a dejar a Miku lista en tu PC, completa: palabra clave, su voz, herramientas y panel. Primero reviso tu PC, te pido dos datos y luego descargo lo que necesita, una sola vez.</p>
      <p class="dim">Tus datos (ajustes, memoria, recordatorios) se guardan en %APPDATA%\\Miku Assistant y nunca salen de tu PC salvo lo que le preguntas a Gemini.</p>${next("Empezar")}`;
  if (step === 1) {
    if (checkError) return `<div class="offline">No pude revisar tu PC: ${esc(checkError)}</div>${next("Seguir de todos modos")}`;
    if (!pc) return loading("Revisando tu PC…");
    const { html, blocked } = pcRows(pc);
    return `<div>${html}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <button type="button" id="recheck" class="btn ghost">Volver a revisar</button>
        <span class="msg ${blocked ? "bad" : "ok"}">${blocked ? "Resuelve lo que falta para seguir." : pc.nvidia ? "Todo listo para Miku completa." : "Todo listo: Miku irá completa, con su voz por el procesador."}</span></div>
      ${next("Siguiente", blocked)}`;
  }
  if (step === 2)
    return `<p class="sub">Miku piensa con Gemini, de Google. Crea una clave gratis en <b class="mono">aistudio.google.com/apikey</b> y pégala aquí.</p>
      <div class="field"><label for="key">API key</label><input id="key" class="input mono" type="password" autocomplete="off" value="${esc(apiKey)}" placeholder="AIza…"></div>
      <span class="dim">Puedes dejarla vacía y ponerla después en Configuración.</span>${next("Siguiente")}`;
  if (step === 3)
    return `<p class="sub">Para el clima: «¿va a llover hoy?».</p>
      <div class="field"><label for="city">Ciudad, País</label><input id="city" class="input" value="${esc(city)}"></div>
      <span class="dim">El micrófono es el predeterminado de Windows; se cambia luego en Configuración.</span>${next("Descargar e instalar")}`;
  if (step === INSTALL) {
    const rows = PARTS.map(([id, label]) => {
      const p = parts[id];
      const st = p?.state ?? "wait";
      const [txt, cls] = st === "done" ? ["Listo", "ok"] : st === "skip" ? ["Omitido", "off"] : st === "run" ? ["En curso…", "gem"] : ["En cola", "off"];
      const note = id === "gpu" && p?.msg ? (p.msg === "NVIDIA" ? "NVIDIA: su voz en la GPU" : "Gráficos integrados: su voz irá por el procesador") : p?.state === "skip" ? p.msg : "";
      return `<div class="list-row" style="min-height:46px"><span class="dot ${st === "done" ? "ok" : st === "run" ? "warn" : ""}"></span>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px"><span style="font-size:14px">${esc(label)}</span>${note ? `<span class="dim">${esc(note)}</span>` : ""}</div>
        <span class="pill ${cls}">${txt}</span></div>`;
    }).join("");
    return `<div style="display:flex;justify-content:space-between;align-items:baseline"><b class="mono" style="font-size:28px;font-weight:500;color:var(--teal-l)">${pct} %</b><span class="dim">Puedes seguir usando la PC mientras tanto</span></div>
      <div class="bar" style="height:10px" role="progressbar" aria-label="Progreso" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
      <div>${rows}</div>
      <span class="mono dim" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(lastLine)}</span>
      ${failed ? `<div class="offline" style="color:var(--coral)">No se pudo terminar: ${esc(failed)}</div><div style="display:flex;justify-content:flex-end"><button type="button" id="retry" class="power off">Reintentar<span class="ic">↻</span></button></div>` : ""}`;
  }
  return done();
}

/** The last step: what this PC measured, and the voice choice when her voice runs on the CPU. */
function done(): string {
  const b = bench;
  const measured = b
    ? `<div>
        ${row("ok", "Entenderte", `Whisper «${esc(b.whisper.model)}»: ${comma(b.whisper.seconds)} s para una frase de ${comma(b.audio_s)} s.`)}
        ${row(b.voice.device === "cuda" ? "ok" : "note", `Su voz: en ${b.voice.device === "cuda" ? "la tarjeta gráfica" : "el procesador"}`, b.voice.device === "cuda" ? "Responde al instante." : `Cada respuesta tarda unos ${comma(b.voice.extra_s)} s más en hablar.`)}
      </div>`
    : `<span class="dim">No se pudo medir la velocidad: Miku usa los ajustes normales.</span>`;
  const choice = b && b.voice.device !== "cuda"
    ? `<div class="field"><span class="label">¿Con qué voz habla?</span><div class="chips" role="radiogroup" aria-label="Voz">
        <button type="button" class="chip" role="radio" data-voice="miku" aria-pressed="${!fastVoice}" aria-checked="${!fastVoice}">Su voz (recomendado)</button>
        <button type="button" class="chip" role="radio" data-voice="fast" aria-pressed="${fastVoice}" aria-checked="${fastVoice}">Voz rápida: otra voz, al instante</button></div>
        <span class="dim">Se cambia cuando quieras en Configuración › Voz de Miku.</span></div>`
    : "";
  return `<p class="sub">Miku está lista. Di «Hey Miku» o pulsa Ctrl+Alt+M para llamarla.</p>${measured}${choice}
    ${pc?.battery ? `<span class="msg warn">Consejo: conecta el cargador, con batería va más lenta.</span>` : ""}
    ${next("Abrir el panel")}`;
}

async function check(): Promise<void> {
  pc = null;
  checkError = "";
  paint();
  try {
    pc = JSON.parse(await invoke<string>("setup_check"));
  } catch (err) {
    checkError = String(err);
  }
  if (step === 1) paint();
}

async function onClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.id === "next") {
    if (step === 2) apiKey = (byId("key") as HTMLInputElement).value.trim();
    if (step === 3) city = (byId("city") as HTMLInputElement).value.trim() || city;
    if (step === STEPS.length - 1) {
      if (fastVoice) {
        el.setAttribute("disabled", "");
        // The backend already started with her voice on: it reads config.yaml only when it starts
        await invoke("settings_set", { changes: JSON.stringify({ rvc_enabled: false }) })
          .then(() => invoke("backend_restart"))
          .catch(() => {});
      }
      location.reload(); // the normal panel, now that Miku is ready
      return;
    }
    step += 1;
    paint();
    if (step === 1) void check();
    if (step === INSTALL) void run();
  } else if (el.id === "recheck") void check();
  else if (el.id === "retry") void run();
  else if (el.dataset.voice) {
    fastVoice = el.dataset.voice === "fast";
    paint();
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
          if (p.step === "bench" && p.state === "done") {
            bench = JSON.parse(p.msg); // core/bench.py's summary
            p.msg = "";
          }
          parts[p.step] = { state: p.state, msg: p.msg };
          pct = Math.max(pct, p.pct);
          if (p.msg && p.state === "run") lastLine = p.msg;
        }
      } catch {
        lastLine = line;
      }
    }
    if (step === INSTALL) paint();
  });
  try {
    await invoke("setup_run", { apiKey, city });
    step = STEPS.length - 1;
  } catch (err) {
    failed ||= String(err);
  }
  paint();
}
