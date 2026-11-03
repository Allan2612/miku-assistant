/**
 * Live2D model loader and PixiJS management.
 * Optimized for low resource usage: stopped ticker when hidden, 30 FPS cap when visible.
 * Configured with safe-framing bounds so hair twin-tails and body are never clipped.
 */

import * as PIXI from "pixi.js";
import { Live2DModel } from "pixi-live2d-display-lipsyncpatch/cubism4";
import { GAIN, MotionEngine, OWNED, REST } from "./motion";

// Expose PIXI globally as required by pixi-live2d-display
(window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI;

// Register PIXI ticker with pixi-live2d-display
Live2DModel.registerTicker(PIXI.Ticker);

// Unlocks browser audio policy on first user gesture
let audioUnlocked = false;
export function unlockAudio(): void {
  if (audioUnlocked) return;
  audioUnlocked = true;
  try {
    const silent = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
    silent.play().then(() => silent.pause()).catch(() => {});
  } catch (_) {}
}

if (typeof window !== "undefined") {
  ["pointerdown", "click", "keydown", "focus"].forEach((evt) => {
    window.addEventListener(evt, unlockAudio, { passive: true });
  });
}

export interface Live2DManager {
  app: PIXI.Application | null;
  model: Live2DModel | null;
  canvas: HTMLCanvasElement | null;
  isModelReady: boolean;
  /** Procedural motion: emotions, gaze, gestures (see motion.ts). */
  motion: MotionEngine;
  init(canvas: HTMLCanvasElement, width: number, height: number, fps?: number): Promise<void>;
  loadModel(modelPath: string, scale?: number): Promise<Live2DModel>;
  setExpression(name: string): boolean;
  startTicker(): void;
  stopTicker(): void;
  hitTest(clientX: number, clientY: number): boolean;
  /** Resolves true when playback ended (or failed), false when interrupted by stopSpeaking().
   *  `words`: [start_ms, end_ms] of each spoken word, to shape the mouth and the head beats. */
  speak(audioB64: string, mime?: string, words?: [number, number][]): Promise<boolean>;
  stopSpeaking(): void;
  destroy(): void;
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);

class Live2DManagerImpl implements Live2DManager {
  app: PIXI.Application | null = null;
  model: Live2DModel | null = null;
  canvas: HTMLCanvasElement | null = null;
  isModelReady: boolean = false;
  motion = new MotionEngine();
  private activeFallbackAudio: HTMLAudioElement | null = null;
  // Cleanup of the playing audio; stopSpeaking() must run it or the lip-sync interval leaks (H-045)
  private interruptActive: (() => void) | null = null;
  private isSpeakingActive: boolean = false;
  private lastFrameMs = 0;
  // Parameters the motion engine drives, with the model's resting value of each
  private owned: { index: number; id: string; rest: number; gain: number }[] = [];
  private basePivotY = 0;
  // Lip sync from the real audio level (was random values every 60 ms)
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private analyserBuf: Float32Array<ArrayBuffer> | null = null;
  private mouth = 0;
  private lipSyncFromAudio = false;
  private words: [number, number][] = [];
  private wordIdx = -1;

  /** Right after the (disabled) motions: every owned parameter is SET to rest + offset, so nothing
   *  accumulates and physics (hair, tie, skirt) then reacts to the head and body moving. */
  private applyMotion(core: any): void {
    const now = performance.now();
    const dt = this.lastFrameMs ? Math.min(0.1, (now - this.lastFrameMs) / 1000) : 1 / 30;
    this.lastFrameMs = now;
    const frame = this.motion.update(dt);
    const open = 1 - frame.blink;
    for (const { index, id, rest, gain } of this.owned) {
      let v = rest + (frame.params[id] ?? 0) * gain;
      if (id === "ParamEyeLOpen" || id === "ParamEyeROpen") v *= open;
      core.setParameterValueByIndex(index, v); // clamps to the parameter's range
    }
    // Hops and bows move the whole model; the pivot keeps the user's drag position untouched
    if (this.model) this.model.pivot.y = this.basePivotY - frame.y / this.model.scale.y;
  }

  /** Runs every frame right before the model is drawn: the mouth, from the voice's level. */
  private animateMouth(core: any): void {
    const dt = 1 / Math.max(10, this.app?.ticker.FPS || 30);
    let level = 0;
    const audio = this.activeFallbackAudio;
    if (this.isSpeakingActive && this.lipSyncFromAudio && this.analyser && this.analyserBuf) {
      this.analyser.getFloatTimeDomainData(this.analyserBuf);
      let sum = 0;
      for (const s of this.analyserBuf) sum += s * s;
      level = Math.min(1, Math.sqrt(sum / this.analyserBuf.length) * 6);
    } else if (this.isSpeakingActive && audio && !audio.paused) {
      // No analyser: soft syllable-like rhythm (two mixed rates, never fully random jumps)
      const t = performance.now() / 1000;
      level = 0.25 + 0.3 * Math.abs(Math.sin(t * 9.0)) * (0.6 + 0.4 * Math.sin(t * 2.3));
    }
    if (this.isSpeakingActive && audio && this.words.length) level *= this.followWords(audio.currentTime * 1000);
    // Fast to open, a bit slower to close, like real speech
    const km = 1 - Math.exp(-dt / (level > this.mouth ? 0.035 : 0.09));
    this.mouth += (level - this.mouth) * km;
    if (this.isSpeakingActive || this.mouth > 0.01) {
      try {
        core.setParameterValueById("ParamMouthOpenY", this.mouth);
      } catch (_) {}
    }
  }

  /** Word timings: the mouth closes between words, each word gets its own mouth shape, a pause
   *  before a word brings a head beat, and the end of a phrase a blink. Returns the mouth gain. */
  private followWords(ms: number): number {
    const w = this.words;
    let i = this.wordIdx;
    while (i + 1 < w.length && ms >= w[i + 1][0] - 40) i++;
    if (i !== this.wordIdx) {
      const gap = i > 0 ? w[i][0] - w[i - 1][1] : 1000;
      this.wordIdx = i;
      this.motion.mouthForm = rand(-0.3, 0.6);
      if (gap > 160 || (i % 4 === 0 && w[i][1] - w[i][0] > 250)) this.motion.play("beat", { scale: rand(0.6, 1.3) });
      if (gap > 350 && i > 0) this.motion.blink();
    }
    return i >= 0 && ms <= w[i][1] + 40 ? 1 : 0.3;
  }

  /** Routes an <audio> element through an analyser so the mouth follows its volume.
   *  Returns null when it could not (the audio then plays directly, with a fallback rhythm). */
  private connectLipSync(audio: HTMLAudioElement): MediaElementAudioSourceNode | null {
    try {
      this.audioCtx ??= new AudioContext();
      if (this.audioCtx.state !== "running") {
        // Routing audio through a suspended context would play it SILENTLY: play it directly
        // this time (fallback mouth rhythm) and try to wake the context for the next phrase
        void this.audioCtx.resume();
        return null;
      }
      if (!this.analyser) {
        this.analyser = this.audioCtx.createAnalyser();
        this.analyser.fftSize = 1024;
        this.analyser.connect(this.audioCtx.destination);
        this.analyserBuf = new Float32Array(this.analyser.fftSize);
      }
      const source = this.audioCtx.createMediaElementSource(audio);
      source.connect(this.analyser);
      return source;
    } catch (err) {
      // Audio still plays directly, with the fallback mouth rhythm
      console.warn("[Live2D] Lip sync analyser unavailable:", err);
      return null;
    }
  }

  async init(canvas: HTMLCanvasElement, width: number, height: number, fps: number = 30): Promise<void> {
    this.canvas = canvas;

    // Create lightweight Pixi application with transparent background
    this.app = new PIXI.Application({
      view: canvas,
      width,
      height,
      backgroundAlpha: 0,
      antialias: true,
      autoStart: true,
      powerPreference: "low-power",
    });

    // Enforce 30 FPS cap to minimize GPU/CPU utilization
    this.app.ticker.maxFPS = fps;
  }

  async loadModel(modelPath: string, scale: number = 0.25): Promise<Live2DModel> {
    if (!this.app) {
      throw new Error("Pixi application not initialized. Call init() first.");
    }

    try {
      // Apply Cubism 5 compatibility bridge
      const Core = (window as unknown as { Live2DCubismCore?: any }).Live2DCubismCore;
      if (Core && Core.Model && Core.Model.fromMoc && !Core._cubism5Patched) {
        Core._cubism5Patched = true;
        const originalFromMoc = Core.Model.fromMoc;
        Core.Model.fromMoc = function (moc: any) {
          const m = originalFromMoc.call(this, moc);
          if (m && m.drawables && !m.drawables.renderOrders) {
            m.drawables.renderOrders =
              m.renderOrders ||
              (m.getRenderOrders && m.getRenderOrders()) ||
              m.drawables.drawOrders;
          }
          return m;
        };
      }

      // Load model using Cubism runtime
      const model = await Live2DModel.from(modelPath, {
        autoFocus: false,
        autoHitTest: false,
      });

      this.model = model;

      // Safe-framing calculations: ensure hair twin-tails and waist-up body fit completely inside the window
      const modelW = model.internalModel?.width || 2000;
      const modelH = model.internalModel?.height || 2000;
      const maxFitWidth = (this.app.screen.width * 0.90) / modelW;
      const maxFitHeight = (this.app.screen.height * 0.92) / modelH;
      const autoFitScale = Math.min(maxFitWidth, maxFitHeight);

      // Default framing: elegant waist-up view with 10% breathing room on all sides
      // live2d.scale in config.yaml: 0 = fit the window automatically (H-046)
      const defaultScale = scale > 0 ? scale : autoFitScale * 1.08;
      const defaultX = this.app.screen.width / 2;
      const defaultY = this.app.screen.height * 0.68;

      model.anchor.set(0.5, 0.5);

      const storageKey = `miku_transform_${encodeURIComponent(modelPath)}`;

      // Restore saved framing if valid and not clipped, otherwise use safe default
      let appliedScale = defaultScale;
      let appliedX = defaultX;
      let appliedY = defaultY;

      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (
            parsed &&
            typeof parsed.scale === "number" &&
            typeof parsed.x === "number" &&
            typeof parsed.y === "number"
          ) {
            // Guard strictly against clipping transforms
            if (
              parsed.scale <= autoFitScale * 1.35 &&
              parsed.x >= this.app.screen.width * 0.3 &&
              parsed.x <= this.app.screen.width * 0.7
            ) {
              appliedScale = parsed.scale;
              appliedX = parsed.x;
              appliedY = parsed.y;
            } else {
              localStorage.removeItem(storageKey);
            }
          }
        }
      } catch (_) {}

      model.scale.set(appliedScale);
      model.position.set(appliedX, appliedY);

      console.log(
        `[Live2D] Model loaded (${modelW}x${modelH}). Safe scale: ${appliedScale.toFixed(4)}. Position: (${appliedX.toFixed(1)}, ${appliedY.toFixed(1)})`
      );

      // The motion engine replaces the model's idle clips (some opened her arms at random), its blink
      // and the head sway of its breathing; only the chest breath stays
      const internal = model.internalModel as any;
      const core = internal.coreModel;
      internal.motionManager.groups.idle = "__none__";
      internal.motionManager.stopAllMotions();
      internal.eyeBlink = undefined;
      internal.breath?.setParameters(
        internal.breath.getParameters().filter((b: any) => b.parameterId === internal.idParamBreath)
      );
      this.owned = OWNED.map((id) => ({ id, index: core.getParameterIndex(id) as number }))
        .filter((p) => p.index < core.getParameterCount())
        .map((p) => ({ ...p, rest: REST[p.id] ?? (core.getParameterDefaultValue(p.index) as number), gain: GAIN[p.id] ?? 1 }));
      this.basePivotY = model.pivot.y;
      internal.on("afterMotionUpdate", () => this.applyMotion(core));
      internal.on("beforeModelUpdate", () => this.animateMouth(core));

      // Setup interactive drag, wheel zoom, double-click reset
      this.setupInteractiveControls(model, defaultX, defaultY, defaultScale, storageKey);

      // Add to scene
      this.app.stage.addChild(model);
      this.isModelReady = true;

      return model;
    } catch (err) {
      console.error("[Live2D] Failed to load model:", err);
      throw err;
    }
  }

  private setupInteractiveControls(
    model: Live2DModel,
    defaultX: number,
    defaultY: number,
    defaultScale: number,
    storageKey: string
  ): void {
    if (!this.canvas) return;

    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let initX = 0;
    let initY = 0;

    const saveTransform = () => {
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({ x: model.position.x, y: model.position.y, scale: model.scale.x })
        );
      } catch (_) {}
    };

    this.canvas.addEventListener("pointerdown", (e) => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      initX = model.position.x;
      initY = model.position.y;
    });

    window.addEventListener("pointermove", (e) => {
      if (isDragging) {
        model.position.x = initX + (e.clientX - startX);
        model.position.y = initY + (e.clientY - startY);
      }
    });

    window.addEventListener("pointerup", () => {
      if (isDragging) {
        isDragging = false;
        saveTransform();
      }
    });

    // Zoom with mouse wheel
    this.canvas.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.04 : 0.96;
        // Bounded so Miku can neither vanish nor overflow the window (H-046)
        const next = Math.min(defaultScale * 1.25, Math.max(defaultScale * 0.5, model.scale.x * factor));
        model.scale.set(next);
        saveTransform();
      },
      { passive: false }
    );

    // Double click to reset to default waist-up framing
    this.canvas.addEventListener("dblclick", () => {
      model.position.set(defaultX, defaultY);
      model.scale.set(defaultScale);
      saveTransform();
      console.log("[Live2D] Reset to default waist-up framing");
    });

    // Press 'R' key to reset framing
    window.addEventListener("keydown", (e) => {
      if ((e.key === "r" || e.key === "R") && !e.ctrlKey && !e.altKey) {
        model.position.set(defaultX, defaultY);
        model.scale.set(defaultScale);
        saveTransform();
        console.log("[Live2D] Reset to default waist-up framing via 'R' key");
      }
    });
  }

  setExpression(name: string): boolean {
    this.motion.setEmotion(name);
    return true;
  }

  startTicker(): void {
    if (this.app && !this.app.ticker.started) {
      this.app.ticker.start();
    }
  }

  stopTicker(): void {
    if (this.app && this.app.ticker.started) {
      this.app.ticker.stop();
    }
  }

  hitTest(clientX: number, clientY: number): boolean {
    if (!this.model || !this.isModelReady || !this.canvas) return false;

    const rect = this.canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    if (x < 0 || y < 0 || x > rect.width || y > rect.height) {
      return false;
    }

    const bounds = this.model.getBounds();
    return bounds.contains(x, y);
  }

  private base64ToBlobUrl(base64: string, mime: string): string {
    const binaryString = window.atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const blob = new Blob([bytes], { type: mime });
    return URL.createObjectURL(blob);
  }

  speak(audioB64: string, mime: string = "audio/wav", words: [number, number][] = []): Promise<boolean> {
    if (!this.model) {
      return Promise.resolve(true);
    }

    this.stopSpeaking();
    this.isSpeakingActive = true;
    this.words = words;
    this.wordIdx = -1;

    const normalizedMime = !mime || mime === "audio/mp3" ? "audio/mpeg" : mime;
    let blobUrl = "";
    try {
      blobUrl = this.base64ToBlobUrl(audioB64, normalizedMime);
    } catch (err) {
      console.warn("[Live2D] Error converting base64 to blob:", err);
      blobUrl = `data:${normalizedMime};base64,${audioB64}`;
    }

    return new Promise<boolean>((resolve) => {
      let finished = false;
      const audio = new Audio(blobUrl);
      audio.volume = 1.0;
      audio.preload = "auto";
      this.activeFallbackAudio = audio;

      // The mouth is driven every frame by animateMouth() from this audio's level
      const lipSource = this.connectLipSync(audio);
      this.lipSyncFromAudio = lipSource !== null;

      const cleanup = (completed: boolean = true) => {
        if (finished) return;
        finished = true;
        this.isSpeakingActive = false;
        this.motion.mouthForm = 0;
        if (this.interruptActive === interrupt) {
          this.interruptActive = null;
        }
        audio.pause();
        // A connected source keeps its <audio> alive in the graph: one leaked per answer without this
        lipSource?.disconnect();

        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        if (this.activeFallbackAudio === audio) {
          this.activeFallbackAudio = null;
        }
        if (blobUrl.startsWith("blob:")) {
          try {
            URL.revokeObjectURL(blobUrl);
          } catch (_) {}
        }
        resolve(completed);
      };
      const interrupt = () => cleanup(false);
      this.interruptActive = interrupt;

      const onEnded = () => cleanup();
      const onError = (e: any) => {
        console.warn("[Live2D] Audio playback error:", e);
        cleanup();
      };

      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise
          .catch((err) => {
            console.warn("[Live2D] Autoplay prevented, waiting for user gesture:", err);
            const unlockAndPlay = () => {
              window.removeEventListener("pointerdown", unlockAndPlay);
              window.removeEventListener("keydown", unlockAndPlay);
              audio.play().catch(() => cleanup());
            };

            window.addEventListener("pointerdown", unlockAndPlay, { once: true });
            window.addEventListener("keydown", unlockAndPlay, { once: true });

            window.setTimeout(() => {
              window.removeEventListener("pointerdown", unlockAndPlay);
              window.removeEventListener("keydown", unlockAndPlay);
              if (audio.paused && !finished) {
                cleanup();
              }
            }, 8000);
          });
      }
    });
  }

  stopSpeaking(): void {
    this.isSpeakingActive = false; // the mouth eases closed in animateMouth()
    this.motion.mouthForm = 0;
    this.interruptActive?.();
    if (this.activeFallbackAudio) {
      try {
        this.activeFallbackAudio.pause();
        this.activeFallbackAudio = null;
      } catch (_) {}
    }
  }

  destroy(): void {
    this.stopSpeaking();
    this.stopTicker();
    if (this.model) {
      this.model.destroy();
      this.model = null;
    }
    if (this.app) {
      this.app.destroy(true, { children: true, texture: true, baseTexture: true });
      this.app = null;
    }
    this.isModelReady = false;
  }
}

export const live2d: Live2DManager = new Live2DManagerImpl();
