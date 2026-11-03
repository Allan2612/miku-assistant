/**
 * The panel's background music: the user's own song (no Miku songs ship: copyright), looped quietly, and the
 * Inicio equalizer dancing to it. Off by default; paused while the panel is hidden.
 */

import { invoke } from "@tauri-apps/api/core";

let audio: HTMLAudioElement | null = null;
let analyser: AnalyserNode | null = null;
let bins: Uint8Array<ArrayBuffer> | null = null;
let frame = 0;
let wanted = localStorage.getItem("miku-music") === "1";

export const musicWanted = () => wanted;
export const musicPlaying = () => !!audio && !audio.paused;

async function load(): Promise<HTMLAudioElement> {
  if (audio) return audio;
  const bytes = await invoke<ArrayBuffer>("panel_music"); // throws a message when there is no song
  audio = new Audio(URL.createObjectURL(new Blob([bytes])));
  audio.loop = true;
  audio.volume = 0.3;
  const ctx = new AudioContext();
  analyser = ctx.createAnalyser();
  analyser.fftSize = 64;
  bins = new Uint8Array(analyser.frequencyBinCount);
  ctx.createMediaElementSource(audio).connect(analyser);
  analyser.connect(ctx.destination);
  return audio;
}

/** On or off; resolves to an error message when there is no song yet. */
export async function toggleMusic(): Promise<string | null> {
  wanted = !wanted;
  localStorage.setItem("miku-music", wanted ? "1" : "0");
  if (!wanted) {
    audio?.pause();
    return null;
  }
  try {
    await (await load()).play();
    return null;
  } catch (err) {
    wanted = false;
    localStorage.setItem("miku-music", "0");
    return String(err);
  }
}

/** Resumes the song when the panel opens (if it was on); pauses it when the panel hides. */
export function followVisibility(): void {
  if (document.hidden) audio?.pause();
  else if (wanted) void load().then((a) => a.play()).catch(() => {});
}

/** Moves the equalizer's bars with the song while it plays (Inicio); its CSS animation is the fallback. */
export function driveEqualizer(): void {
  cancelAnimationFrame(frame);
  const step = () => {
    const eq = document.getElementById("eq");
    if (!eq) return; // left Inicio: stop
    if (musicPlaying() && analyser && bins) {
      analyser.getByteFrequencyData(bins);
      eq.classList.add("music");
      const bars = eq.children;
      for (let i = 0; i < bars.length; i++) {
        const v = bins[Math.floor((i / bars.length) * bins.length * 0.8)] / 255;
        (bars[i] as HTMLElement).style.transform = `scaleY(${(0.12 + v * 0.88).toFixed(3)})`;
      }
    } else if (eq.classList.contains("music")) {
      eq.classList.remove("music");
      for (const bar of Array.from(eq.children)) (bar as HTMLElement).style.transform = "";
    }
    frame = requestAnimationFrame(step);
  };
  frame = requestAnimationFrame(step);
}
