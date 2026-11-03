/**
 * Panel pages around Miku's voice (phase 4): Palabra clave (listen to every "Hey Miku" and label it, for retraining
 * the model) and Chat (write to her; voice turns show up too).
 */

import { invoke } from "@tauri-apps/api/core";
import { byId, esc, head, icon, isTauri, link, state } from "./shared";

const view = () => byId("view")!;
const PLAY = "M8 5.5v13l11-6.5z";
const STOP = "M7 7h10v10H7z";
const SEND = "M4 12h14M13 6l6 6-6 6";
const RETRAIN_CLIPS = 60;
const RETRAIN_YOURS = 20;

// ---------- Palabra clave ----------
interface Clip { folder: string; name: string; label: "yes" | "no" | null; heard: string | null }
let clips: Clip[] = [];
let wakeFilter = "all";
let player: HTMLAudioElement | null = null;
let playing = "";

const keyOf = (c: Clip) => (c.folder ? `${c.folder}/${c.name}` : c.name);
const KIND: Record<string, [string, string]> = {
  "": ["ACTIVACIÓN", "ok"],
  near: ["CASI DISPARO", "gem"],
  silent: ["IGNORADA: SILENCIO", "off"],
};
const FILTERS: [string, string, (c: Clip) => boolean][] = [
  ["all", "Todas", () => true],
  ["act", "Activaciones", (c) => c.folder === ""],
  ["near", "Casi disparos", (c) => c.folder === "near"],
  ["silent", "Ignoradas", (c) => c.folder === "silent"],
  ["todo", "Sin marcar", (c) => !c.label],
];

function clipTime(name: string): { day: string; at: string; score: number } {
  const [d, rest] = name.split("-");
  return { day: `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`, at: `${rest.slice(0, 2)}:${rest.slice(2, 4)}:${rest.slice(4, 6)}`, score: Number(rest.slice(7, 12)) };
}

export function renderWake(): void {
  view().innerHTML = `${head("PALABRA CLAVE", "«Hey Miku»", "Escucha cada activación y dime si eras tú. Con 60 marcas se puede reentrenar el modelo para que te oiga mejor y se active menos sola.")}
    <div id="wk-stats" class="row-wrap"></div>
    <div class="toolbar"><div class="chips" role="group" aria-label="Filtrar">${FILTERS.map(([id, label]) => `<button type="button" class="chip" data-wf="${id}" aria-pressed="${id === wakeFilter}">${label}</button>`).join("")}</div>
      <span id="wk-msg" class="msg"></span></div>
    <section class="card" aria-label="Clips"><div id="wk-list"><span class="dim">Cargando…</span></div></section>`;
  view().onclick = onWakeClick;
  if (!isTauri) return;
  invoke<{ clips: Clip[] }>("wake_clips")
    .then((d) => {
      clips = d.clips;
      paintWake();
    })
    .catch((err) => (byId("wk-list")!.innerHTML = `<span class="msg bad">${esc(err)}</span>`));
}

