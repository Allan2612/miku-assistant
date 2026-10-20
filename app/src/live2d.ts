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
  speak(audioB64: string, mime?: string): Promise<void>;
  stopSpeaking(): void;
  destroy(): void;
}

class Live2DManagerImpl implements Live2DManager {
  app: PIXI.Application | null = null;
  model: Live2DModel | null = null;
  canvas: HTMLCanvasElement | null = null;
  isModelReady: boolean = false;
  private activeFallbackAudio: HTMLAudioElement | null = null;
  private idleGestureTimer: number | null = null;
  private isSpeakingActive: boolean = false;

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
      const defaultScale = (scale > 0 && scale !== 0.25) ? scale : autoFitScale * 1.08;
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
      (model.internalModel as any)?.on("beforeModelUpdate", sanitizeParams);

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
        model.scale.x *= factor;
        model.scale.y *= factor;
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

    try {
      // 1. Play Tap motion (miku_02 or miku_03)
      (this.model as any).motion?.("Tap");
    } catch (_) {}

    try {
      const core = (this.model.internalModel as any)?.coreModel;
      if (core) {
        core.setParameterValueById("ParamCheek", 0.85);
        core.setParameterValueById("ParamEyeLSmile", 1.0);
        core.setParameterValueById("ParamEyeRSmile", 1.0);
        core.setParameterValueById("ParamAngleZ", (Math.random() - 0.5) * 6.0);

        // Gradually return to neutral after 2.5 seconds
        setTimeout(() => {
          if (!this.isSpeakingActive && core) {
            core.setParameterValueById("ParamCheek", 0);
            core.setParameterValueById("ParamEyeLSmile", 0);
            core.setParameterValueById("ParamEyeRSmile", 0);
            core.setParameterValueById("ParamAngleZ", 0);
          }
        }, 2500);
      }
    } catch (_) {}
  }

  setExpression(name: string): boolean {
    if (!this.model) return false;
    try {
      const expSuccess = (this.model as any).expression?.(name);
      if (expSuccess) return true;
    } catch (_) {}

    try {
      const core = (this.model.internalModel as any)?.coreModel;
      if (core) {
        if (name === "happy") {
          core.setParameterValueById("ParamCheek", 0.8);
          core.setParameterValueById("ParamEyeLSmile", 1.0);
          core.setParameterValueById("ParamEyeRSmile", 1.0);
          try { (this.model as any).motion?.("Tap"); } catch (_) {}
        } else if (name === "thinking") {
          core.setParameterValueById("ParamBrowLY", 0.4);
          core.setParameterValueById("ParamBrowRY", -0.2);
        } else if (name === "surprised") {
          core.setParameterValueById("ParamEyeLOpen", 1.2);
          core.setParameterValueById("ParamEyeROpen", 1.2);
          try { (this.model as any).motion?.("Flick"); } catch (_) {}
        } else if (name === "sad") {
          core.setParameterValueById("ParamBrowLAngle", -0.5);
          core.setParameterValueById("ParamBrowRAngle", -0.5);
        } else {
          // Neutral
          core.setParameterValueById("ParamCheek", 0);
          core.setParameterValueById("ParamEyeLSmile", 0);
          core.setParameterValueById("ParamEyeRSmile", 0);
          core.setParameterValueById("ParamBrowLY", 0);
          core.setParameterValueById("ParamBrowRY", 0);
          core.setParameterValueById("ParamBrowLAngle", 0);
          core.setParameterValueById("ParamBrowRAngle", 0);
        }
      }
      return true;
    } catch (err) {
      console.warn(`[Live2D] Could not set expression "${name}":`, err);
      return false;
    }
  }

  focus(clientX?: number, clientY?: number): void {
    if (!this.model || !this.isModelReady || !this.canvas) return;

    const rect = this.canvas.getBoundingClientRect();
    const x = typeof clientX === "number" ? clientX - rect.left : rect.width / 2;
    const y = typeof clientY === "number" ? clientY - rect.top : rect.height / 3;

    this.model.focus(x, y);
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
  }

  private scheduleNextGesture(): void {
    const delay = 4500 + Math.random() * 3500;
    this.idleGestureTimer = window.setTimeout(() => {
      this.triggerRandomGesture();
      if (this.idleGestureTimer !== null) {
        this.scheduleNextGesture();
      }
    }, delay);
  }

  private triggerRandomGesture(): void {
    if (!this.model || !this.isModelReady || this.isSpeakingActive) return;

    const rand = Math.random();
    if (rand < 0.6) {
      const groups = ["Idle", "Tap", "Idle"];
      const group = groups[Math.floor(Math.random() * groups.length)];
      try {
        (this.model as any).motion?.(group);
      } catch (_) {}
    } else {
      try {
        const core = (this.model.internalModel as any)?.coreModel;
        if (core) {
          const angleZ = (Math.random() - 0.5) * 8.0;
          const eyeX = (Math.random() - 0.5) * 0.5;
          const smile = Math.random() > 0.5 ? 0.3 : 0.0;
          core.setParameterValueById("ParamAngleZ", angleZ);
          core.setParameterValueById("ParamEyeBallX", eyeX);
          core.setParameterValueById("ParamEyeLSmile", smile);
          core.setParameterValueById("ParamEyeRSmile", smile);
        }
      } catch (_) {}
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

  speak(audioB64: string, mime: string = "audio/wav"): Promise<void> {
    if (!this.model) {
      return Promise.resolve();
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

    return new Promise<void>((resolve) => {
      let finished = false;
      const audio = new Audio(blobUrl);
      audio.volume = 1.0;
      audio.preload = "auto";
      this.activeFallbackAudio = audio;

      let lipSyncInterval: number | null = null;
      const core = (this.model?.internalModel as any)?.coreModel;

      const cleanup = () => {
        if (finished) return;
        finished = true;
        this.isSpeakingActive = false;

        if (lipSyncInterval !== null) {
          clearInterval(lipSyncInterval);
          lipSyncInterval = null;
        }
        try {
          core?.setParameterValueById("ParamMouthOpenY", 0);
        } catch (_) {}

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
        resolve();
      };

      const onEnded = () => cleanup();
      const onError = (e: any) => {
        console.warn("[Live2D] Audio playback error:", e);
        cleanup();
      };

      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);

      const startLipSync = () => {
        lipSyncInterval = window.setInterval(() => {
          if (!audio.paused && !audio.ended && core) {
            const mouthOpen = Math.random() > 0.15 ? 0.25 + Math.random() * 0.70 : 0.0;
            try {
              core.setParameterValueById("ParamMouthOpenY", mouthOpen);
            } catch (_) {}
          }
        }, 60);
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            startLipSync();
          })
          .catch((err) => {
            console.warn("[Live2D] Autoplay prevented, waiting for user gesture:", err);
            const unlockAndPlay = () => {
              window.removeEventListener("pointerdown", unlockAndPlay);
              window.removeEventListener("keydown", unlockAndPlay);
              audio.play().then(() => startLipSync()).catch(cleanup);
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
    this.isSpeakingActive = false;
    if (this.activeFallbackAudio) {
      try {
        this.activeFallbackAudio.pause();
        this.activeFallbackAudio = null;
      } catch (_) {}
    }
    const core = (this.model?.internalModel as any)?.coreModel;
    try {
      core?.setParameterValueById("ParamMouthOpenY", 0);
    } catch (_) {}
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
