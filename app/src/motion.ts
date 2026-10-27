/**
 * Miku's procedural motion (docs/plan-expresiones.md). Layers summed every frame on top of the model's resting
 * values, in place of the model's random idle clips, so she never freezes and never repeats the same loop:
 *   - ambient: slow noise on head and body, plus a weight shift every 8-15 s
 *   - blink:   fast close, slower open, every 2-6 s, sometimes double, also on big glances
 *   - gaze:    small saccades around a focus point (you, or aside while thinking); the head follows the eyes
 *   - emotion: the face (brows, eyes, mouth, blush) and a posture bias, eased in and out
 *   - gestures: short choreographies with anticipation and settle (nod, bounce, wave, bow...)
 * The model's arms only swing out or in (ParamArmL/R): there are no hands, so there are no hand gestures.
 */

export type Params = Record<string, number>;
type Key = [number, number]; // [progress 0..1, value]

interface Gesture {
  duration: number; // seconds
  // Parameter offsets over time. "_y" moves the whole model (px at the default window size, down is positive)
  tracks: Record<string, Key[]>;
}

// Same keys on both sides: both("Eye*Smile", k) drives ParamEyeLSmile and ParamEyeRSmile
const both = (base: string, keys: Key[]): Record<string, Key[]> => ({
  [`Param${base.replace("*", "L")}`]: keys,
  [`Param${base.replace("*", "R")}`]: keys,
});
// The right arm a beat behind the left: perfect symmetry looks robotic
const arms = (keys: Key[], lag = 0.04): Record<string, Key[]> => ({
  ParamArmL: keys,
  ParamArmR: keys.map(([p, v]) => [Math.min(1, p === 0 || p === 1 ? p : p + lag), v] as Key),
});

