/**
 * Panel pages that change things (phase 3): Configuración, Herramientas, Funciones, Recordatorios, Memoria.
 * Settings and tools go through Rust (a short Python process: they work with Miku off); reminders, notes and
 * memory through the backend, with the same tools Miku uses.
 */

import { invoke } from "@tauri-apps/api/core";
import { byId, comma, esc, head, icon, isTauri, link, offlineNote, state } from "./shared";

const X_ICON = "M6 6l12 12M18 6 6 18";
const CHECK_ICON = "M5 12.5l4.5 4.5L19 7.5";
const view = () => byId("view")!;

function say(id: string, text: string, kind: "" | "ok" | "bad" = ""): void {
  const el = byId(id);
  if (el) {
    el.textContent = text;
    el.className = `msg${kind ? ` ${kind}` : ""}`;
  }
}

const switchHtml = (id: string, label: string, help: string, on: boolean) =>
  `<div class="switch-row"><div><b>${esc(label)}</b><span class="dim">${esc(help)}</span></div>
   <button type="button" class="switch" role="switch" id="${id}" aria-checked="${on}" aria-label="${esc(label)}"><span></span></button></div>`;

const saveBar = (id: string, label: string) =>
  `<div class="savebar"><span id="${id}-msg" class="msg"></span>
   <button type="button" id="${id}-save" class="power off">${esc(label)}<span class="ic">${icon(CHECK_ICON, 16)}</span></button></div>`;

/** Saves settings; restarts the backend if it is on (it reads config.yaml and .env only when it starts). */
async function saveSettings(changes: Record<string, unknown>, msgId: string, btn: HTMLButtonElement): Promise<boolean> {
  btn.disabled = true;
  say(msgId, "Guardando…");
  try {
    const res = JSON.parse(await invoke<string>("settings_set", { changes: JSON.stringify(changes) }));
    if (!res.ok) {
      say(msgId, res.error || "No se pudo guardar.", "bad");
      return false;
    }
    if (state.backendOn) {
      say(msgId, "Guardado. Reiniciando a Miku…");
      await invoke("backend_restart");
      say(msgId, "Listo: Miku ya usa los ajustes nuevos.", "ok");
    } else {
      say(msgId, "Guardado. Se aplicará cuando enciendas a Miku.", "ok");
    }
    return true;
  } catch (err) {
    say(msgId, `No se pudo guardar: ${err}`, "bad");
    return false;
  } finally {
    btn.disabled = false;
  }
}

// ---------- Configuración ----------
let cfg: any = null;
let draft: any = null;

export function renderConfig(): void {
  view().innerHTML = `${head("CONFIGURACIÓN", "Ajustes de Miku", "Se guardan en config.yaml y .env. Las claves nunca salen de tu PC.")}<div id="cfg"><span class="dim">Cargando…</span></div>`;
  if (!isTauri) {
    byId("cfg")!.innerHTML = `<div class="offline">Los ajustes solo se cambian desde la app.</div>`;
    return;
  }
  invoke<string>("settings_get")
    .then((text) => {
      cfg = JSON.parse(text);
      draft = { ...cfg, vocabulary: [...cfg.vocabulary] };
      paintConfig();
    })
    .catch((err) => (byId("cfg")!.innerHTML = `<div class="offline">No pude leer los ajustes: ${esc(err)}</div>`));
}

