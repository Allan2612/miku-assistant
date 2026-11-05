/**
 * Panel pages around Miku's voice: Palabra clave (listen to every "Hey Miku", label it from the keyboard, retrain the
 * model) and Chat (write to her; voice turns show up too).
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ask, byId, loading, clampPage, comma, dayLabel, esc, head, icon, isTauri, link, localDay, offlineNote, pageItems, pager, state } from "./shared";

const view = () => byId("view")!;
const PLAY = "M8 5.5v13l11-6.5z";
const STOP = "M7 7h10v10H7z";
const SEND = "M4 12h14M13 6l6 6-6 6";
const RETRAIN_CLIPS = 60;
const RETRAIN_YOURS = 20;
const PER_PAGE = 15;

// ---------- Palabra clave ----------
interface Clip { folder: string; name: string; label: "yes" | "no" | null; heard: string | null; suggest: "yes" | "no" | null }
let clips: Clip[] = [];
let loaded = false;
let wakeFilter = "all";
let wakePage = 1;
let selected = "";
let audioCtx: AudioContext | null = null;
let source: AudioBufferSourceNode | null = null;
let playing = "";
let training = false;
let trainMsg = "";

const keyOf = (c: Clip) => (c.folder ? `${c.folder}/${c.name}` : c.name);
const KIND: Record<string, [string, string]> = {
  "": ["ACTIVACIÓN", "ok"],
  near: ["CASI DISPARO", "warn"],
  silent: ["IGNORADA: CASI SILENCIO", "off"],
};
const FILTERS: [string, string, (c: Clip) => boolean][] = [
  ["all", "Todas", () => true],
  ["todo", "Sin marcar", (c) => !c.label],
  ["sug", "Sugeridas", (c) => !c.label && !!c.suggest],
  ["act", "Activaciones", (c) => c.folder === ""],
  ["near", "Casi disparos", (c) => c.folder === "near"],
  ["silent", "Ignoradas", (c) => c.folder === "silent"],
];

function clipTime(name: string): { day: string; at: string; score: number } {
  const [d, rest] = name.split("-");
  return { day: `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`, at: `${rest.slice(0, 2)}:${rest.slice(2, 4)}:${rest.slice(4, 6)}`, score: Number(rest.slice(7, 12)) };
}

const shownClips = () => clips.filter(FILTERS.find(([id]) => id === wakeFilter)![2]);

export function renderWake(): void {
  view().innerHTML = `${head("Palabra clave", `Escucha cada activación y dime si eras tú. Con ${RETRAIN_CLIPS} marcas (${RETRAIN_YOURS} tuyas) puedes reentrenarla para que te oiga mejor.`)}
    <section class="card" id="wk-sum" aria-label="Resumen"></section>
    <div class="toolbar"><div class="chips" role="group" aria-label="Filtrar" id="wk-filters"></div>
      <span class="keys"><span id="wk-msg" class="msg" aria-live="polite"></span> Teclado: <kbd>↑</kbd><kbd>↓</kbd> elegir · <kbd>Espacio</kbd> escuchar · <kbd>S</kbd> era yo · <kbd>N</kbd> no era yo</span></div>
    <section class="card" aria-label="Clips" style="padding:10px 12px"><div id="wk-list">${loading("Leyendo los clips de «Hey Miku»…")}</div></section>`;
  view().onclick = onWakeClick;
  if (!isTauri) return;
  invoke<{ clips: Clip[] }>("wake_clips")
    .then((d) => {
      clips = d.clips;
      loaded = true;
      if (!selected || !clips.some((c) => keyOf(c) === selected)) selected = keyOf(shownClips()[0] ?? clips[0] ?? ({ folder: "", name: "" } as Clip));
      paintWake();
    })
    .catch((err) => (byId("wk-list")!.innerHTML = `<span class="msg bad">${esc(err)}</span>`));
}

function paintWake(): void {
  if (!byId("wk-list")) return;
  const today = localDay().replace(/-/g, "");
  const todays = clips.filter((c) => c.name.startsWith(today));
  const yes = clips.filter((c) => c.label === "yes").length;
  const labeled = clips.filter((c) => c.label).length;
  const ready = labeled >= RETRAIN_CLIPS && yes >= RETRAIN_YOURS;
  const count = (folder: string) => todays.filter((c) => c.folder === folder).length;
  const sug = clips.filter((c) => !c.label && c.suggest);
  byId("wk-sum")!.innerHTML = `
    <div class="card-head"><span style="font-size:14px">Hoy: <b class="mono">${count("")}</b> activaciones · <b class="mono">${count("silent")}</b> ignoradas por silencio · <b class="mono">${count("near")}</b> casi disparos</span>
      <span class="mono" style="color:var(--teal-l)">${labeled} de ${RETRAIN_CLIPS} marcas</span></div>
    <div class="bar" role="img" aria-label="${labeled} de ${RETRAIN_CLIPS} marcas"><div style="width:${Math.min(100, (labeled / RETRAIN_CLIPS) * 100)}%"></div></div>
    <div class="toolbar"><span class="dim">${yes} tuyas${yes < RETRAIN_YOURS ? ` (faltan ${RETRAIN_YOURS - yes})` : ""} · ${labeled - yes} que no eras tú</span>
      <div class="inline">${sug.length ? `<button type="button" class="btn small ghost" id="wk-accept" data-tip="Según cómo terminó cada activación: dijo «Miku», o la despediste">Aceptar ${sug.length} sugerencias</button>` : ""}
        <span id="wk-train-msg" class="dim" aria-live="polite">${esc(trainMsg || (ready ? "Tarda unos minutos y necesita internet. Solo se cambia si el nuevo acierta más en clips que ninguno vio." : ""))}</span>
        <button type="button" class="btn small" id="wk-train"${ready && !training ? "" : " disabled"}>${training ? "Entrenando…" : "Reentrenar"}</button></div></div>`;
  byId("wk-filters")!.innerHTML = FILTERS.map(([id, label, keep]) => `<button type="button" class="chip" data-wf="${id}" aria-pressed="${id === wakeFilter}">${label}<span class="n">${clips.filter(keep).length}</span></button>`).join("");
  const list = shownClips();
  wakePage = clampPage(wakePage, list.length, PER_PAGE);
  byId("wk-list")!.innerHTML = list.length
    ? pageItems(list, wakePage, PER_PAGE).map((c) => {
        const { day, at, score } = clipTime(c.name);
        const [kind, cls] = KIND[c.folder] ?? KIND[""];
        const key = esc(keyOf(c));
        const heard = c.heard === null
          ? `<button type="button" class="btn small ghost" data-heard="${key}"${state.backendOn ? "" : ' disabled title="Enciende a Miku"'}>¿Qué oyó?</button>`
          : `<span class="ellipsis" style="font-size:13px;color:var(--soft)" title="${esc(c.heard)}">Oyó: ${c.heard ? `«${esc(c.heard)}»` : "nada"}</span>`;
        return `<div class="clip${keyOf(c) === selected ? " sel" : ""}" data-row="${key}">
          <button type="button" class="btn play" data-play="${key}" aria-label="Escuchar el clip de las ${at}">${icon(playing === keyOf(c) ? STOP : PLAY, 15)}</button>
          <div style="display:flex;flex-direction:column;gap:3px"><span class="mono dim">${day.slice(5).replace("-", "/")} ${at}</span><span style="display:flex;gap:6px;flex-wrap:wrap"><span class="pill ${cls}">${kind}</span>${!c.label && c.suggest ? `<span class="pill gem" data-tip="Por cómo terminó esa activación">SUGERIDO: ${c.suggest === "yes" ? "ERA YO" : "NO ERA YO"}</span>` : ""}</span></div>
          <div style="display:flex;align-items:center;gap:10px;min-width:0">${heard}${c.folder !== "silent" ? `<span class="mono dim" style="flex:none" data-tip="Lo segura que estaba de oír «Hey Miku» (0 a 1)">${comma(score, 2)}</span>` : ""}</div>
          <div class="chips" role="group" aria-label="¿Eras tú?">
            <button type="button" class="chip" data-label="yes" data-key="${key}" aria-pressed="${c.label === "yes"}">Era yo</button>
            <button type="button" class="chip" data-label="no" data-key="${key}" aria-pressed="${c.label === "no"}" style="${c.label === "no" ? "background:var(--coral);border-color:var(--coral);color:#2a0a08" : ""}">No era yo</button></div>
        </div>`;
      }).join("") + pager("clips", list.length, wakePage, PER_PAGE, "clips")
    : loaded ? `<span class="dim">Nada aquí.</span>` : loading("Leyendo los clips de «Hey Miku»…");
}

const findClip = (key: string) => clips.find((c) => keyOf(c) === key);

/** Selects a clip and shows its page. */
function select(key: string, scroll = true): void {
  selected = key;
  const idx = shownClips().findIndex((c) => keyOf(c) === key);
  if (idx >= 0) wakePage = Math.floor(idx / PER_PAGE) + 1;
  paintWake();
  if (scroll) byId("wk-list")?.querySelector(".clip.sel")?.scrollIntoView({ block: "nearest" });
}