export const GESTURES: Record<string, Gesture> = {
  nod: { duration: 0.55, tracks: { ParamAngleY: [[0, 0], [0.18, 2.5], [0.5, -10], [0.78, 1.5], [1, 0]] } },
  small_nod: { duration: 0.45, tracks: { ParamAngleY: [[0, 0], [0.45, -5], [1, 0]] } },
  beat: { duration: 0.32, tracks: { ParamAngleY: [[0, 0], [0.4, -3.5], [1, 0]] } },
  brow_flick: { duration: 0.5, tracks: both("Brow*Y", [[0, 0], [0.3, 0.35], [1, 0]]) },
  shake: { duration: 0.9, tracks: { ParamAngleX: [[0, 0], [0.18, -10], [0.42, 9], [0.66, -6], [0.85, 2], [1, 0]] } },
  tilt: {
    duration: 1.6,
    tracks: { ParamAngleZ: [[0, 0], [0.25, 10], [0.75, 10], [1, 0]], ParamAngleX: [[0, 0], [0.25, 4], [0.75, 4], [1, 0]] },
  },
  bounce: {
    duration: 0.8,
    tracks: {
      _y: [[0, 0], [0.18, 7], [0.42, -20], [0.65, 2], [0.82, -4], [1, 0]],
      ...arms([[0, 0], [0.3, 0.9], [0.7, 0.7], [1, 0]]),
      ParamAngleZ: [[0, 0], [0.4, -4], [1, 0]],
      ...both("Eye*Smile", [[0, 0], [0.25, 0.8], [0.8, 0.8], [1, 0]]),
    },
  },
  hop: { duration: 0.5, tracks: { _y: [[0, 0], [0.25, 6], [0.55, -16], [1, 0]] } },
  open_arms: {
    duration: 1.4,
    tracks: { ...arms([[0, 0], [0.25, 1], [0.75, 1], [1, 0]]), ParamAngleY: [[0, 0], [0.3, 4], [1, 0]] },
  },
  shrug: {
    duration: 1.3,
    tracks: {
      ...arms([[0, 0], [0.3, 0.55], [0.7, 0.55], [1, 0]], 0.06),
      ParamAngleZ: [[0, 0], [0.3, 8], [0.75, 8], [1, 0]],
      ParamBrowLY: [[0, 0], [0.3, 0.5], [0.75, 0.5], [1, 0]],
      ParamBrowRY: [[0, 0], [0.3, 0.2], [0.75, 0.2], [1, 0]],
      ParamMouthForm: [[0, 0], [0.3, -0.5], [0.75, -0.5], [1, 0]],
    },
  },
  bow: {
    duration: 1.5,
    tracks: {
      ParamAngleY: [[0, 0], [0.35, -16], [0.65, -16], [1, 0]],
      ParamBodyAngleY: [[0, 0], [0.35, -8], [0.65, -8], [1, 0]],
      _y: [[0, 0], [0.35, 10], [0.65, 10], [1, 0]],
      ...both("Eye*Smile", [[0, 0], [0.3, 1], [0.7, 1], [1, 0]]),
    },
  },
  // No hands on this model: an arm raised and swung, a sway and a smile is the closest to waving goodbye
  wave: {
    duration: 2.0,
    tracks: {
      ParamArmL: [[0, 0], [0.12, 1], [0.25, 0.55], [0.38, 1], [0.51, 0.55], [0.64, 1], [0.8, 0.8], [1, 0]],
      ParamAngleZ: [[0, 0], [0.15, -6], [0.35, -2], [0.55, -6], [0.75, -2], [1, 0]],
      ParamBodyAngleZ: [[0, 0], [0.2, -3], [0.8, -3], [1, 0]],
      ...both("Eye*Smile", [[0, 0], [0.15, 0.9], [0.85, 0.9], [1, 0]]),
      ParamMouthForm: [[0, 0], [0.15, 0.9], [0.85, 0.9], [1, 0]],
    },
  },
  attention: {
    duration: 1.0,
    tracks: {
      ...both("Brow*Y", [[0, 0], [0.2, 0.7], [0.7, 0.7], [1, 0]]),
      ...both("Eye*Open", [[0, 0], [0.2, 0.2], [0.7, 0.2], [1, 0]]),
      ...arms([[0, 0], [0.25, 0.5], [0.7, 0.5], [1, 0]]),
      _y: [[0, 0], [0.2, -8], [0.5, 0], [1, 0]],
      ParamAngleY: [[0, 0], [0.2, 6], [1, 0]],
    },
  },
  surprise: {
    duration: 0.9,
    tracks: {
      ...both("Eye*Open", [[0, 0], [0.12, 0.3], [0.6, 0.3], [1, 0]]),
      ...both("Brow*Y", [[0, 0], [0.12, 0.8], [0.6, 0.8], [1, 0]]),
      _y: [[0, 0], [0.15, -10], [0.4, 0], [1, 0]],
      ...arms([[0, 0], [0.15, 0.5], [0.6, 0.5], [1, 0]]),
    },
  },
  sigh: {
    duration: 1.8,
    tracks: {
      ParamAngleY: [[0, 0], [0.3, 4], [0.6, -8], [1, 0]],
      ...both("Eye*Open", [[0, 0], [0.35, -0.5], [0.75, -0.5], [1, 0]]),
      ...arms([[0, 0], [0.5, -0.4], [1, 0]]),
    },
  },
  giggle: {
    duration: 1.0,
    tracks: {
      ParamAngleZ: [[0, 0], [0.15, 4], [0.3, -3], [0.45, 4], [0.6, -3], [0.75, 2], [1, 0]],
      ...both("Eye*Smile", [[0, 0], [0.1, 1], [0.85, 1], [1, 0]]),
      ParamCheek: [[0, 0], [0.1, 0.8], [0.9, 0.8], [1, 0]],
      ...arms([[0, 0], [0.2, -0.5], [0.8, -0.5], [1, 0]]),
    },
  },
  look_around: {
    duration: 3.2,
    tracks: {
      ParamAngleX: [[0, 0], [0.2, -16], [0.45, -16], [0.65, 14], [0.85, 14], [1, 0]],
      ParamEyeBallX: [[0, 0], [0.15, -0.8], [0.45, -0.8], [0.6, 0.8], [0.85, 0.8], [1, 0]],
    },
  },
  stretch: {
    duration: 2.4,
    tracks: {
      ...arms([[0, 0], [0.3, 1], [0.7, 1], [1, 0]]),
      ParamAngleY: [[0, 0], [0.3, 10], [0.7, 10], [1, 0]],
      ...both("Eye*Open", [[0, 0], [0.3, -1], [0.7, -1], [1, 0]]),
      ParamBodyAngleY: [[0, 0], [0.35, 4], [0.7, 4], [1, 0]],
      _y: [[0, 0], [0.35, -6], [0.7, -6], [1, 0]],
    },
  },
  hum: {
    duration: 2.8,
    tracks: {
      ParamAngleZ: [[0, 0], [0.12, 5], [0.25, -5], [0.37, 5], [0.5, -5], [0.62, 5], [0.75, -5], [0.87, 3], [1, 0]],
      ParamBodyAngleZ: [[0, 0], [0.25, 2], [0.5, -2], [0.75, 2], [1, 0]],
      ...both("Eye*Smile", [[0, 0], [0.1, 0.7], [0.9, 0.7], [1, 0]]),
      ParamMouthForm: [[0, 0], [0.1, 0.6], [0.9, 0.6], [1, 0]],
    },
  },
  enter: {
    duration: 0.9,
    tracks: {
      _y: [[0, 60], [0.55, -8], [0.8, 2], [1, 0]],
      ParamAngleY: [[0, -6], [0.6, 3], [1, 0]],
      ...arms([[0, -0.3], [0.6, 0.4], [1, 0]]),
      ...both("Eye*Smile", [[0, 0], [0.5, 0.6], [1, 0]]),
    },
  },
  exit: {
    duration: 0.7,
    tracks: {
      _y: [[0, 0], [0.3, -6], [1, 70]],
      ParamAngleY: [[0, 0], [0.35, -10], [1, -10]],
      ...both("Eye*Smile", [[0, 0], [0.3, 1], [1, 1]]),
    },
  },
};

