/**
 * Panel pages that change things: Configuración, Herramientas, Funciones, Recordatorios, Memoria.
 * Settings and tools go through Rust (a short Python process: they work with Miku off); reminders, notes and
 * memory through the backend, with the same tools Miku uses.
 */

import { invoke } from "@tauri-apps/api/core";
import { emit } from "@tauri-apps/api/event";
import { availableMonitors, primaryMonitor } from "@tauri-apps/api/window";
import {
  X_ICON, actions, loading, byId, clampPage, comma, dayLabel, esc, head, icon, isTauri, link, noAnswer, offlineNote, pageItems, pager,
  paint, state, toast, undoable,
} from "./shared";

const CHECK_ICON = "M5 12.5l4.5 4.5L19 7.5";
const view = () => byId("view")!;

function say(id: string, text: string, kind: "" | "ok" | "bad" | "warn" = ""): void {
  const el = byId(id);
  if (el) {
    el.textContent = text;
    el.className = `msg${kind ? ` ${kind}` : ""}`;
  }
}

const switchBtn = (id: string, label: string, on: boolean) =>
  `<button type="button" class="switch" role="switch" id="${id}" aria-checked="${on}" aria-label="${esc(label)}" style="justify-self:end"><span></span></button>`;
const setRow = (label: string, help: string, control: string, forId = "") =>
  `<div class="set${control.includes('role="switch"') ? " sw" : ""}"><div>${forId ? `<label for="${forId}"><b>${esc(label)}</b></label>` : `<b>${esc(label)}</b>`}<span>${help}</span></div><div>${control}</div></div>`;

const saveBar = (id: string, label: string) =>
  `<div class="savebar"><span id="${id}-msg" class="msg" aria-live="polite"></span>
   <button type="button" id="${id}-undo" class="btn ghost" hidden>Descartar</button>
   <button type="button" id="${id}-save" class="btn primary">${icon(CHECK_ICON, 16)}${esc(label)}</button></div>`;

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
let mics: string[] = [];
let autostart = false;
let wakeScores: { yes: number[]; no: number[] } = { yes: [], no: [] };
let capturing = false;
const HOTKEY_RE = /^((ctrl|alt|shift|super)\+){1,3}([a-z0-9]|f([1-9]|1[0-9]|2[0-4])|space)$/i;
const EDITED = ["rvc_enabled", "wakeword_enabled", "threshold", "weather_city", "hotkey", "input_device", "monitor", "window_chat"];
let screens: string[] = []; // "Pantalla 1 · izquierda · 1920×1080 (la principal)", left to right

export function renderConfig(): void {
  view().innerHTML = `${head("Configuración", "Se guardan en config.yaml y .env. Las claves nunca salen de tu PC.")}<div id="cfg" class="stack">${loading("Leyendo tus ajustes…")}</div>`;
  if (!isTauri) {
    byId("cfg")!.innerHTML = `<div class="offline">Los ajustes solo se cambian desde la app.</div>`;
    return;
  }
  Promise.all([
    invoke<string>("settings_get"),
    invoke<string>("settings_inputs").catch(() => "[]"),
    invoke<boolean>("autostart_get").catch(() => false),
    invoke<{ clips: { folder: string; name: string; label: string | null }[] }>("wake_clips").catch(() => ({ clips: [] })),
    Promise.all([availableMonitors(), primaryMonitor()]).catch(() => [[], null] as const),
  ])
    .then(([text, inputs, auto, wake, [all, main]]) => {
      // The same order Miku's window uses: left to right
      const sorted = [...all].sort((a, b) => a.position.x - b.position.x || a.position.y - b.position.y);
      screens = sorted.map((m, i) => `Pantalla ${i + 1}${sorted.length > 1 ? ` · ${i === 0 ? "izquierda" : i === sorted.length - 1 ? "derecha" : "centro"}` : ""} · ${m.size.width}×${m.size.height}${main && m.name === main.name ? " (la principal)" : ""}`);
      cfg = JSON.parse(text);
      mics = JSON.parse(inputs);
      autostart = auto;
      // A clip's name holds the score it had: the threshold slider says how many of the user's marked clips it lets through
      const score = (n: string) => Number(n.slice(16, 21));
      const marked = wake.clips.filter((c) => c.folder !== "silent" && c.label);
      wakeScores = { yes: marked.filter((c) => c.label === "yes").map((c) => score(c.name)), no: marked.filter((c) => c.label === "no").map((c) => score(c.name)) };
      draft = { ...cfg, gemini: { ...cfg.gemini }, vocabulary: [...cfg.vocabulary] };
      paintConfig();
    })
    .catch((err) => (byId("cfg")!.innerHTML = `<div class="offline">No pude leer los ajustes: ${esc(err)}</div>`));
}

function changes(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (!cfg || !draft) return out;
  if (draft.gemini.model !== cfg.gemini.model) out.model = draft.gemini.model;
  for (const k of EDITED) if (draft[k] !== cfg[k]) out[k] = draft[k];
  if (draft.vocabulary.join("|") !== cfg.vocabulary.join("|")) out.vocabulary = draft.vocabulary;
  const key = (byId("apikey") as HTMLInputElement | null)?.value.trim();
  const obs = (byId("obspw") as HTMLInputElement | null)?.value.trim();
  if (key) out.api_key = key;
  if (obs) out.obs_password = obs;
  return out;
}

function markDirty(): void {
  const dirty = Object.keys(changes()).length > 0;
  byId("cfg-undo")!.hidden = !dirty;
  say("cfg-msg", dirty ? "Cambios sin guardar" : "", dirty ? "warn" : "");
}

function thresholdEffect(t: number): string {
  const { yes, no } = wakeScores;
  if (!yes.length && !no.length) return "Más bajo: te oye mejor, pero se activa sola más a menudo. Marca clips en «Palabra clave» para ver aquí cómo afecta a tus llamadas.";
  const pass = (list: number[]) => list.filter((s) => s >= t).length;
  return `Con ${comma(t, 2)}: ${yes.length ? `${pass(yes)} de tus ${yes.length} llamadas marcadas la activan` : "aún no marcaste llamadas tuyas"}${no.length ? ` · ${pass(no)} de ${no.length} falsas también` : ""}.`;
}

