/**
 * Live2D model loader and PixiJS management.
 * Optimized for low resource usage: stopped ticker when hidden, 30 FPS cap when visible.
 * Configured with safe-framing bounds so hair twin-tails and body are never clipped.
 */

import * as PIXI from "pixi.js";
import { Live2DModel } from "pixi-live2d-display-lipsyncpatch/cubism4";

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
  init(canvas: HTMLCanvasElement, width: number, height: number, fps?: number): Promise<void>;
  loadModel(modelPath: string, scale?: number): Promise<Live2DModel>;
  setExpression(name: string): boolean;
  onTapReaction(): void;
  focus(x: number, y: number): void;
  startTicker(): void;
  stopTicker(): void;
  startIdleGestures(): void;
  stopIdleGestures(): void;
  hitTest(clientX: number, clientY: number): boolean;
  /** Resolves true when playback ended (or failed), false when interrupted by stopSpeaking(). */
  speak(audioB64: string, mime?: string): Promise<boolean>;
  stopSpeaking(): void;
  destroy(): void;
}

class Live2DManagerImpl implements Live2DManager {
  app: PIXI.Application | null = null;
  model: Live2DModel | null = null;
  canvas: HTMLCanvasElement | null = null;
  isModelReady: boolean = false;
  private activeFallbackAudio: HTMLAudioElement | null = null;
  // Cleanup of the playing audio; stopSpeaking() must run it or the lip-sync interval leaks (H-045)
  private interruptActive: (() => void) | null = null;
  private idleGestureTimer: number | null = null;
  private isSpeakingActive: boolean = false;

  // --- Smooth parameter animation ---------------------------------------------------------
  // Gestures used to set parameters once, instantly, outside the model update: they jumped,
  // and the next frame's motion overwrote them. Now every gesture only sets a *target*; each
  // frame (beforeModelUpdate) the value eases towards it and is ADDED on top of the idle
  // motion, so Miku keeps breathing/blinking while she smiles or tilts her head.
  private targets: Record<string, number> = {};
  private current: Record<string, number> = {};
  private lastFrameMs = 0;
  // Lip sync from the real audio level (was random values every 60 ms)
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private analyserBuf: Float32Array<ArrayBuffer> | null = null;
  private mouth = 0;
  private lipSyncFromAudio = false;
  private gestureResetTimers: number[] = [];

  /** Ease a parameter offset towards `value` (0 = back to the motion's own value). */
  private setTarget(id: string, value: number): void {
    this.targets[id] = value;
  }

  private setTargets(values: Record<string, number>): void {
    for (const [id, v] of Object.entries(values)) this.setTarget(id, v);
  }

  /** Sets targets now and eases them back to 0 after `holdMs`. */
  private pulse(values: Record<string, number>, holdMs: number): void {
    this.setTargets(values);
    const t = window.setTimeout(() => {
      for (const id of Object.keys(values)) this.setTarget(id, 0);
    }, holdMs);
    this.gestureResetTimers.push(t);
    if (this.gestureResetTimers.length > 20) this.gestureResetTimers.shift();
  }

  /** Runs every frame right before the model is drawn, after motions/physics. */
  private animateParams(core: any): void {
    const now = performance.now();
    const dt = this.lastFrameMs ? Math.min(0.1, (now - this.lastFrameMs) / 1000) : 1 / 30;
    this.lastFrameMs = now;

    // Exponential easing: frame-rate independent, ~0.25 s to settle most of the way
    const k = 1 - Math.exp(-dt / 0.18);
    for (const id of Object.keys(this.targets)) {
      const cur = this.current[id] ?? 0;
      const next = cur + (this.targets[id] - cur) * k;
      this.current[id] = next;
      if (Math.abs(next) > 0.0005) {
        try {
          core.addParameterValueById(id, next);
        } catch (_) {}
      } else if (this.targets[id] === 0) {
        delete this.targets[id];
        delete this.current[id];
      }
    }

    // Mouth: fast to open, a bit slower to close, like real speech
    let level = 0;
    if (this.isSpeakingActive && this.lipSyncFromAudio && this.analyser && this.analyserBuf) {
      this.analyser.getFloatTimeDomainData(this.analyserBuf);
      let sum = 0;
      for (const s of this.analyserBuf) sum += s * s;
      level = Math.min(1, Math.sqrt(sum / this.analyserBuf.length) * 6);
    } else if (this.isSpeakingActive && this.activeFallbackAudio && !this.activeFallbackAudio.paused) {
      // No analyser: soft syllable-like rhythm (two mixed rates, never fully random jumps)
      const t = now / 1000;
      level = 0.25 + 0.3 * Math.abs(Math.sin(t * 9.0)) * (0.6 + 0.4 * Math.sin(t * 2.3));
    }
    const km = 1 - Math.exp(-dt / (level > this.mouth ? 0.035 : 0.09));
    this.mouth += (level - this.mouth) * km;
    if (this.isSpeakingActive || this.mouth > 0.01) {
      try {
        core.setParameterValueById("ParamMouthOpenY", this.mouth);
      } catch (_) {}
    }
  }