async function play(key: string): Promise<void> {
  const clip = findClip(key);
  if (!clip) return;
  const was = playing;
  source?.stop();
  source = null;
  playing = "";
  if (was === key) return paintWake();
  try {
    const bytes = await invoke<ArrayBuffer>("wake_clip_audio", { folder: clip.folder, name: clip.name });
    audioCtx ??= new AudioContext();
    await audioCtx.resume();
    const buf = await audioCtx.decodeAudioData(bytes);
    // The clips are quiet (3-nov: peaks around -27 dB, near misses -37 dB, too low to hear): the loudest point is
    // brought to -3 dB, at most x30 so a silent clip stays a hiss
    let peak = 0;
    for (const v of buf.getChannelData(0)) peak = Math.max(peak, Math.abs(v));
    const gain = audioCtx.createGain();
    gain.gain.value = Math.min(30, 0.7 / Math.max(peak, 1e-4));
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(gain).connect(audioCtx.destination);
    src.onended = () => {
      if (source !== src) return;
      source = null;
      playing = "";
      paintWake();
    };
    source = src;
    playing = key;
    src.start();
  } catch (err) {
    byId("wk-msg")!.textContent = `No pude reproducirlo: ${err}`;
  }
  paintWake();
}

async function label(key: string, value: "yes" | "no", advance: boolean): Promise<void> {
  const clip = findClip(key);
  if (!clip) return;
  const next = clip.label === value ? null : value; // the same one again: unmark
  await invoke("wake_label", { folder: clip.folder, name: clip.name, label: next });
  clip.label = next;
  if (advance && next) {
    // On to the next clip without a mark (the list may be "Sin marcar": this one just left it)
    const list = clips.filter(FILTERS.find(([id]) => id === wakeFilter)![2]);
    const all = shownClipsWith(clip);
    const after = all.slice(all.findIndex((c) => keyOf(c) === key) + 1).find((c) => !c.label);
    if (after) return select(keyOf(after));
    if (list.length) return select(keyOf(list[0]));
  }
  paintWake();
}