function paintConfig(): void {
  const d = draft;
  byId("cfg")!.innerHTML = `
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(380px,1fr))">
    <section class="card" aria-label="Gemini"><h2>Gemini</h2>
      ${setRow("API key", cfg.gemini.has_key ? `Guardada (termina en …${esc(cfg.gemini.hint)}). Déjala vacía para no cambiarla.` : "De Google AI Studio.", `
        <div class="inline"><input id="apikey" class="input mono" type="password" autocomplete="off" spellcheck="false" placeholder="${cfg.gemini.has_key ? "Pega otra para cambiarla…" : "Pega tu API key…"}"><button type="button" id="testkey" class="btn">Probar</button></div>
        <span id="keymsg" class="msg" aria-live="polite"></span>`, "apikey")}
      ${setRow("Modelo principal", "Los de respaldo se usan solos si este falla.", `<select id="model" class="select">${cfg.gemini.models.map((m: string) => `<option${m === d.gemini.model ? " selected" : ""}>${esc(m)}</option>`).join("")}</select>`, "model")}
    </section>
    <section class="card" aria-label="Voz y palabra clave"><h2>Voz y palabra clave</h2>
      ${setRow("Voz de Miku (RVC)", "Usa la GPU. Apagada: solo subtítulos.", switchBtn("sw-rvc", "Voz de Miku (RVC)", d.rvc_enabled))}
      ${setRow("Escuchar «Hey Miku»", "Apagada: solo con el atajo.", switchBtn("sw-wake", "Escuchar «Hey Miku»", d.wakeword_enabled))}
      ${setRow("Umbral de la palabra clave", `<span id="thrfx">${esc(thresholdEffect(d.threshold))}</span>`, `
        <div class="inline"><input id="thr" class="range" type="range" min="0.2" max="0.8" step="0.05" value="${d.threshold}" aria-describedby="thrfx"><span id="thrv" class="mono" style="color:var(--teal-l);width:40px;text-align:right">${comma(d.threshold, 2)}</span></div>`, "thr")}
    </section>
    <section class="card" aria-label="Arranque, atajo y micrófono"><h2>Arranque, atajo y micrófono</h2>
      ${setRow("Arrancar con Windows", "Solo el icono de la bandeja, sin abrir el panel. Se aplica al momento.", switchBtn("sw-auto", "Arrancar con Windows", autostart))}
      ${setRow("Atajo para llamarla", "Haz clic y pulsa la combinación: Ctrl, Alt o Shift y una letra, número o F1-F24.", `<input id="hotkey" class="input mono hotkey" readonly value="${esc(d.hotkey)}" aria-label="Atajo: haz clic y pulsa la combinación">`, "hotkey")}
      ${setRow("Micrófono", "El que usan «Hey Miku» y la grabación de tu frase.", `<select id="mic" class="select"><option value="">El predeterminado de Windows</option>${mics.map((m) => `<option${m === d.input_device ? " selected" : ""}>${esc(m)}</option>`).join("")}
          ${d.input_device && !mics.includes(d.input_device) ? `<option selected>${esc(d.input_device)} (no conectado)</option>` : ""}</select>`, "mic")}
    </section>
    <section class="card" aria-label="La ventana de Miku"><h2>La ventana de Miku</h2>
      ${setRow("Pantalla", "Dónde aparece Miku. Se aplica al guardar.", `<select id="monitor" class="select"><option value="0">La principal de Windows</option>${screens.map((s, i) => `<option value="${i + 1}"${d.monitor === i + 1 ? " selected" : ""}>${esc(s)}</option>`).join("")}
          ${d.monitor > screens.length ? `<option value="${d.monitor}" selected>Pantalla ${d.monitor} (no conectada)</option>` : ""}</select>`, "monitor")}
      ${setRow("Escribirle desde su ventana", "Un cuadro de texto bajo Miku: lo que escribes le llega como si se lo dijeras.", switchBtn("sw-chat", "Escribirle desde su ventana", d.window_chat))}
    </section>
    <section class="card" aria-label="Clima y OBS"><h2>Clima y OBS</h2>
      ${setRow("Ciudad del clima", "Ciudad, País. Para otra ciudad, pregúntale con su nombre.", `<input id="city" class="input" autocomplete="off" value="${esc(d.weather_city)}">`, "city")}
      ${setRow("Contraseña de OBS", "OBS › Herramientas › Ajustes del servidor WebSocket.", `
        <div class="inline"><input id="obspw" class="input mono" type="password" autocomplete="off" spellcheck="false" placeholder="${cfg.obs.has_password ? "Guardada. Vacía: no se cambia" : "Pega la contraseña…"}"><button type="button" id="testobs" class="btn">Probar</button></div>
        <span id="obsmsg" class="msg" aria-live="polite"></span>`, "obspw")}
    </section>
    </div>
    <section class="card" aria-label="Palabras que Whisper debe conocer"><h2>Palabras que Whisper debe conocer</h2>
      <span class="dim">Nombres y canciones que dices a menudo. Solo palabras, nunca órdenes enteras.</span>
      <div id="words" class="chips"></div>
    </section>
    ${saveBar("cfg", state.backendOn ? "Guardar y reiniciar Miku" : "Guardar")}`;
  paintWords();
  actions.leaveGuard = () => Object.keys(changes()).length > 0;
  view().onclick = onConfigClick;
  const onEdit = (ev: Event) => {
    const el = ev.target as HTMLInputElement;
    if (el.id === "thr") {
      draft.threshold = Number(el.value);
      byId("thrv")!.textContent = comma(draft.threshold, 2);
      byId("thrfx")!.textContent = thresholdEffect(draft.threshold);
    } else if (el.id === "city") draft.weather_city = el.value;
    else if (el.id === "mic") draft.input_device = el.value.replace(/ \(no conectado\)$/, "");
    else if (el.id === "monitor") draft.monitor = Number(el.value);
    else if (el.id === "model") draft.gemini = { ...draft.gemini, model: el.value };
    markDirty();
  };
  view().oninput = onEdit;
  view().onchange = onEdit; // the select fires change, not input
  view().onkeydown = onConfigKey;
  byId("hotkey")!.onblur = stopCapture;
}

/** The hotkey is recorded, not typed: the keys pressed while the field is capturing. */
function onConfigKey(ev: KeyboardEvent): void {
  const el = ev.target as HTMLInputElement;
  if (el.id === "newword" && ev.key === "Enter" && el.value.trim()) {
    draft.vocabulary.push(el.value.trim());
    paintWords();
    byId("newword")?.focus();
    markDirty();
    return;
  }
  if (el.id !== "hotkey" || !capturing || ev.key === "Tab") return;
  ev.preventDefault();
  if (ev.key === "Escape") return stopCapture();
  const key = /^Key[A-Z]$/.test(ev.code) ? ev.code.slice(3) : /^Digit\d$/.test(ev.code) ? ev.code.slice(5) : /^F\d{1,2}$/.test(ev.code) ? ev.code : ev.code === "Space" ? "Space" : "";
  if (!key) return; // a modifier alone: wait for the rest
  const combo = [ev.ctrlKey && "Ctrl", ev.altKey && "Alt", ev.shiftKey && "Shift", ev.metaKey && "Super", key].filter(Boolean).join("+");
  if (!HOTKEY_RE.test(combo)) {
    el.value = `${combo}: falta Ctrl, Alt o Shift`;
    return;
  }
  draft.hotkey = combo;
  stopCapture();
  markDirty();
}