  /** Routes an <audio> element through an analyser so the mouth follows its volume.
   *  Returns false when it could not (the audio then plays directly, with a fallback rhythm). */
  private connectLipSync(audio: HTMLAudioElement): boolean {
    try {
      this.audioCtx ??= new AudioContext();
      if (this.audioCtx.state !== "running") {
        // Routing audio through a suspended context would play it SILENTLY: play it directly
        // this time (fallback mouth rhythm) and try to wake the context for the next phrase
        void this.audioCtx.resume();
        return false;
      }
      if (!this.analyser) {
        this.analyser = this.audioCtx.createAnalyser();
        this.analyser.fftSize = 1024;
        this.analyser.connect(this.audioCtx.destination);
        this.analyserBuf = new Float32Array(this.analyser.fftSize);
      }
      this.audioCtx.createMediaElementSource(audio).connect(this.analyser);
      return true;
    } catch (err) {
      // Audio still plays directly, with the fallback mouth rhythm
      console.warn("[Live2D] Lip sync analyser unavailable:", err);
      return false;
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

      // Parameter sanitization
      const core = (model.internalModel as any)?.coreModel;
      const sanitizeParams = () => {
        if (!core) return;
        try {
          core.setParameterValueById("Watermark", 0);
          core.setParameterValueById("HideDefault", 0);
          core.setParameterValueById("PinkPaint", 0);
          core.setParameterValueById("UniformMagicEyes", 0);
          core.setParameterValueById("DeadEyes", 0);
          core.setParameterValueById("DeadEyes2", 0);
          core.setParameterValueById("dxyh", 0);
        } catch (_) {}
      };

      sanitizeParams();
      (model.internalModel as any)?.on("beforeModelUpdate", () => {
        sanitizeParams();
        if (core) this.animateParams(core);
      });

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

  /**
   * Cute interactive tap reaction (Fase 8)
   * Triggers a smile, cheek blush and plays a Tap motion when Miku is clicked.
   */
  onTapReaction(): void {
    if (!this.model || !this.isModelReady) return;

    // A click is a deliberate action: the model's own Tap motion fits here
    try {
      (this.model as any).motion?.("Tap");
    } catch (_) {}

    // Blush, smiling eyes and a small head tilt that ease in and back out
    this.pulse(
      { ParamCheek: 0.7, ParamEyeLSmile: 0.8, ParamEyeRSmile: 0.8, ParamAngleZ: (Math.random() < 0.5 ? -1 : 1) * 5 },
      2200
    );
  }

  setExpression(name: string): boolean {
    if (!this.model) return false;
    // Use the model's own expression only if it defines one with this name. expression()
    // is async and returns a Promise (always truthy), so the old "if (result) return" check
    // returned early every time and no expression was ever shown.
    const defs: any[] = (this.model.internalModel as any)?.motionManager?.expressionManager?.definitions ?? [];
    if (defs.some((d) => (d.Name ?? d.name) === name)) {
      void (this.model as any).expression(name);
      return true;
    }

    // Every expression sets ALL these offsets, so switching between them always blends
    // smoothly instead of leaving leftovers (e.g. raised brows after "surprised")
    const neutral: Record<string, number> = {
      ParamCheek: 0, ParamEyeLSmile: 0, ParamEyeRSmile: 0, ParamEyeLOpen: 0, ParamEyeROpen: 0,
      ParamBrowLY: 0, ParamBrowRY: 0, ParamBrowLAngle: 0, ParamBrowRAngle: 0,
      ParamAngleY: 0, ParamEyeBallY: 0,
    };
    const looks: Record<string, Record<string, number>> = {
      happy: { ParamCheek: 0.5, ParamEyeLSmile: 0.7, ParamEyeRSmile: 0.7, ParamBrowLY: 0.15, ParamBrowRY: 0.15 },
      thinking: { ParamBrowLY: 0.3, ParamBrowRY: -0.1, ParamEyeBallY: 0.35, ParamAngleY: 4 },
      surprised: { ParamEyeLOpen: 0.25, ParamEyeROpen: 0.25, ParamBrowLY: 0.45, ParamBrowRY: 0.45 },
      sad: { ParamBrowLAngle: -0.45, ParamBrowRAngle: -0.45, ParamBrowLY: -0.15, ParamBrowRY: -0.15, ParamAngleY: -5 },
      angry: { ParamBrowLAngle: 0.4, ParamBrowRAngle: 0.4, ParamBrowLY: -0.25, ParamBrowRY: -0.25 },
    };
    this.setTargets({ ...neutral, ...(looks[name] ?? {}) });
    return true;
  }

  focus(clientX?: number, clientY?: number): void {
    if (!this.model || !this.isModelReady || !this.canvas) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = typeof clientX === "number" ? clientX - rect.left : rect.width / 2;
    const y = typeof clientY === "number" ? clientY - rect.top : rect.height / 3;

    // model.focus() turns any point into a full-length direction, so even a cursor slightly
    // off-center made her look to the extreme (head roll up to 30°). Feed the focus controller
    // directly with a damped vector instead: up to half the range, eased by the controller.
    const b = this.model.getBounds();
    const faceX = b.x + b.width / 2;
    const faceY = b.y + b.height * 0.3;
    const clamp = (v: number) => Math.max(-1, Math.min(1, v));
    const nx = clamp(((x - faceX) / rect.width) * 1.5) * 0.5;
    const ny = clamp(((faceY - y) / rect.height) * 1.5) * 0.5;
    (this.model.internalModel as any).focusController?.focus(nx, ny);
  }

  startTicker(): void {
    if (this.app && !this.app.ticker.started) {
      this.app.ticker.start();
    }
    this.startIdleGestures();
  }

  stopTicker(): void {
    this.stopIdleGestures();
    if (this.app && this.app.ticker.started) {
      this.app.ticker.stop();
    }
  }

  startIdleGestures(): void {
    if (this.idleGestureTimer !== null) return;
    this.scheduleNextGesture();
  }

  stopIdleGestures(): void {
    if (this.idleGestureTimer !== null) {
      clearTimeout(this.idleGestureTimer);
      this.idleGestureTimer = null;
    }
    this.gestureResetTimers.forEach((t) => clearTimeout(t));
    this.gestureResetTimers = [];
    this.setTargets({ ParamAngleX: 0, ParamAngleZ: 0, ParamBodyAngleX: 0, ParamEyeBallX: 0 });
  }

  private scheduleNextGesture(): void {
    const delay = 5000 + Math.random() * 4000;
    this.idleGestureTimer = window.setTimeout(() => {
      this.triggerRandomGesture();
      if (this.idleGestureTimer !== null) {
        this.scheduleNextGesture();
      }
    }, delay);
  }

  /**
   * Small, slow idle gestures layered on the model's own idle motion (which keeps playing):
   * no extra motions are triggered, so nothing snaps or restarts.
   * Uses head/body/gaze params only, so it never cancels an expression's smile or brows.
   */
  private triggerRandomGesture(): void {
    if (!this.model || !this.isModelReady || this.isSpeakingActive) return;

    const side = Math.random() < 0.5 ? -1 : 1;
    const r = Math.random();
    if (r < 0.4) {
      // Gentle head tilt with a little body sway
      this.pulse({ ParamAngleZ: side * (3 + Math.random() * 3), ParamBodyAngleX: side * 2 }, 1800 + Math.random() * 1500);
    } else if (r < 0.75) {
      // Glance to one side, eyes first then a slight head turn
      this.pulse({ ParamEyeBallX: side * 0.5, ParamAngleX: side * 6 }, 900 + Math.random() * 900);
    } else {
      // Thoughtful look slightly up
      this.pulse({ ParamAngleY: 5, ParamEyeBallY: 0.3 }, 1500);
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

  speak(audioB64: string, mime: string = "audio/wav"): Promise<boolean> {
    if (!this.model) {
      return Promise.resolve(true);
    }

    this.stopSpeaking();
    this.isSpeakingActive = true;

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

      // The mouth is driven every frame by animateParams() from this audio's level
      this.lipSyncFromAudio = this.connectLipSync(audio);

      const cleanup = (completed: boolean = true) => {
        if (finished) return;
        finished = true;
        this.isSpeakingActive = false;
        if (this.interruptActive === interrupt) {
          this.interruptActive = null;
        }
        audio.pause();

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
    this.isSpeakingActive = false; // the mouth eases closed in animateParams()
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