function paintWake(): void {
  const today = localDay("");
  const todays = clips.filter((c) => c.name.startsWith(today));
  const yes = clips.filter((c) => c.label === "yes").length;
  const labeled = clips.filter((c) => c.label).length;
  const ready = labeled >= RETRAIN_CLIPS && yes >= RETRAIN_YOURS;
  const stat = (label: string, value: number, color: string) =>
    `<div class="card kpi"><span class="muted" style="font-size:12px">${label}</span><span class="big" style="color:${color}">${value}</span></div>`;
  byId("wk-stats")!.innerHTML = `
    ${stat("Activaciones hoy", todays.filter((c) => c.folder === "").length, "var(--text)")}
    ${stat("Ignoradas hoy (silencio)", todays.filter((c) => c.folder === "silent").length, "#a9bfbd")}
    ${stat("Casi disparos hoy", todays.filter((c) => c.folder === "near").length, "var(--pink-l)")}
    <div class="card kpi" style="flex:2 1 320px"><div class="card-head"><span class="muted" style="font-size:12px">${ready ? "Listo para reentrenar" : "Para reentrenar"}</span>
      <span class="mono" style="color:var(--teal-l)">${labeled} de ${RETRAIN_CLIPS}</span></div>
      <div class="bar"><div style="width:${Math.min(100, (labeled / RETRAIN_CLIPS) * 100)}%"></div></div>
      <span class="dim">${yes} tuyas (hacen falta ${RETRAIN_YOURS}) · ${labeled - yes} que no eras tú</span></div>`;
  const keep = FILTERS.find(([id]) => id === wakeFilter)![2];
  const shown = clips.filter(keep).slice(0, 80);
  byId("wk-list")!.innerHTML = shown.length
    ? shown.map((c) => {
        const { day, at, score } = clipTime(c.name);
        const [kind, cls] = KIND[c.folder] ?? KIND[""];
        const key = esc(keyOf(c));
        const heard = c.heard === null
          ? `<button type="button" class="btn small ghost" style="align-self:flex-start" data-heard="${key}"${state.backendOn ? "" : " disabled title=\"Enciende a Miku\""}>¿Qué oyó?</button>`
          : `<span style="font-size:14px;color:var(--soft)">Oyó: ${c.heard ? `«${esc(c.heard)}»` : "nada"}</span>`;
        return `<div class="list-row" style="min-height:70px;gap:14px">
          <button type="button" class="btn" style="width:44px;padding:0;border-radius:22px" data-play="${key}" aria-label="Escuchar el clip de las ${at}">${icon(playing === keyOf(c) ? STOP : PLAY, 16)}</button>
          <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:5px">
            <div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px"><span class="mono dim">${day.slice(5)} ${at}</span>
              <span class="mono" style="font-size:12px">puntuación ${score.toFixed(3).replace(".", ",")}</span><span class="pill ${cls}">${kind}</span></div>
            ${heard}</div>
          <div class="chips" role="group" aria-label="¿Eras tú?">
            <button type="button" class="chip" data-label="yes" data-key="${key}" aria-pressed="${c.label === "yes"}">Era yo</button>
            <button type="button" class="chip" data-label="no" data-key="${key}" aria-pressed="${c.label === "no"}" style="${c.label === "no" ? "background:var(--pink);border-color:var(--pink);color:#2a0a18" : ""}">No era yo</button></div>
        </div>`;
      }).join("")
    : `<span class="dim">Nada aquí todavía.</span>`;
}

const findClip = (key: string) => clips.find((c) => keyOf(c) === key);