function startCapture(): void {
  const el = byId("hotkey") as HTMLInputElement;
  capturing = true;
  el.classList.add("capturing");
  el.value = "Pulsa la combinación… (Esc: cancelar)";
}

function stopCapture(): void {
  const el = byId("hotkey") as HTMLInputElement | null;
  capturing = false;
  if (!el) return;
  el.classList.remove("capturing");
  el.value = draft.hotkey;
}

function paintWords(): void {
  byId("words")!.innerHTML =
    draft.vocabulary.map((w: string, i: number) => `<span class="word">${esc(w)}<button type="button" data-word="${i}" aria-label="Quitar ${esc(w)}">${icon(X_ICON, 10)}</button></span>`).join("") +
    `<label for="newword" class="sr">Añadir palabra</label><input id="newword" class="input" style="width:150px;min-height:32px;border-radius:999px;border-style:dashed" placeholder="Añadir…" autocomplete="off">`;
}

async function onConfigClick(ev: MouseEvent): Promise<void> {
  const target = ev.target as HTMLElement;
  if (target.id === "hotkey") return startCapture();
  const el = target.closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.word !== undefined) {
    draft.vocabulary.splice(Number(el.dataset.word), 1);
    paintWords();
    markDirty();
  } else if (el.id === "sw-auto") {
    try {
      autostart = await invoke<boolean>("autostart_set", { enabled: !autostart });
      el.setAttribute("aria-checked", String(autostart));
      toast(autostart ? "Miku arrancará con Windows." : "Miku ya no arranca con Windows.");
    } catch (err) {
      toast(String(err));
    }
  } else if (el.id === "sw-rvc" || el.id === "sw-wake" || el.id === "sw-chat") {
    const key = el.id === "sw-rvc" ? "rvc_enabled" : el.id === "sw-wake" ? "wakeword_enabled" : "window_chat";
    draft[key] = !draft[key];
    el.setAttribute("aria-checked", String(draft[key]));
    markDirty();
  } else if (el.id === "testkey") {
    say("keymsg", "Probando…");
    try {
      const res = JSON.parse(await invoke<string>("settings_testkey", { key: (byId("apikey") as HTMLInputElement).value }));
      say("keymsg", res.ok ? "La API key funciona." : res.error, res.ok ? "ok" : "bad");
    } catch (err) {
      say("keymsg", String(err), "bad");
    }
  } else if (el.id === "testobs") {
    say("obsmsg", "Probando… (OBS tiene que estar abierto)");
    try {
      const res = JSON.parse(await invoke<string>("settings_testobs", { password: (byId("obspw") as HTMLInputElement).value }));
      say("obsmsg", res.ok ? `OBS responde${res.version ? ` (versión ${res.version})` : ""}.` : res.error, res.ok ? "ok" : "bad");
    } catch (err) {
      say("obsmsg", String(err), "bad");
    }
  } else if (el.id === "cfg-undo") {
    draft = { ...cfg, gemini: { ...cfg.gemini }, vocabulary: [...cfg.vocabulary] };
    paintConfig();
  } else if (el.id === "cfg-save") {
    const ch = changes();
    if (ch.hotkey !== undefined && !HOTKEY_RE.test(String(ch.hotkey))) {
      say("cfg-msg", "Atajo no válido: por ejemplo Ctrl+Alt+M.", "bad");
      return;
    }
    if (!Object.keys(ch).length) {
      say("cfg-msg", "No hay cambios.");
      return;
    }
    if (await saveSettings(ch, "cfg-msg", el as HTMLButtonElement)) {
      if (ch.monitor !== undefined || ch.window_chat !== undefined)
        await emit("window-settings-changed", { monitor: draft.monitor, chat: draft.window_chat }); // Miku's window moves now
      if (ch.hotkey) {
        await emit("hotkey-changed", ch.hotkey); // Miku's window takes the new one now
        state.hotkey = String(ch.hotkey);
      }
      cfg = JSON.parse(await invoke<string>("settings_get"));
      draft = { ...cfg, gemini: { ...cfg.gemini }, vocabulary: [...cfg.vocabulary] };
      (byId("apikey") as HTMLInputElement).value = "";
      (byId("obspw") as HTMLInputElement).value = "";
      byId("cfg-undo")!.hidden = true;
    }
  }
}