// Faces, as offsets from the model's resting values; a few carry a posture (arms in, head down)
export const EMOTIONS: Record<string, Params> = {
  neutral: {},
  happy: { ParamEyeLSmile: 0.6, ParamEyeRSmile: 0.6, ParamCheek: 0.4, ParamMouthForm: 0.8, ParamBrowLY: 0.2, ParamBrowRY: 0.2 },
  thinking: {
    ParamBrowLY: 0.35, ParamBrowRY: -0.05, ParamBrowLAngle: 0.2, ParamMouthForm: -0.2, ParamArmL: -0.7, ParamArmR: -0.7,
    ParamAngleY: 3,
  },
  surprised: { ParamEyeLOpen: 0.25, ParamEyeROpen: 0.25, ParamBrowLY: 0.6, ParamBrowRY: 0.6, ParamArmL: 0.25, ParamArmR: 0.25 },
  sad: {
    ParamBrowLAngle: -0.6, ParamBrowRAngle: -0.6, ParamBrowLY: -0.25, ParamBrowRY: -0.25, ParamMouthForm: -0.6,
    ParamEyeLOpen: -0.2, ParamEyeROpen: -0.2, ParamArmL: -0.6, ParamArmR: -0.6, ParamAngleY: -6,
  },
  angry: {
    ParamBrowLAngle: 0.5, ParamBrowRAngle: 0.5, ParamBrowLY: -0.35, ParamBrowRY: -0.35, ParamMouthForm: -0.5,
    ParamEyeLOpen: -0.1, ParamEyeROpen: -0.1,
  },
  shy: {
    ParamCheek: 1, ParamEyeLSmile: 0.3, ParamEyeRSmile: 0.3, ParamMouthForm: 0.3, ParamArmL: -0.8, ParamArmR: -0.8,
    ParamEyeLOpen: -0.15, ParamEyeROpen: -0.15, ParamAngleY: -5,
  },
  excited: {
    ParamEyeLOpen: 0.15, ParamEyeROpen: 0.15, ParamEyeLSmile: 0.3, ParamEyeRSmile: 0.3, ParamCheek: 0.5,
    ParamMouthForm: 1, ParamBrowLY: 0.45, ParamBrowRY: 0.45, ParamArmL: 0.5, ParamArmR: 0.5,
  },
  confused: { ParamBrowLY: 0.5, ParamBrowRY: -0.3, ParamBrowLAngle: 0.3, ParamBrowRAngle: -0.3, ParamMouthForm: -0.3, ParamAngleZ: 7 },
  proud: { ParamEyeLSmile: 0.5, ParamEyeRSmile: 0.5, ParamMouthForm: 0.7, ParamBrowLY: 0.3, ParamBrowRY: 0.3, ParamCheek: 0.2, ParamAngleY: 6 },
  playful: { ParamEyeROpen: -1, ParamEyeLSmile: 0.6, ParamMouthForm: 0.9, ParamCheek: 0.3, ParamAngleZ: 6 },
  tired: {
    ParamEyeLOpen: -0.45, ParamEyeROpen: -0.45, ParamBrowLY: -0.2, ParamBrowRY: -0.2, ParamMouthForm: -0.1,
    ParamArmL: -0.5, ParamArmR: -0.5, ParamAngleY: -4,
  },
};