function paintConfig(): void {
  const d = draft;
  byId("cfg")!.innerHTML = `
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(360px,1fr))">
      <section class="card" aria-label="Gemini"><h2>Gemini</h2>
        <div class="field"><label for="apikey">API key</label>
          <div class="inline"><input id="apikey" class="input mono" type="password" autocomplete="off" placeholder="${cfg.gemini.has_key ? `Guardada: …${esc(cfg.gemini.hint)}` : "Pega tu API key de Google AI Studio"}"><button type="button" id="testkey" class="btn">Probar</button></div>
          <span id="keymsg" class="msg">${cfg.gemini.has_key ? "Déjala vacía para no cambiarla." : ""}</span></div>
        <div class="field"><label for="model">Modelo principal</label>
          <select id="model" class="select">${cfg.gemini.models.map((m: string) => `<option${m === d.gemini.model ? " selected" : ""}>${esc(m)}</option>`).join("")}</select></div>
      </section>
      <section class="card" aria-label="Voz y palabra clave"><h2>Voz y palabra clave</h2>
        ${switchHtml("sw-rvc", "Voz de Miku (RVC)", "Usa la GPU. Apagada: solo subtítulos.", d.rvc_enabled)}
        ${switchHtml("sw-wake", "Escuchar «Hey Miku»", "Apagada: solo con el atajo.", d.wakeword_enabled)}
        <div class="field"><div class="card-head"><label for="thr">Umbral de la palabra clave</label><span id="thrv" class="mono" style="color:var(--teal-l)">${comma(d.threshold, 2)}</span></div>
          <input id="thr" class="range" type="range" min="0.2" max="0.8" step="0.05" value="${d.threshold}">
          <span class="dim">Más bajo: te oye mejor, pero se activa sola más a menudo.</span></div>
      </section>
      <section class="card" aria-label="Atajo y micrófono"><h2>Atajo y micrófono</h2>
        <div class="field"><label for="hotkey">Atajo para llamarla</label><input id="hotkey" class="input mono" readonly value="${esc(d.hotkey)}">
          <span class="dim">Se cambia en config.yaml y necesita volver a compilar la app.</span></div>
        <div class="field"><label for="mic">Micrófono</label><input id="mic" class="input" readonly value="El predeterminado de Windows">
          <span class="dim">Cámbialo en Configuración de Windows › Sonido.</span></div>
      </section>
      <section class="card" aria-label="Clima y OBS"><h2>Clima y OBS</h2>
        <div class="field"><label for="city">Ciudad del clima (Ciudad, País)</label><input id="city" class="input" value="${esc(d.weather_city)}"></div>
        <div class="field"><label for="obspw">Contraseña del servidor WebSocket de OBS</label>
          <input id="obspw" class="input mono" type="password" autocomplete="off" placeholder="${cfg.obs.has_password ? "Guardada. Vacía: no se cambia" : "Herramientas › Ajustes del servidor WebSocket"}"></div>
      </section>
    </div>
    <section class="card" aria-label="Palabras que Whisper debe conocer"><h2>Palabras que Whisper debe conocer</h2>
      <span class="dim">Nombres y canciones que dices a menudo. Solo palabras, nunca órdenes enteras.</span>
      <div id="words" class="chips"></div>
    </section>
    ${saveBar("cfg", state.backendOn ? "Guardar y reiniciar Miku" : "Guardar")}`;
  paintWords();
  view().onclick = onConfigClick;
  const onEdit = (ev: Event) => {
    const el = ev.target as HTMLInputElement;
    if (el.id === "thr") {
      draft.threshold = Number(el.value);
      byId("thrv")!.textContent = comma(draft.threshold, 2);
    } else if (el.id === "city") draft.weather_city = el.value;
    else if (el.id === "model") draft.gemini = { ...draft.gemini, model: el.value };
  };
  view().oninput = onEdit;
  view().onchange = onEdit; // the select fires change, not input
  view().onkeydown = (ev) => {
    const el = ev.target as HTMLInputElement;
    if (el.id === "newword" && ev.key === "Enter" && el.value.trim()) {
      draft.vocabulary.push(el.value.trim());
      paintWords();
      byId("newword")?.focus();
    }
  };
}

function paintWords(): void {
  byId("words")!.innerHTML =
    draft.vocabulary.map((w: string, i: number) => `<span class="word">${esc(w)}<button type="button" data-word="${i}" aria-label="Quitar ${esc(w)}">${icon(X_ICON, 10)}</button></span>`).join("") +
    `<label for="newword" class="sr">Añadir palabra</label><input id="newword" class="input" style="width:140px;min-height:32px;border-radius:999px;border-style:dashed" placeholder="Añadir…">`;
}