// ---------- Herramientas: grouped by topic, in plain words; the technical name stays small ----------
const GROUPS = ["Apps y ventanas", "Música y video", "Opera y web", "PC y sonido", "Archivos", "Recordatorios y notas", "Memoria", "OBS, clima y más", "Otras"];
const TOOL_INFO: Record<string, [number, string, string]> = {
  open_app: [0, "Abrir una app", "Abre un programa instalado por su nombre."],
  close_app: [0, "Cerrar una app", "Cierra un programa abierto por su nombre."],
  list_open_apps: [0, "Apps abiertas", "Dice qué programas tienes abiertos."],
  windows: [0, "Ventanas", "Activa, minimiza, maximiza, mueve o cierra ventanas."],
  show_desktop: [0, "Mostrar el escritorio", "Minimiza todas las ventanas, como Win+D. No cierra nada."],
  type_text: [0, "Escribir por ti", "Escribe un texto en la ventana activa."],
  media_control: [1, "Pausa, play y siguiente", "Controla la música o el video que suena en Windows."],
  youtube_play: [1, "Poner en YouTube", "Busca y reproduce una canción o un video."],
  youtube_player: [1, "Reproductor de YouTube", "Volumen, calidad, subtítulos, velocidad y siguiente video."],
  youtube_search: [1, "Buscar en YouTube", "Abre los resultados de una búsqueda, sin reproducir."],
  browser_tabs: [2, "Pestañas de Opera", "Cierra, cambia, recarga o vuelve atrás en tus pestañas."],
  open_url: [2, "Abrir una web", "Abre una dirección en Opera."],
  open_website: [2, "Abrir la web de algo", "Encuentra y abre la web de algo por su nombre."],
  web_search: [2, "Buscar en Google", "Abre una búsqueda de Google."],
  change_volume: [3, "Subir o bajar el volumen", "Cambia el volumen de Windows un poco."],
  set_volume: [3, "Volumen exacto", "Pone el volumen de Windows en un número de 0 a 100."],
  mute: [3, "Silenciar", "Silencia o vuelve a activar el sonido."],
  lock_pc: [3, "Bloquear el PC", "Pone la pantalla de bloqueo de Windows."],
  shutdown_pc: [3, "Apagar o reiniciar", "Apaga, reinicia o suspende el PC. Siempre pregunta antes."],
  get_system_status: [3, "Estado del PC", "Dice el uso de CPU, memoria y disco."],
  copy_to_clipboard: [3, "Copiar al portapapeles", "Deja un texto listo para pegar con Ctrl+V."],
  read_clipboard: [3, "Leer el portapapeles", "Lee en voz alta lo último que copiaste."],
  find_file: [4, "Buscar un archivo", "Busca por nombre en Escritorio, Documentos y Descargas."],
  open_file: [4, "Abrir un archivo", "Abre un archivo que encontró antes."],
  open_folder: [4, "Abrir una carpeta", "Abre Escritorio, Descargas o Documentos en el Explorador."],
  create_text_file: [4, "Crear un archivo de texto", "Crea un .txt nuevo en el Escritorio. Nunca sobrescribe."],
  read_text_file: [4, "Leer un archivo", "Lee en voz alta un .txt, .md o .csv."],
  remind: [5, "Recordatorio", "Te avisa más tarde: en unos minutos o a una hora."],
  set_timer: [5, "Temporizador", "Una cuenta atrás en minutos."],
  list_timers: [5, "Ver avisos", "Dice tus temporizadores y recordatorios activos."],
  cancel_timer: [5, "Cancelar un aviso", "Quita un temporizador o recordatorio."],
  my_day: [5, "Tu día", "Resume tus recordatorios de hoy y tus pendientes."],
  take_note: [5, "Apuntar un pendiente", "Añade un pendiente a tu lista."],
  read_notes: [5, "Leer pendientes", "Lee los pendientes que aún no has hecho."],
  complete_note: [5, "Marcar como hecho", "Tacha un pendiente cuando le dices que ya lo hiciste."],
  delete_note: [5, "Borrar una nota", "Quita una nota o pendiente de tu lista."],
  open_notes: [5, "Abrir tus notas", "Abre notes.md en el Bloc de notas."],
  watch_downloads: [5, "Avisar de descargas", "Avisa cuando terminen las descargas en curso."],
  remember: [6, "Recordar un dato", "Guarda algo de ti para usarlo en las respuestas."],
  forget: [6, "Olvidar un dato", "Borra de su memoria lo que le pidas olvidar."],
  recall_conversation: [6, "Recordar conversaciones", "Busca de qué hablaron otros días."],
  obs: [7, "OBS", "Guarda un clip, graba o cambia de escena. Nunca inicia directos."],
  weather: [7, "Clima", "El tiempo de hoy o de mañana."],
  quota_status: [7, "Cuota de Gemini", "Dice cuántas peticiones lleva hoy y cuántas quedan."],
  get_datetime: [7, "Fecha y hora", "Dice la hora y la fecha."],
  run_routine: [7, "Rutinas", "Hace varias cosas seguidas con una sola orden, como «trabajo»."],
};
const TOOL_FILTERS: [string, string, (t: any) => boolean][] = [
  ["all", "Todas", () => true],
  ["local", "Locales", (t) => t.local],
  ["confirm", "Piden confirmación", (t) => t.destructive],
  ["off", "Apagadas", (t) => disabled.has(t.name)],
];
let tools: any[] = [];
let disabled = new Set<string>();
let savedDisabled = "";
let toolQuery = "";
let toolFilter = "all";
const openGroups = new Set<number>(); // closed by default: the page shows the topics, not 46 rows
let toggleBound = false;

const toolInfo = (t: any): [number, string, string] => TOOL_INFO[t.name] ?? [GROUPS.length - 1, t.name, t.description];

export function renderTools(): void {
  view().innerHTML = `${head("Herramientas", "Lo que Miku puede hacer en tu PC. Una herramienta apagada desaparece para Gemini y para las frases locales.")}
    <div class="toolbar"><div class="chips" role="group" aria-label="Filtrar" id="tfilters"></div>
      <div><label for="tq" class="sr">Buscar herramienta</label><input id="tq" class="search" type="search" placeholder="Buscar…" value="${esc(toolQuery)}"></div></div>
    <section class="card" aria-label="Herramientas" style="padding-top:8px;padding-bottom:8px"><div id="tlist">${loading("Leyendo las herramientas…")}</div></section>
    ${saveBar("tools", state.backendOn ? "Guardar y reiniciar Miku" : "Guardar")}`;
  view().onclick = onToolsClick;
  view().oninput = (ev) => {
    const el = ev.target as HTMLInputElement;
    if (el.id === "tq") {
      toolQuery = el.value;
      paintTools();
    }
  };
  actions.leaveGuard = () => [...disabled].sort().join("|") !== savedDisabled;
  if (!toggleBound) {
    toggleBound = true; // "toggle" does not bubble: one capturing listener on the page, for good
    view().addEventListener("toggle", (ev) => {
      const g = ev.target as HTMLDetailsElement;
      if (g.dataset?.group === undefined) return;
      if (g.open) openGroups.add(Number(g.dataset.group));
      else openGroups.delete(Number(g.dataset.group));
    }, true);
  }
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
  byId("tfilters")!.innerHTML = TOOL_FILTERS.map(([id, label, keep]) => `<button type="button" class="chip" data-tf="${id}" aria-pressed="${id === toolFilter}">${label}<span class="n">${tools.filter(keep).length}</span></button>`).join("");
  const q = toolQuery.toLowerCase();
  const keep = TOOL_FILTERS.find(([id]) => id === toolFilter)![2];
  const shown = tools.filter((t) => keep(t) && (!q || `${t.name} ${toolInfo(t)[1]} ${toolInfo(t)[2]}`.toLowerCase().includes(q)));
  const html = GROUPS.map((name, gi) => {
    const list = shown.filter((t) => toolInfo(t)[0] === gi).sort((a, b) => toolInfo(a)[1].localeCompare(toolInfo(b)[1]));
    if (!list.length) return "";
    const off = list.filter((t) => disabled.has(t.name)).length;
    return `<details class="group" data-group="${gi}"${openGroups.has(gi) || q || toolFilter !== "all" ? " open" : ""}><summary>${esc(name)} <span class="dim">${list.length}${off ? ` · ${off} apagada${off > 1 ? "s" : ""}` : ""}</span></summary>
      ${list.map((t) => {
        const [, title, summary] = toolInfo(t);
        return `<div class="tool"><div class="tool-name">${esc(title)}${t.local ? `<span class="pill ok" data-tip="Con su frase corta lo hace en tu PC, sin gastar cuota">LOCAL</span>` : ""}${t.destructive ? `<span class="pill warn">PIDE CONFIRMACIÓN</span>` : ""}<code>${esc(t.name)}</code></div>
          <p>${esc(summary)}</p>
          <button type="button" class="switch" role="switch" data-tool="${esc(t.name)}" aria-checked="${!disabled.has(t.name)}" aria-label="${esc(title)}"><span></span></button></div>`;
      }).join("")}</details>`;
  }).join("");
  byId("tlist")!.innerHTML = html || `<span class="dim" style="display:block;padding:12px 0">Ninguna herramienta coincide.</span>`;
  const changed = [...disabled].sort().join("|") !== savedDisabled;
  byId("tools-undo")!.hidden = !changed;
  say("tools-msg", changed ? `Cambios sin guardar · ${disabled.size} apagada(s)` : `${tools.length - disabled.size} de ${tools.length} encendidas`, changed ? "warn" : "");
}