// Every parameter the engine drives: set as resting value + offset every frame, so nothing accumulates
export const OWNED = [
  "ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ",
  "ParamEyeLOpen", "ParamEyeROpen", "ParamEyeLSmile", "ParamEyeRSmile", "ParamEyeBallX", "ParamEyeBallY",
  "ParamBrowLY", "ParamBrowRY", "ParamBrowLAngle", "ParamBrowRAngle", "ParamBrowLForm", "ParamBrowRForm",
  "ParamMouthForm", "ParamCheek", "ParamArmL", "ParamArmR",
];

// This model's defaults are not a resting pose (left arm out, right arm in, widest smile): these replace them.
// Arms go from -1 (against the body) to 1 (out); arm offsets are scaled so 1 means fully out from rest.
export const REST: Params = { ParamArmL: -0.8, ParamArmR: -0.8, ParamMouthForm: 0.5 };
export const GAIN: Params = { ParamArmL: 1.8, ParamArmR: 1.8 };

// A gesture played mirrored: sideways angles flip sign, left and right parts swap
const MIRROR_FLIP = new Set(["ParamAngleX", "ParamAngleZ", "ParamEyeBallX", "ParamBodyAngleX", "ParamBodyAngleZ"]);
const mirrorId = (id: string) =>
  id.replace(/(Arm|Brow|Eye)L/, "$1#").replace(/(Arm|Brow|Eye)R/, "$1L").replace(/(Arm|Brow|Eye)#/, "$1R");

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const ease = (cur: number, target: number, dt: number, tau: number) => cur + (target - cur) * (1 - Math.exp(-dt / tau));
const smooth = (t: number) => t * t * (3 - 2 * t);

function sample(keys: Key[], p: number): number {
  if (p <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    const [t1, v1] = keys[i];
    if (p <= t1) {
      const [t0, v0] = keys[i - 1];
      return v0 + (v1 - v0) * smooth((p - t0) / Math.max(1e-6, t1 - t0));
    }
  }
  return keys[keys.length - 1][1];
}

interface Playing {
  name: string;
  start: number;
  scale: number;
  mirror: boolean;
}

export interface Frame {
  params: Params; // offsets for OWNED parameters
  blink: number; // 0 = eyes as they are, 1 = closed
  y: number; // whole-model offset in px at the default window size
}

export class MotionEngine {
  private t = 0;
  private playing: Playing[] = [];
  private emotionTarget: Params = {};
  private face: Params = {};
  // gaze
  private focusX = 0;
  private focusY = 0;
  private eyeX = 0;
  private eyeY = 0;
  private gazeX = 0;
  private gazeY = 0;
  private headX = 0;
  private headY = 0;
  private nextSaccade = 0;
  // blink
  private blinkAt = -1;
  private nextBlink = rand(1.5, 4);
  private secondBlink = -1;
  // ambient
  private phase = Array.from({ length: 10 }, () => Math.random() * 100);
  private shiftX = 0;
  private shiftZ = 0;
  private shiftTargetX = 0;
  private shiftTargetZ = 0;
  private nextShift = rand(6, 10);
  /** Ambient liveliness: 1 normal, more while speaking, less when tired. */
  energy = 1;
  /** Mouth shape offset per word, set by the lip sync. */
  mouthForm = 0;
  private mouthNow = 0;

  setEmotion(name: string): void {
    this.emotionTarget = EMOTIONS[name] ?? {};
  }

  /** Where she means to look: (0, 0) is you; x right, y up, about -1..1. */
  setFocus(x: number, y: number): void {
    this.focusX = x;
    this.focusY = y;
    this.nextSaccade = 0; // look there now
  }

  play(name: string, opts: { scale?: number; mirror?: boolean } = {}): void {
    if (!GESTURES[name]) return;
    this.playing = this.playing.filter((g) => g.name !== name); // replaying restarts it
    this.playing.push({ name, start: this.t, scale: opts.scale ?? 1, mirror: opts.mirror ?? false });
  }

  isPlaying(name: string): boolean {
    return this.playing.some((g) => g.name === name);
  }

  blink(double = false): void {
    if (this.blinkAt < 0) this.blinkAt = this.t;
    if (double) this.secondBlink = this.t + 0.24;
  }

  update(dt: number): Frame {
    this.t += dt;
    const t = this.t;
    const p: Params = {};
    const add = (id: string, v: number) => {
      p[id] = (p[id] ?? 0) + v;
    };

    // Ambient: three sines per channel with unrelated periods read as noise, never as a loop
    const noise = (i: number, speed = 1) => {
      const ph = this.phase[i];
      return (
        Math.sin(t * 0.31 * speed + ph) * 0.55 + Math.sin(t * 0.73 * speed + ph * 1.7) * 0.3 +
        Math.sin(t * 1.37 * speed + ph * 2.3) * 0.15
      );
    };
    const e = this.energy;
    if (t > this.nextShift) {
      this.shiftTargetX = rand(-2.5, 2.5);
      this.shiftTargetZ = rand(-3, 3);
      this.nextShift = t + rand(8, 15);
    }
    this.shiftX = ease(this.shiftX, this.shiftTargetX, dt, 1.4);
    this.shiftZ = ease(this.shiftZ, this.shiftTargetZ, dt, 1.4);
    add("ParamAngleX", noise(0) * 2.5 * e);
    add("ParamAngleY", noise(1) * 1.8 * e);
    add("ParamAngleZ", noise(2) * 2.5 * e);
    add("ParamBodyAngleX", noise(3, 0.7) * 1.2 * e + this.shiftX);
    add("ParamBodyAngleZ", noise(4, 0.7) * 1.0 * e + this.shiftZ);

    // Gaze: saccades (quick jumps, then still) around the focus point; the head follows the eyes, slower
    if (t >= this.nextSaccade) {
      const nx = this.focusX + rand(-0.12, 0.12);
      const ny = this.focusY + rand(-0.08, 0.08);
      if (Math.hypot(nx - this.gazeX, ny - this.gazeY) > 0.3 && Math.random() < 0.4) this.blink();
      this.gazeX = nx;
      this.gazeY = ny;
      this.nextSaccade = t + rand(0.6, 2.4);
    }
    this.eyeX = ease(this.eyeX, this.gazeX, dt, 0.045);
    this.eyeY = ease(this.eyeY, this.gazeY, dt, 0.045);
    this.headX = ease(this.headX, this.eyeX * 0.7, dt, 0.35);
    this.headY = ease(this.headY, this.eyeY * 0.7, dt, 0.35);
    add("ParamEyeBallX", this.eyeX);
    add("ParamEyeBallY", this.eyeY);
    add("ParamAngleX", this.headX * 14);
    add("ParamAngleY", this.headY * 10);
    add("ParamBodyAngleX", this.headX * 3);

    // Emotion, eased (~0.3 s): every face param moves to its new value, so faces never leave leftovers
    for (const id of new Set([...Object.keys(this.face), ...Object.keys(this.emotionTarget)])) {
      this.face[id] = ease(this.face[id] ?? 0, this.emotionTarget[id] ?? 0, dt, 0.3);
      add(id, this.face[id]);
    }
    this.mouthNow = ease(this.mouthNow, this.mouthForm, dt, 0.08);
    add("ParamMouthForm", this.mouthNow);

    // Gestures
    let y = 0;
    this.playing = this.playing.filter((g) => t - g.start < GESTURES[g.name].duration);
    for (const g of this.playing) {
      const def = GESTURES[g.name];
      const prog = (t - g.start) / def.duration;
      for (const [id, keys] of Object.entries(def.tracks)) {
        let v = sample(keys, prog) * g.scale;
        if (id === "_y") {
          y += v;
          continue;
        }
        let target = id;
        if (g.mirror) {
          target = mirrorId(id);
          if (MIRROR_FLIP.has(id)) v = -v;
        }
        add(target, v);
      }
    }

    // Blink: close in 70 ms, hold 30 ms, open in 120 ms; every 2-6 s, sometimes twice in a row
    if (this.blinkAt < 0 && t >= this.nextBlink) {
      this.blink(Math.random() < 0.18);
      this.nextBlink = t + rand(2, 6);
    }
    if (this.blinkAt < 0 && this.secondBlink > 0 && t >= this.secondBlink) {
      this.blinkAt = t;
      this.secondBlink = -1;
    }
    let blink = 0;
    if (this.blinkAt >= 0) {
      const b = t - this.blinkAt;
      blink = b < 0.07 ? smooth(b / 0.07) : b < 0.1 ? 1 : b < 0.22 ? 1 - smooth((b - 0.1) / 0.12) : 0;
      if (b >= 0.22) this.blinkAt = -1;
    }
    return { params: p, blink, y };
  }
}
