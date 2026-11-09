/**
 * What Miku does with her body in each moment of a conversation (docs/plan-expresiones.md, phase 3).
 * The backend only says what is happening (listening, thinking, speaking, you are talking); the
 * reactions are chosen here, with some randomness so she never repeats the same choreography.
 */

import { live2d } from "./live2d";
import { EMOTIONS, GESTURES } from "./motion";

type Mode = "hidden" | "idle" | "listening" | "thinking" | "speaking";

export interface SpeakInfo {
  emotion?: string;
  farewell?: boolean;
  gesture?: string;
  outcome?: "ok" | "fail";
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const side = () => (Math.random() < 0.5 ? -1 : 1);
const wait = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
const POSITIVE = new Set(["happy", "excited", "proud", "playful"]);

class Behavior {
  private mode: Mode = "hidden";
  // Timers of the current mode: cleared whenever the mode changes, so no old reaction fires late
  private timers = new Set<number>();
  private lastNod = 0;
  private saidGoodbye = false;

  private get m() {
    return live2d.motion;
  }

  private after(ms: number, fn: () => void): void {
    const id = window.setTimeout(() => {
      this.timers.delete(id);
      fn();
    }, ms);
    this.timers.add(id);
  }

  private enter(mode: Mode): void {
    this.timers.forEach((t) => clearTimeout(t));
    this.timers.clear();
    this.mode = mode;
  }

  /** She pops up from below the window edge, then smiles and glances at you. */
  appear(): void {
    this.enter("idle");
    this.saidGoodbye = false;
    this.m.energy = 1;
    this.m.setFocus(side() * 0.5, -0.2);
    this.m.play("enter");
    this.after(450, () => {
      this.m.setFocus(0, 0);
      this.m.setEmotion("happy");
    });
    this.after(2200, () => this.m.setEmotion("neutral"));
    this.scheduleIdle(5000);
  }

  /** Resolves when she has left the frame (a bow first after a goodbye). */
  async disappear(): Promise<void> {
    this.enter("hidden");
    if (this.saidGoodbye) {
      this.m.play("bow");
      await wait(900);
    }
    this.m.play("exit");
    await wait(450);
  }

  listening(): void {
    if (this.mode === "hidden") return;
    this.enter("listening");
    this.m.energy = 0.7; // still and attentive
    this.m.setFocus(0, 0);
    this.m.play("brow_flick");
  }

  /** You are talking: an attentive nod now and then (backchannel). */
  userSpeech(): void {
    if (this.mode !== "listening") return;
    const nod = () => {
      if (this.mode !== "listening") return;
      if (performance.now() - this.lastNod > 1200) {
        this.m.play(Math.random() < 0.7 ? "small_nod" : "nod", { scale: rand(0.6, 1) });
        this.lastNod = performance.now();
      }
      this.after(rand(1600, 3200), nod);
    };
    this.after(rand(700, 1400), nod);
  }

  /** Looks up and aside (people look away to think), arms in; switches side, then sighs if it drags on. */
  thinking(): void {
    if (this.mode === "hidden") return;
    this.enter("thinking");
    this.m.energy = 0.8;
    const s = side();
    this.m.setEmotion("thinking");
    this.m.setFocus(s * 0.6, 0.5);
    this.after(3000, () => {
      this.m.setFocus(-s * 0.5, 0.45);
      this.m.play("tilt", { scale: 0.6, mirror: s > 0 });
    });
    this.after(7000, () => this.m.play("sigh"));
  }

