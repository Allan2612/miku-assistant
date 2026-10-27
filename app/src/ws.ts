/**
 * Miku Assistant - WebSocket Client
 * Native browser/WebView2 WebSocket with automatic exponential backoff reconnection.
 */

export type ServerMessage =
  | { type: "show"; sent_at?: number }
  | { type: "hide" }
  | { type: "state"; value: "idle" | "listening" | "thinking" | "speaking" }
  | { type: "subtitle"; who: "user" | "miku"; text: string }
  | { type: "expression"; name: string }
  | { type: "stop_speaking" }
  | {
      type: "speak";
      audio_b64: string;
      mime: string;
      text: string;
      emotion: string;
      words?: [number, number][]; // [start_ms, end_ms] of each word in the audio
      farewell?: boolean;
      gesture?: string; // "attention" (reminder), "greet"
      outcome?: "ok" | "fail"; // how the actions of this turn went
    }
  | { type: "user_speech" } // the user started talking
  | { type: "confirm_request"; id: string; text: string };

export type MessageHandler = (msg: ServerMessage) => void;

const KNOWN_TYPES = new Set<string>([
  "show", "hide", "state", "subtitle", "expression", "stop_speaking", "speak", "user_speech", "confirm_request",
]);

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string = "ws://127.0.0.1:8765";
  private handlers: Set<MessageHandler> = new Set();
  private reconnectTimeout: number | null = null;
  private retryDelay: number = 1000;
  private maxRetryDelay: number = 10000;
  public isConnected: boolean = false;
  private isExplicitlyClosed: boolean = false;

  constructor(url?: string) {
    if (url) this.url = url;
  }

  public onMessage(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  public connect(url?: string): void {
    if (url) this.url = url;
    this.isExplicitlyClosed = false;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    // Never keep two sockets: the old one's onclose would schedule yet another reconnect (H-022)
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log(`[WS] Connected to Miku Core at ${this.url}`);
        this.isConnected = true;
        this.retryDelay = 1000;

        // Send ready event
        this.send({ type: "ready" });
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
          if (!msg || typeof msg !== "object" || !KNOWN_TYPES.has(msg.type)) {
            console.warn("[WS] Ignoring unknown message:", event.data);
            return;
          }
          for (const handler of this.handlers) {
            handler(msg);
          }
        } catch (err) {
          console.warn("[WS] Error parsing message:", event.data, err);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        if (!this.isExplicitlyClosed) {
          console.log(`[WS] Connection closed. Retrying in ${this.retryDelay / 1000}s...`);
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (err) => {
        console.warn("[WS] Connection error:", err);
      };
    } catch (err) {
      console.warn("[WS] Could not initialize WebSocket:", err);
      if (!this.isExplicitlyClosed) {
        this.scheduleReconnect();
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout || this.isExplicitlyClosed) return;
    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.retryDelay = Math.min(this.retryDelay * 1.5, this.maxRetryDelay);
      this.connect();
    }, this.retryDelay);
  }

  public send(data: unknown): void {
    const payload = JSON.stringify(data);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(payload);
    } else {
      // Messages are not queued: an "activate" from minutes ago must not fire when the
      // backend comes back (H-022). "ready" is sent again on every (re)connect anyway.
      console.warn("[WS] Not connected, dropping message:", payload);
    }
  }

  public sendTextInput(text: string): void {
    this.send({ type: "text_input", text });
  }

  public sendActivate(): void {
    this.send({ type: "activate" });
  }

  public sendDismiss(): void {
    this.send({ type: "dismiss" });
  }

  public disconnect(): void {
    this.isExplicitlyClosed = true;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected = false;
  }
}

export const ws = new WebSocketClient();