async function onConfigClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.word !== undefined) {
    draft.vocabulary.splice(Number(el.dataset.word), 1);
    paintWords();
  } else if (el.id === "sw-rvc" || el.id === "sw-wake") {
    const key = el.id === "sw-rvc" ? "rvc_enabled" : "wakeword_enabled";
    draft[key] = !draft[key];
    el.setAttribute("aria-checked", String(draft[key]));
  } else if (el.id === "testkey") {
    say("keymsg", "Probando…");
    try {
      const res = JSON.parse(await invoke<string>("settings_testkey", { key: (byId("apikey") as HTMLInputElement).value }));
      say("keymsg", res.ok ? "La API key funciona." : res.error, res.ok ? "ok" : "bad");
    } catch (err) {
      say("keymsg", String(err), "bad");
    }
  } else if (el.id === "cfg-save") {
    const changes: Record<string, unknown> = {};
    if (draft.gemini.model !== cfg.gemini.model) changes.model = draft.gemini.model;
    for (const k of ["rvc_enabled", "wakeword_enabled", "threshold", "weather_city"]) if (draft[k] !== cfg[k]) changes[k] = draft[k];
    if (draft.vocabulary.join("|") !== cfg.vocabulary.join("|")) changes.vocabulary = draft.vocabulary;
    const key = (byId("apikey") as HTMLInputElement).value.trim();
    const obs = (byId("obspw") as HTMLInputElement).value.trim();
    if (key) changes.api_key = key;
    if (obs) changes.obs_password = obs;
    if (!Object.keys(changes).length) {
      say("cfg-msg", "No hay cambios.");
      return;
    }
    if (await saveSettings(changes, "cfg-msg", el as HTMLButtonElement)) {
      cfg = JSON.parse(await invoke<string>("settings_get"));
      draft = { ...cfg, vocabulary: [...cfg.vocabulary] };
      (byId("apikey") as HTMLInputElement).value = "";
      (byId("obspw") as HTMLInputElement).value = "";
    }
  }
}

// ---------- Herramientas ----------
let tools: any[] = [];
let disabled = new Set<string>();
let savedDisabled = "";
let toolQuery = "";

export function renderTools(): void {
  view().innerHTML = `${head("HERRAMIENTAS", "Lo que Miku puede tocar", "Una herramienta apagada desaparece para Gemini y tampoco la usan las frases locales.")}
    <div class="toolbar"><div class="chips"><span class="pill ok">FRASE LOCAL: sin gastar cuota</span><span class="pill warn">PIDE CONFIRMACIÓN</span></div>
      <div><label for="tq" class="sr">Buscar herramienta</label><input id="tq" class="search" type="search" placeholder="Buscar…" value="${esc(toolQuery)}"></div></div>
    <section class="card" aria-label="Herramientas"><div id="tlist"><span class="dim">Cargando…</span></div></section>
    ${saveBar("tools", state.backendOn ? "Guardar y reiniciar Miku" : "Guardar")}`;
  view().onclick = onToolsClick;
  view().oninput = (ev) => {
    const el = ev.target as HTMLInputElement;
    if (el.id === "tq") {
      toolQuery = el.value;
      paintTools();
    }
  };
  if (!isTauri) return;
  Promise.all([invoke<string>("settings_tools"), invoke<string>("settings_get")])
    .then(([t, s]) => {
      tools = JSON.parse(t);
      disabled = new Set(JSON.parse(s).disabled_tools);
      savedDisabled = [...disabled].sort().join("|");
      paintTools();
    })
    .catch((err) => (byId("tlist")!.innerHTML = `<span class="msg bad">${esc(err)}</span>`));
}