  speak(info: SpeakInfo): void {
    if (this.mode === "hidden") return;
    this.enter("speaking");
    this.m.energy = 1.25;
    this.m.setFocus(0, 0);
    const emotion = info.emotion && EMOTIONS[info.emotion] ? info.emotion : "neutral";
    this.m.setEmotion(emotion);
    this.saidGoodbye = Boolean(info.farewell);
    if (info.farewell) this.m.play("wave", { mirror: Math.random() < 0.5 });
    else if (info.gesture === "attention") this.m.play("attention");
    else if (info.gesture === "greet") this.m.play("hop");
    else if (info.gesture === "none") return; // the rest of an answer: its first sentence made the gesture
    else if (info.outcome === "fail") this.m.play("shrug");
    else if (info.outcome === "ok" && POSITIVE.has(emotion)) this.m.play("bounce");
    else if (emotion === "surprised") this.m.play("surprise", { scale: 0.7 });
    else if (emotion === "sad") this.m.play("sigh", { scale: 0.7 });
    else if (emotion === "confused") this.m.play("tilt", { mirror: Math.random() < 0.5 });
    else if (emotion === "excited") this.m.play("hop");
    else if (emotion === "proud") this.m.play("open_arms", { scale: 0.6 });
    else this.m.play("small_nod", { scale: 0.6 });
  }

  /** End of her turn: eyes back on you, a blink, and the face relaxes after a moment. */
  speakEnd(): void {
    if (this.mode !== "speaking") return;
    this.enter("idle");
    this.m.energy = 1;
    this.m.setFocus(0, 0);
    this.m.blink();
    this.after(2500, () => this.m.setEmotion("neutral"));
    this.scheduleIdle(4000);
  }

  idle(): void {
    if (this.mode === "hidden" || this.mode === "speaking") return;
    this.enter("idle");
    this.m.energy = 1;
    this.m.setFocus(0, 0);
    this.m.setEmotion("neutral");
    this.scheduleIdle(3000);
  }

  /** A click: a little start, then she giggles and blushes. */
  tap(): void {
    if (this.mode === "hidden") return;
    this.m.play("surprise", { scale: 0.5 });
    window.setTimeout(() => {
      this.m.play("giggle");
      this.m.setEmotion("shy");
    }, 280);
    window.setTimeout(() => {
      if (this.mode !== "thinking") this.m.setEmotion("neutral");
    }, 2600);
  }

  /** Waiting with nothing to do: a look around, a stretch, a hum, a glance. */
  private scheduleIdle(firstMs: number): void {
    this.after(firstMs + rand(0, 3000), () => {
      if (this.mode !== "idle") return;
      const r = Math.random();
      if (r < 0.3) {
        const s = side();
        this.m.setFocus(s * 0.6, rand(-0.3, 0.3));
        this.after(rand(900, 1800), () => this.m.setFocus(0, 0));
      } else if (r < 0.5) this.m.play("look_around", { mirror: Math.random() < 0.5 });
      else if (r < 0.65) this.m.play("stretch");
      else if (r < 0.85) this.m.play("hum");
      else this.m.play("tilt", { scale: 0.7, mirror: Math.random() < 0.5 });
      this.scheduleIdle(6000);
    });
  }
}

export const behavior = new Behavior();

// Debug: ?anim in the URL (or localStorage.mikuDebug = 1) lets the keyboard play every gesture
// (1-9, 0, q..p, n, m; Shift+letter mirrored) and emotion (a..l, ;, z, x), and exposes the engine for headless renders
const debug = (() => {
  try {
    return location.search.includes("anim") || localStorage.getItem("mikuDebug") === "1";
  } catch (_) {
    return false;
  }
})();
if (debug) {
  const gestureKeys = "1234567890qwetyuiopnm".split(""); // no "r": it resets the framing
  const emotionKeys = "asdfghjkl;zx".split("");
  const gestures = Object.keys(GESTURES);
  const emotions = Object.keys(EMOTIONS);
  (window as unknown as { __miku: unknown }).__miku = { live2d, behavior };
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.altKey) return;
    const g = gestures[gestureKeys.indexOf(e.key.toLowerCase())];
    const em = emotions[emotionKeys.indexOf(e.key)];
    if (g) live2d.motion.play(g, { mirror: e.shiftKey });
    if (em) live2d.motion.setEmotion(em);
    if (g || em) console.log("[Anim]", g ?? em);
  });
}
