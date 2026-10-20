/**
 * Miku Assistant - WebSocket Client
 * Native browser/WebView2 WebSocket with automatic exponential backoff reconnection.
 */

export type ServerMessage =
  | { type: "show" }
  | { type: "hide" }
  | { type: "state"; value: "idle" | "listening" | "thinking" | "speaking" }
  | { type: "subtitle"; who: "user" | "miku"; text: string }
  | { type: "expression"; name: string }
  | { type: "stop_speaking" }
  | { type: "speak"; audio_b64: string; mime: string; text: string; emotion: string }
  | { type: "confirm_request"; id: string; text: string };

export type MessageHandler = (msg: ServerMessage) => void;

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string = "ws://127.0.0.1:8765";
  private handlers: Set<MessageHandler> = new Set();
  private reconnectTimeout: number | null = null;
  private retryDelay: number = 1000;
  private maxRetryDelay: number = 10000;
  private queue: string[] = [];
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

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log(`[WS] Connected to Miku Core at ${this.url}`);
        this.isConnected = true;
        this.retryDelay = 1000;

        // Send ready event
        this.send({ type: "ready" });

        // Flush queued messages
        while (this.queue.length > 0) {
          const item = this.queue.shift();
          if (item) this.ws?.send(item);
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
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
      if (this.queue.length >= 20) {
        this.queue.shift(); // Bound memory
      }
      this.queue.push(payload);
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

