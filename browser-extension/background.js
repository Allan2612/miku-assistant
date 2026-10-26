// Miku Assistant - Opera extension (service worker).
// Keeps Miku's backend told about every open tab (id, title, url) and runs its tab commands through the tabs API:
// exact tab ids instead of simulated keystrokes, which broke on pinned tabs, "recently used" Ctrl+Tab, closing
// confirmations and stolen focus. It only talks to Miku's own server on this PC.

const SERVER = "ws://127.0.0.1:8765";
const STATE_DELAY_MS = 400; // tab events come in bursts (a page load fires several): send one state
const MAX_RESULTS = 10;
// Search pages whose result links are read for Miku ("ábreme la segunda opción")
const RESULT_PAGES = /^https?:\/\/([^/]*\.)?(google\.[a-z.]+\/search|youtube\.com\/results|duckduckgo\.com\/|bing\.com\/search)/;

let ws = null;
let stateTimer = null;

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(SERVER);
  ws.onopen = () => {
    send({ type: "ext_hello", version: chrome.runtime.getManifest().version });
    pushState();
  };
  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.type === "ext_cmd") runCommand(msg);
  };
  ws.onclose = () => {
    ws = null;
  };
  ws.onerror = () => {}; // Miku not running: the next alarm tries again
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// Runs in the search page: the visible result links, in order
function collectResults() {
  const out = [];
  const add = (title, href) => {
    title = (title || "").trim();
    if (title && href && /^https?:/.test(href) && !out.some((r) => r.url === href)) {
      out.push({ title: title.slice(0, 90), url: href });
    }
  };
  document.querySelectorAll("a h3").forEach((h) => add(h.textContent, h.closest("a") && h.closest("a").href));
  document.querySelectorAll("a#video-title, a#video-title-link").forEach((a) => add(a.title || a.textContent, a.href));
  document.querySelectorAll('a[data-testid="result-title-a"]').forEach((a) => add(a.textContent, a.href));
  return out;
}

async function pushState() {
  const tabs = await chrome.tabs.query({});
  const state = {
    type: "tabs_state",
    tabs: tabs.map((t) => ({
      id: t.id, window_id: t.windowId, index: t.index, title: t.title || "", url: t.url || "",
      active: t.active, pinned: t.pinned, audible: !!t.audible,
    })),
    results: null,
  };
  const [focused] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (focused && RESULT_PAGES.test(focused.url || "") && focused.status === "complete") {
    try {
      const [run] = await chrome.scripting.executeScript({ target: { tabId: focused.id }, func: collectResults });
      state.results = { tab_id: focused.id, items: (run && run.result || []).slice(0, MAX_RESULTS) };
    } catch {
      // page not readable (still loading, or a permission it lacks): no results this time
    }
  }
  send(state);
}

function schedulePush() {
  clearTimeout(stateTimer);
  stateTimer = setTimeout(pushState, STATE_DELAY_MS);
}

async function focusTab(tab) {
  await chrome.tabs.update(tab.id, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
}

async function runCommand({ id, cmd, args = {} }) {
  try {
    let result = {};
    if (cmd === "open") {
      let tab;
      if (args.tab_id) {
        tab = await chrome.tabs.update(args.tab_id, { url: args.url, active: true });
      } else if (args.new_window) {
        const win = await chrome.windows.create({ url: args.url, focused: true });
        tab = win.tabs[0];
      } else {
        const [current] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        tab = await chrome.tabs.create({ url: args.url, active: true, windowId: current ? current.windowId : undefined });
      }
      await focusTab(tab);
      result = { tab_id: tab.id };
    } else if (cmd === "close") {
      // remove() can resolve only after every page has unloaded (8 tabs took over 6 s and Miku said it failed):
      // a bad id still fails at once, so answer after a short wait at most
      await Promise.race([chrome.tabs.remove(args.tab_ids), new Promise((r) => setTimeout(r, 1500))]);
    } else if (cmd === "activate") {
      await focusTab(await chrome.tabs.get(args.tab_id));
    } else if (cmd === "reload") {
      await chrome.tabs.reload(args.tab_id);
    } else if (cmd === "back") {
      await chrome.tabs.goBack(args.tab_id);
    } else if (cmd === "forward") {
      await chrome.tabs.goForward(args.tab_id);
    } else {
      throw new Error(`comando desconocido: ${cmd}`);
    }
    send({ type: "ext_result", id, ok: true, ...result });
  } catch (err) {
    send({ type: "ext_result", id, ok: false, error: String(err && err.message || err) });
  }
}

for (const event of [chrome.tabs.onCreated, chrome.tabs.onRemoved, chrome.tabs.onActivated, chrome.tabs.onMoved,
                     chrome.tabs.onAttached, chrome.windows.onFocusChanged]) {
  event.addListener(schedulePush);
}
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (change.title || change.url || change.status === "complete" || "audible" in change) schedulePush();
});

// A service worker sleeps when idle: the alarm wakes it to reconnect and keep the connection alive
chrome.alarms.create("miku-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => {
  connect();
  send({ type: "ext_ping" });
});
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
