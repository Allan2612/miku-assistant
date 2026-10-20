/**
 * Hand-crafted appear/disappear animations and particle sparkles.
 * Complies with docs/architecture.md: no tween libraries, <= 20 temporary particles, auto-cleanup.
 */

// Easing functions
function easeOutBack(x: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
}

function easeInBack(x: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return c3 * x * x * x - c1 * x * x;
}

function easeOutQuad(x: number): number {
  return 1 - (1 - x) * (1 - x);
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  color: string;
}

export class AnimationManager {
  private _isAnimating: boolean = false;

  get isAnimating(): boolean {
    return this._isAnimating;
  }

  /**
   * Appear animation (~240 ms):
   * Instant fade-in + crisp pop from bottom (20px) + snappy bounce scale (0.94 -> 1.0).
   */
  async appear(element: HTMLElement, durationMs: number = 240): Promise<void> {
    if (this._isAnimating) return;
    this._isAnimating = true;

    element.style.display = "flex";
    element.style.opacity = "0";

    const particles = this.createSparkleCanvas(element);
    const startTime = performance.now();

    return new Promise((resolve) => {
      const step = (currentTime: number) => {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / durationMs, 1);

        // Fast alpha fade-in (fully opaque by 35% of duration, ~80ms)
        const alpha = Math.min(progress * 2.8, 1);
        element.style.opacity = alpha.toFixed(3);

        // Translate up from 20px below to 0
        const translateY = (1 - easeOutQuad(progress)) * 20;

        // Bounce scale: 0.94 -> 1.0 with subtle spring
        const scaleProgress = easeOutBack(progress);
        const scale = 0.94 + (1.0 - 0.94) * scaleProgress;

        element.style.transform = `translateY(${translateY.toFixed(1)}px) scale(${scale.toFixed(3)})`;

        // Update sparkle particles
        this.renderSparkles(particles, progress);

        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          element.style.transform = "none";
          element.style.opacity = "1";
          this.removeSparkleCanvas(element);
          this._isAnimating = false;
          resolve();
        }
      };

      requestAnimationFrame(step);
    });
  }

  /**
   * Disappear animation (~220 ms):
   * Quick shrink and fade out.
   */
  async disappear(element: HTMLElement, durationMs: number = 220): Promise<void> {
    if (this._isAnimating) return;
    this._isAnimating = true;

    const particles = this.createSparkleCanvas(element);
    const startTime = performance.now();

    return new Promise((resolve) => {
      const step = (currentTime: number) => {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / durationMs, 1);

        // Fast fade out
        const alpha = Math.max(1 - progress * 1.5, 0);
        element.style.opacity = alpha.toFixed(3);

        // Small upward bounce
        const translateY = -10 * Math.sin(progress * Math.PI);

        // Scale down with ease-in
        const scaleProgress = easeInBack(progress);
        const scale = Math.max(1.0 - scaleProgress, 0);

        element.style.transform = `translateY(${translateY.toFixed(1)}px) scale(${scale.toFixed(3)})`;

        // Update sparkle particles
        this.renderSparkles(particles, progress);

        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          element.style.display = "none";
          element.style.opacity = "0";
          element.style.transform = "none";
          this.removeSparkleCanvas(element);
          this._isAnimating = false;
          resolve();
        }
      };

      requestAnimationFrame(step);
    });
  }

  private createSparkleCanvas(parent: HTMLElement): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; list: Particle[] } | null {
    const canvas = document.createElement("canvas");
    canvas.id = "sparkle-canvas";
    canvas.width = parent.clientWidth || 400;
    canvas.height = parent.clientHeight || 600;
    canvas.style.position = "absolute";
    canvas.style.top = "0";
    canvas.style.left = "0";
    canvas.style.pointerEvents = "none";
    canvas.style.zIndex = "10";
    parent.appendChild(canvas);

    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    // Up to 18 lightweight particles
    const list: Particle[] = [];
    const colors = ["#39c5bb", "#ffffff", "#86e3ce", "#d0f4de"];
    const count = 16;
    const centerX = canvas.width / 2;
    const centerY = canvas.height * 0.6;

    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5);
      const speed = 1.5 + Math.random() * 2.5;
      list.push({
        x: centerX + (Math.random() - 0.5) * 80,
        y: centerY + (Math.random() - 0.5) * 120,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 1.0,
        size: 2 + Math.random() * 3,
        alpha: 1.0,
        color: colors[i % colors.length],
      });
    }

    return { canvas, ctx, list };
  }

  private renderSparkles(
    data: { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; list: Particle[] } | null,
    progress: number
  ): void {
    if (!data) return;
    const { ctx, canvas, list } = data;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const fade = 1 - progress;
    for (const p of list) {
      p.x += p.vx;
      p.y += p.vy;
      p.alpha = fade;

      ctx.save();
      ctx.globalAlpha = Math.max(p.alpha, 0);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      // Draw 4-point star sparkle
      const r = p.size;
      ctx.moveTo(p.x, p.y - r);
      ctx.lineTo(p.x + r * 0.3, p.y - r * 0.3);
      ctx.lineTo(p.x + r, p.y);
      ctx.lineTo(p.x + r * 0.3, p.y + r * 0.3);
      ctx.lineTo(p.x, p.y + r);
      ctx.lineTo(p.x - r * 0.3, p.y + r * 0.3);
      ctx.lineTo(p.x - r, p.y);
      ctx.lineTo(p.x - r * 0.3, p.y - r * 0.3);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
  }

  private removeSparkleCanvas(parent: HTMLElement): void {
    const existing = parent.querySelector("#sparkle-canvas");
    if (existing) {
      existing.remove();
    }
  }
}

export const animations = new AnimationManager();