async function onToolsClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.tool) {
    const name = el.dataset.tool;
    if (disabled.has(name)) disabled.delete(name);
    else disabled.add(name);
    paintTools();
  } else if (el.dataset.tf) {
    toolFilter = el.dataset.tf;
    paintTools();
  } else if (el.id === "tools-undo") {
    disabled = new Set(savedDisabled ? savedDisabled.split("|") : []);
    paintTools();
  } else if (el.id === "tools-save") {
    if ([...disabled].sort().join("|") === savedDisabled) {
      say("tools-msg", "No hay cambios.");
      return;
    }
    if (await saveSettings({ disabled_tools: [...disabled].sort() }, "tools-msg", el as HTMLButtonElement)) {
      savedDisabled = [...disabled].sort().join("|");
      byId("tools-undo")!.hidden = true;
    }
  }
}

// ---------- Funciones (docs/funciones.md): an index, one section at a time, phrases you can try ----------
interface DocSection { title: string; level: number; html: string; gem: boolean }
let sections: DocSection[] = [];
let activeSection = 0;

/** The small markdown funciones.md uses: headings, tables, lists, paragraphs, bold, code. Quoted phrases in tables
 *  become buttons that put the phrase in the "Probar con Miku" box. Everything is escaped first. */
function markdown(src: string, gem: boolean): string {
  const fmt = (t: string) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  // In a cell, ** around a phrase would split from it: the first column is bold by style anyway
  const cell = (t: string) =>
    t.replace(/\*\*/g, "").split(/("[^"]+")/).map((part) => (/^"[^"]+"$/.test(part)
      ? `<button type="button" class="phrase${gem ? " gem" : ""}" data-say="${esc(part.slice(1, -1))}" data-tip="${gem ? "Gasta 1 petición de Gemini" : "Local: sin gastar cuota"} · pulsa para probarla">${esc(part.slice(1, -1))}</button>`
      : fmt(part))).join("");
  const lines = src.split(/\r?\n/);
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^#\s/.test(l) || !l.trim()) continue;
    if (/^###\s/.test(l)) out.push(`<h3 id="h-${esc(l.slice(4)).replace(/\W+/g, "-")}">${fmt(l.slice(4))}</h3>`);
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
      if (!para.join(" ").includes("tools.md")) out.push(`<p>${fmt(para.join(" "))}</p>`); // a link the panel cannot open
    }
  }
  return out.join("\n");
}