function paintTools(): void {
  const q = toolQuery.toLowerCase();
  const shown = tools.filter((t) => !q || t.name.includes(q) || t.description.toLowerCase().includes(q));
  byId("tlist")!.innerHTML = shown.length
    ? shown.map((t) => `<div class="tool"><div class="tool-name"><code>${esc(t.name)}</code>${t.local ? `<span class="pill ok">FRASE LOCAL</span>` : ""}${t.destructive ? `<span class="pill warn">PIDE CONFIRMACIÓN</span>` : ""}</div>
        <p>${esc(t.description)}</p>
        <button type="button" class="switch" role="switch" data-tool="${esc(t.name)}" aria-checked="${!disabled.has(t.name)}" aria-label="${esc(t.name)}"><span></span></button></div>`).join("")
    : `<span class="dim">Ninguna herramienta coincide.</span>`;
  const changed = [...disabled].sort().join("|") !== savedDisabled;
  say("tools-msg", changed ? `${disabled.size} apagada(s) · cambios sin guardar` : `${tools.length - disabled.size} de ${tools.length} encendidas`);
}

async function onToolsClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.tool) {
    const name = el.dataset.tool;
    if (disabled.has(name)) disabled.delete(name);
    else disabled.add(name);
    paintTools();
  } else if (el.id === "tools-save") {
    if ([...disabled].sort().join("|") === savedDisabled) {
      say("tools-msg", "No hay cambios.");
      return;
    }
    if (await saveSettings({ disabled_tools: [...disabled].sort() }, "tools-msg", el as HTMLButtonElement)) {
      savedDisabled = [...disabled].sort().join("|");
    }
  }
}

// ---------- Funciones (docs/funciones.md) ----------
let docHtml = "";

/** The small markdown funciones.md uses: headings, tables, lists, paragraphs, bold, code. Quoted phrases in tables
 *  become buttons that send the phrase to Miku. Everything is escaped first. */