/** The filtered list as it was before `clip` changed (so "the next one" is found from where it was). */
const shownClipsWith = (clip: Clip) => clips.filter((c) => c === clip || FILTERS.find(([id]) => id === wakeFilter)![2](c));

/** Keyboard on Palabra clave: ↑/↓ choose, Space listens, S = it was me, N = it was not. */
export function onWakeKey(ev: KeyboardEvent): void {
  if (!clips.length) return;
  const list = shownClips();
  const idx = list.findIndex((c) => keyOf(c) === selected);
  const k = ev.key.toLowerCase();
  if (k === "arrowdown" || k === "j" || k === "arrowup" || k === "k") {
    ev.preventDefault();
    const down = k === "arrowdown" || k === "j";
    const to = list[Math.min(list.length - 1, Math.max(0, idx < 0 ? 0 : idx + (down ? 1 : -1)))];
    if (to) select(keyOf(to));
  } else if (k === " " && (ev.target as HTMLElement).tagName !== "BUTTON") {
    ev.preventDefault();
    if (selected) void play(selected);
  } else if ((k === "s" || k === "y") && selected) void label(selected, "yes", true);
  else if (k === "n" && selected) void label(selected, "no", true);
}

async function onWakeClick(ev: MouseEvent): Promise<void> {
  const target = ev.target as HTMLElement;
  const el = target.closest<HTMLElement>("button");
  const row = target.closest<HTMLElement>("[data-row]");
  if (row && row.dataset.row !== selected) select(row.dataset.row!, false);
  if (!el) return;
  if (el.dataset.wf) {
    wakeFilter = el.dataset.wf;
    wakePage = 1;
    const first = shownClips()[0];
    if (first && !shownClips().some((c) => keyOf(c) === selected)) selected = keyOf(first);
    paintWake();
  } else if (el.dataset.pager) {
    wakePage = Number(el.dataset.page);
    const first = pageItems(shownClips(), wakePage, PER_PAGE)[0];
    if (first) selected = keyOf(first);
    paintWake();
    byId("wk-list")?.scrollIntoView({ block: "start" });
  } else if (el.dataset.play) void play(el.dataset.play);
  else if (el.dataset.label && el.dataset.key) void label(el.dataset.key, el.dataset.label as "yes" | "no", false);
  else if (el.dataset.heard) {
    const clip = findClip(el.dataset.heard);
    if (!clip) return;
    el.textContent = "Escuchando…";
    (el as HTMLButtonElement).disabled = true;
    const res = await link.request("do:transcribe_clip", { folder: clip.folder, name: clip.name });
    if (res?.ok) clip.heard = res.result;
    else byId("wk-msg")!.textContent = res?.result ?? "Miku no respondió.";
    paintWake();
  } else if (el.id === "wk-accept") {
    const sug = clips.filter((c) => !c.label && c.suggest);
    const yes = sug.filter((c) => c.suggest === "yes").length;
    if (!(await ask(`¿Aceptar ${sug.length} sugerencias?`, `Marca ${yes} como «era yo» (se oyó «Miku») y ${sug.length - yes} como «no era yo» (era otra cosa o la despediste). Puedes cambiar cualquiera después.`, "Aceptar"))) return;
    for (const c of sug) {
      await invoke("wake_label", { folder: c.folder, name: c.name, label: c.suggest });
      c.label = c.suggest;
    }
    paintWake();
  } else if (el.id === "wk-train") {
    training = true;
    trainMsg = "Empezando…";
    paintWake();
    const stop = await listen<string>("train-progress", (e) => {
      try {
        const p = JSON.parse(e.payload.replace(/^@@/, ""));
        trainMsg = p.state === "done" && p.pct === 100 ? p.msg : `${p.pct} % · ${p.msg}`;
      } catch {
        return; // not a progress line
      }
      const msg = byId("wk-train-msg");
      if (msg) msg.textContent = trainMsg;
    });
    try {
      await invoke("wake_train");
    } catch (err) {
      trainMsg = `No se pudo: ${String(err).replace(/^@@.*"msg":\s*"([^"]*)".*$/, "$1")}`;
    } finally {
      stop();
      training = false;
      paintWake();
    }
  }
}

