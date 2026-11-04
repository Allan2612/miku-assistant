/**
 * Almacenamiento: what Miku takes on disk, part by part (core/storage.py, run by Rust: works with Miku off), and the
 * two things that can be freed safely. The logs are never offered.
 */

import { invoke } from "@tauri-apps/api/core";
import { ask, byId, esc, head, loading, isTauri, size, toast } from "./shared";

interface Item { key: string; name: string; what: string; bytes: number; torch?: number; clean?: string }
interface Scan { items: Item[]; total: number; free: number; disk: number; drive: string; installed: boolean }

const COLORS: Record<string, string> = {
  runtime: "#39c5bb", speech: "#7eb6ff", models: "#b59cff", program: "#7ff3e8",
  wake: "#f2b544", logs: "#8fa6a4", voice: "#ff5aaa", data: "#d5e5e3", unused: "#ff7b72",
};
let scan: Scan | null = null;

export function renderStorage(): void {
  byId("view")!.innerHTML = `${head("Almacenamiento", "Lo que ocupa Miku en tu disco. Se mide cada vez que abres esta página.", `<button type="button" class="chip" id="st-again">Volver a medir</button>`)}
    <div id="st" class="stack">${loading("Midiendo el disco… tarda unos segundos")}</div>`;
  byId("view")!.onclick = onClick;
  if (!isTauri) {
    byId("st")!.innerHTML = `<div class="offline">El disco solo se mide desde la app.</div>`;
    return;
  }
  void measure();
}

async function measure(): Promise<void> {
  try {
    scan = JSON.parse(await invoke<string>("storage_scan"));
    paint();
  } catch (err) {
    const box = byId("st");
    if (box) box.innerHTML = `<div class="offline">No pude medir el disco: ${esc(err)}</div>`;
  }
}

function paint(): void {
  const box = byId("st");
  if (!box || !scan) return;
  const s = scan;
  const items = [...s.items].sort((a, b) => b.bytes - a.bytes);
  const pct = (n: number) => (s.total ? (n / s.total) * 100 : 0);
  const share = (n: number) => { const p = pct(n); return p >= 1 ? `${Math.round(p)} %` : "<1 %"; };
  box.innerHTML = `
    <section class="card" aria-label="Total">
      <div class="card-head"><div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap"><b class="mono" style="font-size:34px;font-weight:500;color:var(--teal-l)">${size(s.total)}</b>
        <span class="muted">en total</span></div>
        <span class="dim">Disco ${esc(s.drive.replace(/\\$/, ""))} · quedan ${size(s.free)} libres de ${size(s.disk)}</span></div>
      <div class="bar stacked" style="height:14px;border-radius:7px" role="img" aria-label="Reparto del espacio por partes">
        ${items.filter((i) => i.bytes).map((i) => `<div data-tip="${esc(`${i.name}: ${size(i.bytes)} (${share(i.bytes)})`)}" style="width:${pct(i.bytes).toFixed(2)}%;background:${COLORS[i.key] ?? "#56666a"}"></div>`).join("")}
      </div>
      <span class="dim">Python y PyTorch son lo grande: los usa la voz de Miku en la GPU. Los clips y los logs se limitan solos.</span>
    </section>
    <section class="card" aria-label="Partes">
      ${items.map((i) => `<div class="store-row">
        <span class="swatch" style="background:${COLORS[i.key] ?? "#56666a"}"></span>
        <div style="min-width:0"><b>${esc(i.name)}</b><span class="dim">${esc(i.what)}${i.torch ? ` · PyTorch ${size(i.torch)}` : ""}</span></div>
        <span class="mono" style="text-align:right">${size(i.bytes)}</span>
        <span class="mono dim" style="text-align:right">${share(i.bytes)}</span>
        <div class="actions">
          ${i.clean ? `<button type="button" class="btn small danger" data-clean="${esc(i.clean)}" data-name="${esc(i.name)}" data-size="${i.bytes}">Liberar</button>` : ""}
          <button type="button" class="btn small ghost" data-open="${esc(i.key)}">Abrir carpeta</button></div>
      </div>`).join("")}
    </section>
    <p class="dim" style="margin:0">Los logs nunca se borran desde aquí. ${s.installed ? "" : `Modo desarrollo: «Programa» cuenta solo el código de Miku (sin node_modules ni compilaciones).`}</p>`;
}

async function onClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.id === "st-again") {
    byId("st")!.innerHTML = `${loading("Midiendo el disco… tarda unos segundos")}`;
    await measure();
  } else if (el.dataset.clean) {
    const what = el.dataset.clean;
    const text = what === "voice"
      ? "Borra las frases fijas ya dichas. Miku las vuelve a crear la próxima vez que las diga (tarda un poco más esa vez)."
      : "Borra modelos de voz que Miku descargó antes y ya no carga. Si un día vuelves a elegirlos, se descargan otra vez.";
    if (!(await ask(`¿Liberar ${size(Number(el.dataset.size))}?`, `${el.dataset.name}: ${text}`, "Liberar", true))) return;
    el.setAttribute("disabled", "");
    try {
      const res = JSON.parse(await invoke<string>("storage_clean", { what }));
      toast(res.ok ? `Liberados ${size(res.freed)}.` : res.error);
    } catch (err) {
      toast(`No se pudo: ${err}`);
    }
    await measure();
  }
}