async function onWakeClick(ev: MouseEvent): Promise<void> {
  const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
  if (!el) return;
  if (el.dataset.wf) {
    wakeFilter = el.dataset.wf;
    document.querySelectorAll<HTMLElement>("[data-wf]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.wf === wakeFilter)));
    paintWake();
  } else if (el.dataset.play) {
    const clip = findClip(el.dataset.play);
    if (!clip) return;
    player?.pause();
    if (playing === el.dataset.play) {
      playing = "";
      paintWake();
      return;
    }
    try {
      const bytes = await invoke<ArrayBuffer>("wake_clip_audio", { folder: clip.folder, name: clip.name });
      const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
      player = new Audio(url);
      playing = el.dataset.play;
      player.onended = () => {
        URL.revokeObjectURL(url);
        playing = "";
        paintWake();
      };
      await player.play();
    } catch (err) {
      byId("wk-msg")!.textContent = `No pude reproducirlo: ${err}`;
    }
    paintWake();
  } else if (el.dataset.label && el.dataset.key) {
    const clip = findClip(el.dataset.key);
    if (!clip) return;
    const label = clip.label === el.dataset.label ? null : (el.dataset.label as "yes" | "no"); // again: unmark
    await invoke("wake_label", { folder: clip.folder, name: clip.name, label });
    clip.label = label;
    paintWake();
  } else if (el.dataset.heard) {
    const clip = findClip(el.dataset.heard);
    if (!clip) return;
    el.textContent = "Escuchando…";
    (el as HTMLButtonElement).disabled = true;
    const res = await link.request("do:transcribe_clip", { folder: clip.folder, name: clip.name });
    if (res?.ok) clip.heard = res.result;
    else byId("wk-msg")!.textContent = res?.result ?? "Miku no respondió.";
    paintWake();
  }
}

// ---------- Chat ----------
interface Msg { who: "user" | "miku"; text: string; at: string }
const chatLog: Msg[] = [];
let chatLoaded = false;
let thinking = false;
let quiet = localStorage.getItem("miku-chat-quiet") === "1";
let echoTimer: number | null = null;

const nowHM = () => new Date().toTimeString().slice(0, 5);
/** Today in the PC's own time zone (toISOString is UTC: after 18:00 in Costa Rica it is already tomorrow). */
const localDay = (sep = "-") => {
  const d = new Date();
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join(sep);
};

export function renderChat(): void {
  view().innerHTML = `${head("CHAT", "Escríbele a Miku", "Para cuando no puedes hablar. Lo que le dices por voz también aparece aquí.")}
    <section class="card" aria-label="Conversación" style="flex:1;min-height:420px">
      <div id="chat" class="chat" style="flex:1;max-height:none;min-height:300px" aria-live="polite"></div>
      <div id="typing" class="dim" style="min-height:18px"></div>
      <div class="inline"><label for="chat-in" class="sr">Mensaje</label>
        <input id="chat-in" class="input" placeholder="${state.backendOn ? "Escribe algo… (Enter para enviar)" : "Enciende a Miku para escribirle"}" maxlength="1000" autocomplete="off">
        <button type="button" id="chat-send" class="btn" aria-label="Enviar">${icon(SEND, 16)}</button></div>
      <div class="switch-row" style="min-height:36px"><div><b style="font-size:13px">Solo texto</b><span class="dim">Miku contesta aquí, sin voz (útil en partida).</span></div>
        <button type="button" class="switch" role="switch" id="chat-quiet" aria-checked="${quiet}" aria-label="Solo texto"><span></span></button></div>
    </section>`;
  view().onclick = (ev) => {
    const el = (ev.target as HTMLElement).closest<HTMLElement>("button");
    if (el?.id === "chat-send") sendChat();
    else if (el?.id === "chat-quiet") {
      quiet = !quiet;
      localStorage.setItem("miku-chat-quiet", quiet ? "1" : "0");
      el.setAttribute("aria-checked", String(quiet));
    }
  };
  view().onkeydown = (ev) => {
    if (ev.key === "Enter" && (ev.target as HTMLElement).id === "chat-in") sendChat();
  };
  paintChat();
  if (!chatLoaded && state.backendOn) {
    chatLoaded = true;
    const today = localDay();
    void link.request("conversation", { day: today }).then((d) => {
      if (!d) return;
      const earlier: Msg[] = d.turns.slice(-30).flatMap((t: any) => [{ who: "user", text: t.user, at: t.at }, { who: "miku", text: t.miku, at: t.at }]);
      chatLog.unshift(...earlier);
      paintChat();
    });
  }
}

function paintChat(): void {
  const box = byId("chat");
  if (!box) return;
  box.innerHTML = chatLog.length
    ? chatLog.map((m) => `<div class="bubble ${m.who}"><small>${esc(m.at)}</small>${esc(m.text)}</div>`).join("")
    : `<span class="dim">Todavía no habéis hablado hoy.</span>`;
  box.scrollTop = box.scrollHeight;
  const typing = byId("typing");
  if (typing) typing.textContent = thinking ? "Miku está pensando…" : "";
}

function sendChat(): void {
  const input = byId("chat-in") as HTMLInputElement | null;
  const text = input?.value.trim();
  if (!input || !text) return;
  if (!state.backendOn || !link.send({ type: "text_input", text, quiet })) {
    byId("typing")!.textContent = "Miku está apagada: enciéndela desde Inicio.";
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
    chatLog.push({ who: msg.who, text: String(msg.text), at: nowHM() });
    if (chatLog.length > 200) chatLog.shift();
  } else if (msg.type === "state") {
    thinking = msg.value === "thinking";
  } else return;
  paintChat();
}