// ---------- Chat ----------
interface Msg { who: "user" | "miku"; text: string; at: string; day: string }
const chatLog: Msg[] = [];
let chatLoaded = false;
let olderDays: string[] | null = null; // days with a conversation before the ones shown, newest first
let thinking = false;
let quiet = localStorage.getItem("miku-chat-quiet") === "1";
let echoTimer: number | null = null;

const nowHM = () => new Date().toTimeString().slice(0, 5);

export function renderChat(): void {
  const on = state.backendOn;
  view().innerHTML = `${head("Chat", "Para cuando no puedes hablar. Lo que le dices por voz también aparece aquí.")}
    ${on ? "" : offlineNote()}
    <section class="card grow" aria-label="Conversación">
      <div id="chat" class="chat grow" aria-live="polite"></div>
      <div id="typing" class="dim" style="min-height:18px"></div>
      <div class="inline"><label for="chat-in" class="sr">Mensaje</label>
        <input id="chat-in" class="input" placeholder="${on ? "Escribe algo… (Enter para enviar)" : "Enciende a Miku para escribirle"}" maxlength="1000" autocomplete="off"${on ? "" : " disabled"}>
        <button type="button" id="chat-send" class="btn" aria-label="Enviar"${on ? "" : " disabled"}>${icon(SEND, 16)}</button></div>
      <div class="switch-row" style="min-height:34px"><div><b style="font-size:13px">Solo texto</b><span class="dim">Miku contesta aquí, sin voz (útil en partida).</span></div>
        <button type="button" class="switch" role="switch" id="chat-quiet" aria-checked="${quiet}" aria-label="Solo texto"><span></span></button></div>
    </section>`;
  view().onclick = (ev) => {
    const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
    if (el?.id === "chat-send") sendChat();
    else if (el?.id === "chat-older") void loadOlder();
    else if (el?.id === "chat-quiet") {
      quiet = !quiet;
      localStorage.setItem("miku-chat-quiet", quiet ? "1" : "0");
      el.setAttribute("aria-checked", String(quiet));
    }
  };
  view().onkeydown = (ev) => {
    if (ev.key === "Enter" && (ev.target as HTMLElement).id === "chat-in") sendChat();
  };
  paintChat(true);
  if (!chatLoaded && on) {
    chatLoaded = true;
    const today = localDay();
    void link.request("conversation", { day: today }).then((d) => {
      if (!d) return;
      chatLog.unshift(...turnsOf(d.turns, today));
      paintChat(true);
    });
    void link.request("memory").then((d) => {
      olderDays = d ? d.days.filter((day: string) => day < today) : [];
      paintChat(false);
    });
  }
}

