/**
 * Miku Assistant - UI Overlays
 * Speech bubble subtitles and listening waves (pure vanilla HTML/CSS, zero dependencies).
 * Pure voice companion mode: no buttons or input bars on screen for a clean, distraction-free aesthetic.
 */

export interface UIManager {
  init(container: HTMLElement): void;
  showSubtitle(who: "user" | "miku", text: string, durationMs?: number): void;
  showThinking(): void;
  showListening(): void;
  clearStatus(): void;
  clearSubtitle(): void;
}

class UIManagerImpl implements UIManager {
  private bubbleEl: HTMLDivElement | null = null;
  private subtitleTimer: number | null = null;

  public init(container: HTMLElement): void {
    // Create Speech Bubble Element for subtitles and feedback
    const bubble = document.createElement("div");
    bubble.className = "miku-speech-bubble hidden";
    bubble.id = "speech-bubble";
    bubble.innerHTML = `
      <div class="bubble-speaker" id="bubble-speaker">Miku</div>
      <div class="bubble-content" id="bubble-text"></div>
    `;
    bubble.addEventListener("click", () => {
      this.clearSubtitle();
    });
    container.appendChild(bubble);
    this.bubbleEl = bubble;
  }

  public showSubtitle(who: "user" | "miku", text: string, durationMs: number = 6000): void {
    if (!this.bubbleEl) return;

    if (this.subtitleTimer) {
      clearTimeout(this.subtitleTimer);
      this.subtitleTimer = null;
    }

    const speakerEl = this.bubbleEl.querySelector<HTMLDivElement>("#bubble-speaker");
    const textEl = this.bubbleEl.querySelector<HTMLDivElement>("#bubble-text");

    if (speakerEl) {
      speakerEl.textContent = who === "miku" ? "Miku" : "Tú";
      speakerEl.className = `bubble-speaker ${who}`;
    }

    if (textEl) {
      textEl.textContent = text;
    }

    this.bubbleEl.classList.remove("hidden", "thinking", "listening", "user", "miku");
    this.bubbleEl.classList.add("visible", who);

    if (durationMs > 0) {
      this.subtitleTimer = window.setTimeout(() => {
        this.clearSubtitle();
      }, durationMs);
    }
  }

  public showThinking(): void {
    if (!this.bubbleEl) return;
    if (this.subtitleTimer) {
      clearTimeout(this.subtitleTimer);
      this.subtitleTimer = null;
    }

    const speakerEl = this.bubbleEl.querySelector<HTMLDivElement>("#bubble-speaker");
    const textEl = this.bubbleEl.querySelector<HTMLDivElement>("#bubble-text");

    if (speakerEl) {
      speakerEl.textContent = "Miku";
      speakerEl.className = "bubble-speaker miku";
    }

    if (textEl) {
      textEl.innerHTML = `<span class="thinking-dots">Pensando<span>.</span><span>.</span><span>.</span></span>`;
    }

    this.bubbleEl.classList.remove("hidden", "user", "listening");
    this.bubbleEl.classList.add("visible", "miku", "thinking");
  }

  public showListening(): void {
    if (!this.bubbleEl) return;
    if (this.subtitleTimer) {
      clearTimeout(this.subtitleTimer);
      this.subtitleTimer = null;
    }

    const speakerEl = this.bubbleEl.querySelector<HTMLDivElement>("#bubble-speaker");
    const textEl = this.bubbleEl.querySelector<HTMLDivElement>("#bubble-text");

    if (speakerEl) {
      speakerEl.textContent = "Miku";
      speakerEl.className = "bubble-speaker miku";
    }

    if (textEl) {
      textEl.innerHTML = `
        <span class="listening-indicator">
          <span class="mic-wave">
            <span></span><span></span><span></span><span></span><span></span>
          </span>
          Escuchando...
        </span>
      `;
    }

    this.bubbleEl.classList.remove("hidden", "user", "thinking");
    this.bubbleEl.classList.add("visible", "miku", "listening");
  }

  /** Back to idle: drop "Escuchando..." / "Pensando..." (the mic is closed), but keep an answer's subtitle. */
  public clearStatus(): void {
    if (this.bubbleEl?.classList.contains("listening") || this.bubbleEl?.classList.contains("thinking")) {
      this.clearSubtitle();
    }
  }

  public clearSubtitle(): void {
    if (this.bubbleEl) {
      this.bubbleEl.classList.remove("visible", "thinking", "listening");
      this.bubbleEl.classList.add("hidden");
    }
  }
}

export const ui: UIManager = new UIManagerImpl();