function markdown(src: string): string {
  const fmt = (t: string) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  // In a cell, ** around a phrase would split from it: the first column is bold by style anyway
  const cell = (t: string) =>
    t.replace(/\*\*/g, "").split(/("[^"]+")/).map((part) => (/^"[^"]+"$/.test(part) ? `<button type="button" class="phrase" data-say="${esc(part.slice(1, -1))}">${esc(part)}</button>` : fmt(part))).join("");
  const lines = src.split(/\r?\n/);
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^#\s/.test(l) || !l.trim()) continue;
    if (/^##\s/.test(l)) out.push(`<h2>${fmt(l.slice(3))}</h2>`);
    else if (/^###\s/.test(l)) out.push(`<h3>${fmt(l.slice(4))}</h3>`);
    else if (l.startsWith("|")) {
      const rows: string[][] = [];
      for (; i < lines.length && lines[i].startsWith("|"); i++) {
        if (!/^\|(\s*:?-{3,}:?\s*\|)+$/.test(lines[i].trim())) rows.push(lines[i].trim().slice(1, -1).split(" | ").map((c) => c.trim()));
      }
      i--;
      const [hdr, ...body] = rows;
      out.push(`<table><thead><tr>${hdr.map((c) => `<th>${fmt(c)}</th>`).join("")}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${cell(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
    } else if (/^\s*-\s/.test(l)) {
      const items: string[] = [];
      for (; i < lines.length && /^\s*(-\s|\s{2,}\S)/.test(lines[i]); i++) {
        if (/^\s*-\s/.test(lines[i])) items.push(lines[i].replace(/^\s*-\s/, ""));
        else items[items.length - 1] += ` ${lines[i].trim()}`;
      }
      i--;
      out.push(`<ul>${items.map((t) => `<li>${fmt(t)}</li>`).join("")}</ul>`);
    } else {
      const para: string[] = [];
      for (; i < lines.length && lines[i].trim() && !/^(#|\||\s*-\s)/.test(lines[i]); i++) para.push(lines[i].trim());
      i--;
      out.push(`<p>${fmt(para.join(" "))}</p>`);
    }
  }
  return out.join("\n");
}

export function renderFunctions(): void {
  view().innerHTML = `${head("FUNCIONES", "Qué puedes pedirle", "Pulsa una frase para que Miku la reciba como si se la escribieras.")}
    <div class="toolbar"><span id="fmsg" class="msg">${state.backendOn ? "" : "Enciende a Miku para probar las frases."}</span>
      <div><label for="fq" class="sr">Buscar</label><input id="fq" class="search" type="search" placeholder="Buscar: clima, OBS, volumen…"></div></div>
    <section class="card md" id="doc"><span class="dim">Cargando…</span></section>`;
  view().onclick = (ev) => {
    const el = (ev.target as HTMLElement).closest<HTMLElement>(".phrase");
    if (!el?.dataset.say) return;
    if (!state.backendOn || !link.send({ type: "text_input", text: el.dataset.say })) {
      say("fmsg", "Enciende a Miku para probar las frases.", "bad");
      return;
    }
    say("fmsg", `Enviado: «${el.dataset.say}». Miku te contesta con su voz.`, "ok");
  };
  view().oninput = (ev) => {
    const el = ev.target as HTMLInputElement;
    if (el.id !== "fq") return;
    const q = el.value.toLowerCase();
    byId("doc")!.querySelectorAll<HTMLElement>("tbody tr, li, p").forEach((row) => {
      row.style.display = !q || row.textContent!.toLowerCase().includes(q) ? "" : "none";
    });
  };
  const show = (html: string) => (byId("doc")!.innerHTML = html);
  if (docHtml) show(docHtml);
  else if (isTauri)
    invoke<string>("read_functions_doc")
      .then((text) => show((docHtml = markdown(text))))
      .catch((err) => show(`<span class="msg bad">No pude leer docs/funciones.md: ${esc(err)}</span>`));
}

// ---------- Recordatorios y pendientes ----------
let pendingNotes: string[] = [];

export function renderReminders(): void {
  view().innerHTML = `${head("RECORDATORIOS", "Avisos y pendientes", "Los mismos que creas hablando con Miku: aquí los ves, los creas y los cancelas.")}<div id="rem"></div>`;
  view().onclick = onRemindersClick;
  view().onchange = (ev) => {
    if ((ev.target as HTMLElement).id === "rkind") {
      const atTime = (byId("rkind") as HTMLSelectElement).value === "at";
      byId("rmin-f")!.style.display = atTime ? "none" : "";
      byId("rat-f")!.style.display = atTime ? "" : "none";
    }
  };
  view().onkeydown = (ev) => {
    if (ev.key === "Enter" && (ev.target as HTMLElement).id === "pnew") byId("padd")?.click();
  };
  if (!state.backendOn) {
    byId("rem")!.innerHTML = offlineNote();
    return;
  }
  byId("rem")!.innerHTML = `
    <div class="row-wrap">
      <section class="card" style="flex:2 1 440px" aria-label="Recordatorios y temporizadores"><h2>Recordatorios y temporizadores</h2><div id="tl"><span class="dim">Cargando…</span></div></section>
      <section class="card" style="flex:1 1 300px" aria-label="Nuevo recordatorio"><h2>Nuevo recordatorio</h2>
        <div class="field"><label for="rtext">Qué te recuerdo</label><input id="rtext" class="input" placeholder="Ej: tomar agua"></div>
        <div class="field"><label for="rkind">Cuándo</label><select id="rkind" class="select"><option value="in">Dentro de unos minutos</option><option value="at">A una hora</option></select></div>
        <div class="field" id="rmin-f"><label for="rmin">Minutos</label><input id="rmin" class="input" type="number" min="1" max="10080" value="30"></div>
        <div class="field" id="rat-f" style="display:none"><label for="rat">Hora</label><input id="rat" class="input" type="time" value="09:00"></div>
        <div class="field"><label for="revery">Repetir</label><select id="revery" class="select"><option value="0">No</option><option value="1440">Todos los días</option><option value="10080">Cada semana</option></select></div>
        <button type="button" id="radd" class="btn">Crear recordatorio</button><span id="rmsg" class="msg"></span>
      </section>
    </div>
    <section class="card" aria-label="Pendientes"><h2>Pendientes</h2><div id="pl"></div>
      <div class="inline"><label for="pnew" class="sr">Nuevo pendiente</label><input id="pnew" class="input" placeholder="Apunta un pendiente…"><button type="button" id="padd" class="btn">Apuntar</button></div>
      <span id="pmsg" class="msg"></span></section>`;
}

export async function refreshReminders(): Promise<void> {
  if (!state.backendOn || !byId("tl")) return;
  const d = await link.request("timers");
  if (!d || !byId("tl")) return;
  pendingNotes = d.pending;
  byId("tl")!.innerHTML = d.timers.length
    ? d.timers.map((t: any) => `<div class="list-row" style="min-height:52px"><span class="pill ${t.reminder ? "ok" : "off"}">${t.reminder ? "AVISO" : "TEMPORIZADOR"}</span>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px"><span style="font-size:14px">${esc(t.text)}</span><span class="dim">${esc(t.when)}</span></div>
        <button type="button" class="btn small danger" data-cancel="${t.id}">Cancelar</button></div>`).join("")
    : `<span class="dim">No hay avisos activos.</span>`;
  byId("pl")!.innerHTML = d.pending.length
    ? d.pending.map((p: string, i: number) => `<div class="list-row"><span style="flex:1;font-size:14px">${esc(p)}</span>
        <button type="button" class="btn small" data-done="${i}">Hecho</button><button type="button" class="btn small ghost" data-del="${i}">Borrar</button></div>`).join("")
    : `<span class="dim">No tienes pendientes.</span>`;
}

async function doAndSay(action: string, args: Record<string, unknown>, msgId: string): Promise<void> {
  const res = await link.request(`do:${action}`, args);
  say(msgId, res ? res.result : "Miku no respondió.", res?.ok ? "ok" : "bad");
  await refreshReminders();
}

async function onRemindersClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.cancel) await doAndSay("cancel_timer", { id: Number(el.dataset.cancel) }, "rmsg");
  else if (el.dataset.done) await doAndSay("note_done", { text: pendingNotes[Number(el.dataset.done)] }, "pmsg");
  else if (el.dataset.del) await doAndSay("note_delete", { text: pendingNotes[Number(el.dataset.del)] }, "pmsg");
  else if (el.id === "padd") {
    const input = byId("pnew") as HTMLInputElement;
    if (!input.value.trim()) return;
    await doAndSay("note_add", { text: input.value.trim() }, "pmsg");
    input.value = "";
  } else if (el.id === "radd") {
    const text = (byId("rtext") as HTMLInputElement).value.trim();
    if (!text) {
      say("rmsg", "Escribe qué te recuerdo.", "bad");
      return;
    }
    const atTime = (byId("rkind") as HTMLSelectElement).value === "at";
    await doAndSay("remind", {
      text,
      minutes: atTime ? 0 : Number((byId("rmin") as HTMLInputElement).value),
      at: atTime ? (byId("rat") as HTMLInputElement).value : "",
      every_minutes: Number((byId("revery") as HTMLSelectElement).value),
    }, "rmsg");
    (byId("rtext") as HTMLInputElement).value = "";
  }
}

// ---------- Memoria ----------
let facts: string[] = [];
let editing = -1;

export function renderMemory(): void {
  view().innerHTML = `${head("MEMORIA", "Lo que Miku recuerda", "Los datos tuyos que usa en cada respuesta, y lo que hablasteis cada día.")}<div id="mem"></div>`;
  view().onclick = onMemoryClick;
  view().onkeydown = (ev) => {
    if (ev.key !== "Enter") return;
    const id = (ev.target as HTMLElement).id;
    if (id === "fnew") byId("fadd")?.click();
    if (id === "fedit") byId("fsave")?.click();
  };
  if (!state.backendOn) {
    byId("mem")!.innerHTML = offlineNote();
    return;
  }
  byId("mem")!.innerHTML = `
    <div class="row-wrap">
      <section class="card" style="flex:1 1 380px" aria-label="Datos que recuerda"><h2>Lo que recuerda de ti</h2><div id="facts"><span class="dim">Cargando…</span></div>
        <div class="inline"><label for="fnew" class="sr">Nuevo dato</label><input id="fnew" class="input" placeholder="Ej: Le encanta Frieren"><button type="button" id="fadd" class="btn">Guardar</button></div>
        <span id="fmsg" class="msg"></span></section>
      <section class="card" style="flex:1.4 1 440px" aria-label="Conversaciones"><h2>Conversaciones</h2><div id="days" class="chips"></div><div id="convo" class="chat"></div></section>
    </div>`;
  void loadMemory();
}

async function loadMemory(): Promise<void> {
  const d = await link.request("memory");
  if (!d || !byId("facts")) return;
  facts = d.facts;
  editing = -1;
  paintFacts();
  byId("days")!.innerHTML = d.days.length
    ? d.days.slice(0, 14).map((day: string) => `<button type="button" class="chip" data-day="${esc(day)}" aria-pressed="false">${esc(new Date(`${day}T12:00:00`).toLocaleDateString("es", { weekday: "short", day: "numeric", month: "short" }))}</button>`).join("")
    : `<span class="dim">Todavía no hay conversaciones guardadas.</span>`;
  if (d.days.length) void showDay(d.days[0]);
}

function paintFacts(): void {
  byId("facts")!.innerHTML = facts.length
    ? facts.map((f, i) => i === editing
        ? `<div class="list-row inline"><label for="fedit" class="sr">Editar dato</label><input id="fedit" class="input" value="${esc(f)}"><button type="button" id="fsave" class="btn small">Guardar</button><button type="button" class="btn small ghost" data-cancel-edit="1">Cancelar</button></div>`
        : `<div class="list-row"><span style="flex:1;font-size:14px">${esc(f)}</span><button type="button" class="btn small ghost" data-edit="${i}">Editar</button><button type="button" class="btn small danger" data-forget="${i}">Borrar</button></div>`).join("")
    : `<span class="dim">Todavía no recuerda nada de ti. Dile «recuerda que…».</span>`;
}

async function showDay(day: string): Promise<void> {
  document.querySelectorAll<HTMLElement>("[data-day]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.day === day)));
  const d = await link.request("conversation", { day });
  const box = byId("convo");
  if (!d || !box) return;
  box.innerHTML = d.turns.length
    ? d.turns.map((t: any) => `<div class="bubble user"><small>${esc(t.at)}</small>${esc(t.user)}</div><div class="bubble miku">${esc(t.miku)}</div>`).join("")
    : `<span class="dim">Ese día no hablasteis.</span>`;
  box.scrollTop = box.scrollHeight;
}

async function onMemoryClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  const act = async (action: string, args: Record<string, unknown>) => {
    const res = await link.request(`do:${action}`, args);
    say("fmsg", res ? res.result : "Miku no respondió.", res?.ok ? "ok" : "bad");
    await loadMemory();
  };
  if (el.dataset.day) void showDay(el.dataset.day);
  else if (el.dataset.edit) {
    editing = Number(el.dataset.edit);
    paintFacts();
    (byId("fedit") as HTMLInputElement)?.focus();
  } else if (el.dataset.cancelEdit) {
    editing = -1;
    paintFacts();
  } else if (el.id === "fsave") {
    const value = (byId("fedit") as HTMLInputElement).value.trim();
    if (value) await act("fact_edit", { old: facts[editing], new: value });
  } else if (el.dataset.forget) await act("fact_delete", { text: facts[Number(el.dataset.forget)] });
  else if (el.id === "fadd") {
    const input = byId("fnew") as HTMLInputElement;
    if (input.value.trim()) await act("fact_add", { text: input.value.trim() });
  }
}