const turnsOf = (turns: any[], day: string): Msg[] =>
  turns.flatMap((t: any) => [{ who: "user" as const, text: t.user, at: t.at, day }, { who: "miku" as const, text: t.miku, at: t.at, day }]);

async function loadOlder(): Promise<void> {
  const day = olderDays?.shift();
  if (!day) return;
  const box = byId("chat");
  const fromBottom = box ? box.scrollHeight - box.scrollTop : 0;
  const d = await link.request("conversation", { day });
  if (d) chatLog.unshift(...turnsOf(d.turns, day));
  paintChat(false);
  if (box) box.scrollTop = box.scrollHeight - fromBottom;
}

function paintChat(toBottom: boolean): void {
  const box = byId("chat");
  if (!box) return;
  let lastDay = "";
  const older = olderDays?.length ? `<button type="button" class="btn small ghost" id="chat-older" style="align-self:center">Cargar ${esc(dayLabel(olderDays[0]))}</button>` : "";
  box.innerHTML = older + (chatLog.length
    ? chatLog.map((m) => {
        const sep = m.day !== lastDay ? `<div class="daysep">${esc(dayLabel((lastDay = m.day), true))}</div>` : "";
        return `${sep}<div class="bubble ${m.who}"><small>${esc(m.at)}</small>${esc(m.text)}</div>`;
      }).join("")
    : `<span class="dim">Todavía no han hablado hoy.</span>`);
  if (toBottom) box.scrollTop = box.scrollHeight;
  const typing = byId("typing");
  if (typing) typing.textContent = thinking ? "Miku está pensando…" : "";
}

function sendChat(): void {
  const input = byId("chat-in") as HTMLInputElement | null;
  const text = input?.value.trim();
  if (!input || !text) return;
  if (!state.backendOn || !link.send({ type: "text_input", text, quiet })) {
    byId("typing")!.textContent = "Miku está apagada: enciéndela para escribirle.";
    return;
  }
  input.value = "";
  // Her echo of the message (a "user" subtitle) says she took it; none means she was busy and dropped it
  if (echoTimer) clearTimeout(echoTimer);
  echoTimer = window.setTimeout(() => {
    const typing = byId("typing");
    if (typing && !thinking) typing.textContent = "Miku estaba ocupada y no lo recibió. Prueba otra vez en un momento.";
  }, 4000);
}

/** Miku's events (subtitles, state) reach the chat while the panel is open, on any page. */
export function onChatEvent(msg: Record<string, any>): void {
  if (msg.type === "subtitle" && (msg.who === "user" || msg.who === "miku") && msg.text) {
    if (msg.who === "user" && echoTimer) {
      clearTimeout(echoTimer);
      echoTimer = null;
    }
    chatLog.push({ who: msg.who, text: String(msg.text), at: nowHM(), day: localDay() });
    if (chatLog.length > 400) chatLog.shift();
  } else if (msg.type === "state") {
    thinking = msg.value === "thinking";
  } else return;
  const box = byId("chat");
  paintChat(!box || box.scrollHeight - box.scrollTop - box.clientHeight < 60);
}