/** funciones.md split at its "## " headings; the text before the first one goes with the first section. */
function splitDoc(text: string): DocSection[] {
  const parts = text.split(/\r?\n(?=## )/);
  const intro = parts[0].startsWith("## ") ? "" : parts.shift()!;
  return parts.map((p, i) => {
    const title = p.slice(3, p.indexOf("\n") > 0 ? p.indexOf("\n") : undefined).trim();
    const gem = /gemini/i.test(title);
    return { title, level: 2, gem, html: markdown((i === 0 ? `${intro}\n` : "") + p.slice(p.indexOf("\n") + 1), gem) };
  });
}

export function renderFunctions(): void {
  view().innerHTML = `${head("Funciones", "Qué puedes pedirle y cómo. Pulsa una frase para probarla: nada se envía hasta que pulses «Enviar».")}
    <div class="try"><div class="card" style="padding:12px 14px;gap:8px">
      <div class="inline"><label for="try-in" class="sr">Frase para Miku</label><input id="try-in" class="input" autocomplete="off" placeholder="Pulsa una frase de abajo o escribe una…">
        <button type="button" id="try-send" class="btn">Enviar a Miku</button></div>
      <div class="toolbar"><div class="legend"><span><i class="swatch" style="background:var(--teal)"></i>Local: sin gastar cuota</span><span><i class="swatch" style="background:var(--blue)"></i>Gasta 1 petición de Gemini</span></div>
        <span id="fmsg" class="msg" aria-live="polite">${state.backendOn ? "" : "Enciende a Miku para probar frases."}</span></div>
    </div></div>
    <div class="docs"><nav class="toc" id="toc" aria-label="Secciones"></nav>
      <div class="stack"><div><label for="fq" class="sr">Buscar</label><input id="fq" class="search" type="search" style="width:100%" placeholder="Buscar en todas las secciones: clima, OBS, volumen…"></div>
        <section class="card md" id="doc">${loading("Leyendo funciones.md…")}</section></div></div>`;
  view().onclick = (ev) => {
    const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
    if (!el) return;
    if (el.dataset.say) {
      const input = byId("try-in") as HTMLInputElement;
      input.value = el.dataset.say;
      input.focus();
      say("fmsg", el.classList.contains("gem") ? "Esta frase gasta 1 petición de Gemini." : "Esta frase es local: no gasta cuota.");
    } else if (el.id === "try-send") sendTry();
    else if (el.dataset.sec !== undefined) {
      activeSection = Number(el.dataset.sec);
      (byId("fq") as HTMLInputElement).value = "";
      paintDoc("");
      if (el.dataset.h) byId(el.dataset.h)?.scrollIntoView({ block: "start" });
      else view().scrollTop = 0;
    }
  };
  view().onkeydown = (ev) => {
    if (ev.key === "Enter" && (ev.target as HTMLElement).id === "try-in") sendTry();
  };
  view().oninput = (ev) => {
    const el = ev.target as HTMLInputElement;
    if (el.id === "fq") paintDoc(el.value.trim().toLowerCase());
  };
  if (sections.length) paintDoc("");
  else if (isTauri)
    invoke<string>("read_functions_doc")
      .then((text) => {
        sections = splitDoc(text);
        paintDoc("");
      })
      .catch((err) => (byId("doc")!.innerHTML = `<span class="msg bad">No pude leer docs/funciones.md: ${esc(err)}</span>`));
}

function sendTry(): void {
  const text = (byId("try-in") as HTMLInputElement).value.trim();
  if (!text) return;
  if (!state.backendOn || !link.send({ type: "text_input", text })) {
    say("fmsg", "Enciende a Miku para probar frases.", "bad");
    return;
  }
  say("fmsg", `Enviado: «${text}». Miku te contesta con su voz.`, "ok");
}

/** One section, or (when searching) every match in every section, with where it comes from. */
function paintDoc(q: string): void {
  const toc = byId("toc");
  const doc = byId("doc");
  if (!toc || !doc || !sections.length) return;
  toc.innerHTML = sections.map((s, i) => {
    const subs = [...s.html.matchAll(/<h3 id="([^"]+)">(.*?)<\/h3>/g)];
    return `<button type="button" data-sec="${i}" aria-current="${!q && i === activeSection}">${esc(s.title)}</button>` +
      (i === activeSection ? subs.map((m) => `<button type="button" class="sub" data-sec="${i}" data-h="${m[1]}">${m[2]}</button>`).join("") : "");
  }).join("");
  if (!q) {
    doc.innerHTML = `<h2>${esc(sections[activeSection].title)}</h2>${sections[activeSection].html}`;
    return;
  }
  doc.innerHTML = sections.map((s, i) => `<div data-part="${i}"><div class="from">${esc(s.title.toUpperCase())}</div>${s.html}</div>`).join("");
  let found = 0;
  doc.querySelectorAll<HTMLElement>("[data-part]").forEach((part) => {
    part.querySelectorAll<HTMLElement>("tbody tr, li, p").forEach((row) => {
      const hit = row.textContent!.toLowerCase().includes(q);
      row.style.display = hit ? "" : "none";
      if (hit) found++;
    });
    part.querySelectorAll<HTMLElement>("table, ul").forEach((block) => {
      const rows = [...block.querySelectorAll<HTMLElement>("tbody tr, li")];
      block.style.display = rows.some((r) => r.style.display !== "none") ? "" : "none";
    });
    part.querySelectorAll<HTMLElement>("h3").forEach((h) => {
      let next = h.nextElementSibling as HTMLElement | null;
      let visible = false;
      while (next && next.tagName !== "H3") {
        if (next.style.display !== "none") visible = true;
        next = next.nextElementSibling as HTMLElement | null;
      }
      h.style.display = visible ? "" : "none";
    });
    const any = [...part.querySelectorAll<HTMLElement>("tbody tr, li, p")].some((r) => r.style.display !== "none");
    part.style.display = any ? "" : "none";
  });
  if (!found) doc.innerHTML = `<span class="dim">Nada coincide con «${esc(q)}».</span>`;
}

// ---------- Recordatorios y pendientes ----------
const PER_LIST = 10;
let remData: any = null;
let remAsked = false;
let timerPage = 1;
let notePage = 1;
const hiddenTimers = new Set<number>();
const hiddenNotes = new Set<string>();

export function renderReminders(): void {
  view().innerHTML = `${head("Recordatorios", "Los mismos avisos y pendientes que creas hablando con Miku: aquí los ves, los creas y los quitas.")}<div id="rem" class="stack"></div>`;
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
  remAsked = false;
  byId("rem")!.innerHTML = `
    <div class="row-wrap">
      <section class="card" style="flex:2 1 440px" aria-label="Avisos activos"><h2>Avisos activos</h2><div id="tl">${loading("Leyendo tus avisos…")}</div></section>
      <section class="card" style="flex:1 1 300px" aria-label="Nuevo recordatorio"><h2>Nuevo recordatorio</h2>
        <div class="field"><label for="rtext">Qué te recuerdo</label><input id="rtext" class="input" autocomplete="off" placeholder="Ej: tomar agua…"></div>
        <div class="inline" style="align-items:flex-end">
          <div class="field" style="flex:1"><label for="rkind">Cuándo</label><select id="rkind" class="select"><option value="in">En unos minutos</option><option value="at">A una hora</option></select></div>
          <div class="field" id="rmin-f" style="width:110px"><label for="rmin">Minutos</label><input id="rmin" class="input" type="number" inputmode="numeric" min="1" max="10080" value="30"></div>
          <div class="field" id="rat-f" style="display:none;width:130px"><label for="rat">Hora</label><input id="rat" class="input" type="time" value="09:00"></div></div>
        <div class="field"><label for="revery">Repetir</label><select id="revery" class="select"><option value="0">No</option><option value="1440">Todos los días</option><option value="10080">Cada semana</option></select></div>
        <button type="button" id="radd" class="btn">Crear recordatorio</button><span id="rmsg" class="msg" aria-live="polite"></span>
      </section>
    </div>
    <section class="card" aria-label="Pendientes"><h2>Pendientes</h2>
      <div class="inline"><label for="pnew" class="sr">Nuevo pendiente</label><input id="pnew" class="input" autocomplete="off" placeholder="Apunta un pendiente…"><button type="button" id="padd" class="btn">Apuntar</button></div>
      <div id="pl"></div><span id="pmsg" class="msg" aria-live="polite"></span></section>`;
  if (remData) paintReminders();
}

export async function refreshReminders(): Promise<void> {
  if (!state.backendOn || !byId("tl")) return;
  const d = await link.request("timers");
  remAsked = true;
  if (d) remData = d;
  if (byId("tl")) paintReminders();
}

function paintReminders(): void {
  const tl = byId("tl");
  const pl = byId("pl");
  if (!tl || !pl) return;
  if (!remData) {
    paint(tl, remAsked ? noAnswer() : loading("Leyendo tus avisos…"));
    return;
  }
  const timers: any[] = remData.timers.filter((t: any) => !hiddenTimers.has(t.id));
  timerPage = clampPage(timerPage, timers.length, PER_LIST);
  paint(tl, timers.length
    ? pageItems(timers, timerPage, PER_LIST).map((t: any) => `<div class="list-row" style="min-height:52px"><span class="pill ${t.reminder ? "ok" : "off"}">${t.reminder ? "AVISO" : "TEMPORIZADOR"}</span>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px"><span style="font-size:14px">${esc(t.text)}</span><span class="dim">${esc(t.when)} · ${esc(t.at)}${t.repeats ? " · se repite" : ""}</span></div>
        <button type="button" class="btn small danger" data-cancel="${t.id}" data-text="${esc(t.text)}">Cancelar</button></div>`).join("") + pager("timers", timers.length, timerPage, PER_LIST, "avisos")
    : `<span class="dim">No hay avisos activos. Crea uno aquí o dile «recuérdame…».</span>`);
  const notes: string[] = remData.pending.filter((p: string) => !hiddenNotes.has(p));
  notePage = clampPage(notePage, notes.length, PER_LIST);
  paint(pl, notes.length
    ? pageItems(notes, notePage, PER_LIST).map((p: string) => `<div class="list-row"><span style="flex:1;font-size:14px">${esc(p)}</span>
        <button type="button" class="btn small" data-done="${esc(p)}" data-tip="Lo tacha en tus notas">Hecho</button><button type="button" class="btn small ghost" data-del="${esc(p)}" data-tip="Lo quita de tus notas">Borrar</button></div>`).join("") + pager("notes", notes.length, notePage, PER_LIST, "pendientes")
    : `<span class="dim">No tienes pendientes.</span>`);
}

async function doAndSay(action: string, args: Record<string, unknown>, msgId: string): Promise<void> {
  const res = await link.request(`do:${action}`, args);
  say(msgId, res ? res.result : "Miku no respondió.", res?.ok ? "ok" : "bad");
  await refreshReminders();
}

/** Hides an item now and does the action in 5 s, unless "Deshacer". */
function later<T>(set: Set<T>, key: T, text: string, action: string, args: Record<string, unknown>): void {
  set.add(key);
  paintReminders();
  undoable(text, async () => {
    await link.request(`do:${action}`, args);
    set.delete(key);
    await refreshReminders();
  }, () => {
    set.delete(key);
    paintReminders();
  });
}

async function onRemindersClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.pager) {
    if (el.dataset.pager === "timers") timerPage = Number(el.dataset.page);
    else notePage = Number(el.dataset.page);
    paintReminders();
  } else if (el.dataset.cancel) later(hiddenTimers, Number(el.dataset.cancel), `Aviso cancelado: ${el.dataset.text}`, "cancel_timer", { id: Number(el.dataset.cancel) });
  else if (el.dataset.done) later(hiddenNotes, el.dataset.done, "Pendiente marcado como hecho", "note_done", { text: el.dataset.done });
  else if (el.dataset.del) later(hiddenNotes, el.dataset.del, "Pendiente borrado", "note_delete", { text: el.dataset.del });
  else if (el.id === "padd") {
    const input = byId("pnew") as HTMLInputElement;
    if (!input.value.trim()) return;
    await doAndSay("note_add", { text: input.value.trim() }, "pmsg");
    input.value = "";
  } else if (el.id === "radd") {
    const text = (byId("rtext") as HTMLInputElement).value.trim();
    if (!text) {
      say("rmsg", "Escribe qué te recuerdo.", "bad");
      byId("rtext")!.focus();
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

// ---------- Memoria: what she remembers, and every day's conversation (with a search) ----------
const PER_FACTS = 20;
const PER_DAYS = 15;
let memTab: "facts" | "conv" = "facts";
let facts: string[] = [];
let days: string[] = [];
let memLoaded: "no" | "yes" | "failed" = "no";
let factPage = 1;
let dayPage = 1;
let memDay = "";
let memAt = "";
let editing = -1;
let memQuery = "";
let searchTimer = 0;
const hiddenFacts = new Set<string>();

/** Opens Memoria on a day's conversation (Inicio's "Hoy" list), at the turn said at `at`. */
export function openConversation(day: string, at = ""): void {
  memTab = "conv";
  memDay = day;
  memAt = at;
  memQuery = "";
}

export function renderMemory(): void {
  view().innerHTML = `${head("Memoria", "Lo que Miku sabe de ti, que usa en cada respuesta, y lo que hablaron cada día.")}
    <div class="chips" role="tablist" aria-label="Memoria">
      <button type="button" class="chip" role="tab" data-tab="facts" aria-pressed="${memTab === "facts"}" aria-selected="${memTab === "facts"}">Lo que recuerda<span class="n" id="n-facts"></span></button>
      <button type="button" class="chip" role="tab" data-tab="conv" aria-pressed="${memTab === "conv"}" aria-selected="${memTab === "conv"}">Conversaciones<span class="n" id="n-days"></span></button></div>
    <div id="mem" class="stack grow"></div>`;
  view().classList.toggle("fill", memTab === "conv");
  view().onclick = onMemoryClick;
  view().onkeydown = (ev) => {
    const id = (ev.target as HTMLElement).id;
    if (ev.key === "Enter" && id === "fnew") byId("fadd")?.click();
    if (ev.key === "Enter" && id === "fedit") byId("fsave")?.click();
    if (ev.key === "Escape" && id === "fedit") {
      editing = -1;
      paintFacts();
    }
  };
  view().oninput = (ev) => {
    const el = ev.target as HTMLInputElement;
    if (el.id !== "msearch") return;
    memQuery = el.value;
    clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void showSearch(), 300);
  };
  if (!state.backendOn) {
    byId("mem")!.innerHTML = offlineNote();
    return;
  }
  paintMemory();
  void loadMemory();
}

async function loadMemory(): Promise<void> {
  const d = await link.request("memory");
  if (!byId("mem")) return;
  if (!d) {
    memLoaded = memLoaded === "yes" ? "yes" : "failed";
  } else {
    facts = d.facts;
    days = d.days;
    memLoaded = "yes";
    if (!memDay || !days.includes(memDay)) memDay = days[0] ?? "";
  }
  paintMemory();
}

function paintMemory(): void {
  const box = byId("mem");
  if (!box) return;
  paint(byId("n-facts"), memLoaded === "yes" ? String(facts.length) : "");
  paint(byId("n-days"), memLoaded === "yes" ? String(days.length) : "");
  if (memLoaded === "failed") return void (box.innerHTML = noAnswer());
  if (memLoaded === "no") return void (box.innerHTML = loading("Leyendo lo que Miku recuerda…"));
  if (memTab === "facts") {
    box.innerHTML = `<section class="card" aria-label="Lo que recuerda de ti">
      <div class="inline"><label for="fnew" class="sr">Nuevo dato</label><input id="fnew" class="input" autocomplete="off" placeholder="Algo que Miku deba saber de ti. Ej: le encanta Frieren…"><button type="button" id="fadd" class="btn">Guardar</button></div>
      <span class="dim">Haz clic en un dato para corregirlo.</span>
      <div id="facts"></div><span id="fmsg" class="msg" aria-live="polite"></span></section>`;
    paintFacts();
  } else {
    box.innerHTML = `<div class="two grow">
      <section class="card" style="min-height:0" aria-label="Días">
        <div><label for="msearch" class="sr">Buscar en las conversaciones</label><input id="msearch" class="search" style="width:100%" type="search" placeholder="Buscar en todas…" value="${esc(memQuery)}"></div>
        <div id="days" class="days" style="flex:1"></div><div id="dpager"></div></section>
      <section class="card" style="min-height:0" aria-label="Conversación"><div class="card-head"><h2 id="convtitle"></h2><span id="convnote" class="dim"></span></div>
        <div id="convo" class="chat" style="flex:1"></div></section></div>`;
    paintDays();
    if (memQuery.trim().length >= 2) void showSearch();
    else if (memDay) void showDay(memDay);
    else byId("convo")!.innerHTML = `<span class="dim">Todavía no hay conversaciones guardadas.</span>`;
  }
}

function paintFacts(): void {
  const box = byId("facts");
  if (!box) return;
  const list = facts.filter((f) => !hiddenFacts.has(f));
  factPage = clampPage(factPage, list.length, PER_FACTS);
  box.innerHTML = list.length
    ? pageItems(list, factPage, PER_FACTS).map((f) => {
        const i = facts.indexOf(f);
        return i === editing
          ? `<div class="list-row inline"><label for="fedit" class="sr">Corregir dato</label><input id="fedit" class="input" value="${esc(f)}"><button type="button" id="fsave" class="btn small">Guardar</button><button type="button" class="btn small ghost" data-cancel-edit>Cancelar</button></div>`
          : `<div class="list-row"><button type="button" class="fact" data-edit="${i}" title="Corregir">${esc(f)}</button>
             <button type="button" class="btn small icon danger" data-forget="${i}" aria-label="Borrar: ${esc(f)}" data-tip="Borrar">${icon(X_ICON, 14)}</button></div>`;
      }).join("") + pager("facts", list.length, factPage, PER_FACTS, "datos")
    : `<span class="dim">Todavía no recuerda nada de ti. Escríbelo arriba o dile «recuerda que…».</span>`;
}

function paintDays(): void {
  const box = byId("days");
  if (!box) return;
  dayPage = clampPage(dayPage, days.length, PER_DAYS);
  let month = "";
  box.innerHTML = days.length
    ? pageItems(days, dayPage, PER_DAYS).map((day) => {
        const m = new Date(`${day}T12:00:00`).toLocaleDateString("es", { month: "long", year: "numeric" });
        const label = m !== month ? `<div class="month">${esc((month = m))}</div>` : "";
        return `${label}<button type="button" data-day="${day}" aria-current="${!memQuery && day === memDay}"><span>${esc(dayLabel(day))}</span><span class="dim">${esc(day.slice(8))}</span></button>`;
      }).join("")
    : `<span class="dim">Todavía no hay conversaciones guardadas.</span>`;
  byId("dpager")!.innerHTML = pager("days", days.length, dayPage, PER_DAYS, "días");
}

async function showDay(day: string): Promise<void> {
  memDay = day;
  const d = await link.request("conversation", { day });
  const box = byId("convo");
  if (!box) return;
  byId("convtitle")!.textContent = dayLabel(day, true).replace(/^./, (c) => c.toUpperCase());
  if (!d) return void (box.innerHTML = noAnswer());
  byId("convnote")!.textContent = d.turns.length ? `${d.turns.length} turnos` : "";
  box.innerHTML = d.turns.length
    ? d.turns.map((t: any) => `<div class="bubble user${t.at === memAt ? " hit" : ""}" data-at="${esc(t.at)}"><small>${esc(t.at)} · tú</small>${esc(t.user)}</div><div class="bubble miku"><small>Miku</small>${esc(t.miku)}</div>`).join("")
    : `<span class="dim">Ese día no hablaron.</span>`;
  const hit = memAt ? box.querySelector<HTMLElement>(`[data-at="${CSS.escape(memAt)}"]`) : null;
  if (hit) hit.scrollIntoView({ block: "center" });
  else box.scrollTop = box.scrollHeight;
  memAt = "";
}

async function showSearch(): Promise<void> {
  const box = byId("convo");
  if (!box) return;
  const q = memQuery.trim();
  paintDays();
  if (q.length < 2) {
    if (memDay) void showDay(memDay);
    return;
  }
  byId("convtitle")!.textContent = `Buscar «${q}»`;
  const d = await link.request("search", { q });
  if (memQuery.trim() !== q || !byId("convo")) return;
  if (!d) return void (box.innerHTML = noAnswer());
  byId("convnote")!.textContent = d.hits.length >= 40 ? "los 40 más recientes" : `${d.hits.length} resultados`;
  box.innerHTML = d.hits.length
    ? d.hits.map((h: any) => `<button type="button" class="turn list-row" data-hit="${h.day}" data-at="${esc(h.at)}" style="flex-direction:column;align-items:flex-start;gap:4px;padding:10px 4px">
        <span class="dim">${esc(dayLabel(h.day))} · ${esc(h.at)}</span><span style="font-size:14px">${esc(h.user)}</span><span class="muted" style="font-size:13px">${esc(h.miku)}</span></button>`).join("")
    : `<span class="dim">Nada coincide con «${esc(q)}».</span>`;
}

async function onMemoryClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  const act = async (action: string, args: Record<string, unknown>) => {
    const res = await link.request(`do:${action}`, args);
    say("fmsg", res ? res.result : "Miku no respondió.", res?.ok ? "ok" : "bad");
    await loadMemory();
  };
  if (el.dataset.tab) {
    memTab = el.dataset.tab as "facts" | "conv";
    renderMemory();
  } else if (el.dataset.pager === "facts") {
    factPage = Number(el.dataset.page);
    paintFacts();
  } else if (el.dataset.pager === "days") {
    dayPage = Number(el.dataset.page);
    paintDays();
  } else if (el.dataset.day) {
    memQuery = "";
    (byId("msearch") as HTMLInputElement).value = "";
    void showDay(el.dataset.day);
    paintDays();
  } else if (el.dataset.hit) {
    memQuery = "";
    memAt = el.dataset.at ?? "";
    (byId("msearch") as HTMLInputElement).value = "";
    dayPage = Math.floor(Math.max(0, days.indexOf(el.dataset.hit)) / PER_DAYS) + 1;
    void showDay(el.dataset.hit);
    paintDays();
  } else if (el.dataset.edit) {
    editing = Number(el.dataset.edit);
    paintFacts();
    (byId("fedit") as HTMLInputElement)?.focus();
  } else if (el.dataset.cancelEdit !== undefined) {
    editing = -1;
    paintFacts();
  } else if (el.id === "fsave") {
    const value = (byId("fedit") as HTMLInputElement).value.trim();
    if (value && value !== facts[editing]) await act("fact_edit", { old: facts[editing], new: value });
    editing = -1;
    paintFacts();
  } else if (el.dataset.forget) {
    const fact = facts[Number(el.dataset.forget)];
    hiddenFacts.add(fact);
    paintFacts();
    undoable("Dato borrado", async () => {
      await link.request("do:fact_delete", { text: fact });
      hiddenFacts.delete(fact);
      await loadMemory();
    }, () => {
      hiddenFacts.delete(fact);
      paintFacts();
    });
  } else if (el.id === "fadd") {
    const input = byId("fnew") as HTMLInputElement;
    if (input.value.trim()) await act("fact_add", { text: input.value.trim() });
  }
}
