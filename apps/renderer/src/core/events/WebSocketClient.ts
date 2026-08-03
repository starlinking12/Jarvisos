import { createLogger } from "../logging/logger";

const logger = createLogger("WebSocketClient");

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export interface WebSocketClientOptions {
  url: string;
  /** Base delay for exponential backoff between reconnect attempts, ms. */
  baseBackoffMs?: number;
  /** Cap on backoff delay, ms. */
  maxBackoffMs?: number;
}

/**
 * A reconnecting WebSocket transport with exponential backoff. Deliberately
 * schema-agnostic — it deals in raw string messages only. `EventBusClient`
 * layers `JarvisEvent` parsing on top, keeping the transport reusable for
 * any future socket-based channel without duplicating reconnect logic.
 */
export class WebSocketClient {
  private socket: WebSocket | null = null;
  private state: ConnectionState = "closed";
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByCaller = false;

  private readonly url: string;
  private readonly baseBackoffMs: number;
  private readonly maxBackoffMs: number;

  private readonly messageListeners = new Set<(data: string) => void>();
  private readonly stateListeners = new Set<(state: ConnectionState) => void>();

  constructor(options: WebSocketClientOptions) {
    this.url = options.url;
    this.baseBackoffMs = options.baseBackoffMs ?? 500;
    this.maxBackoffMs = options.maxBackoffMs ?? 15_000;
  }

  public connect(): void {
    this.closedByCaller = false;
    this.open();
  }

  public disconnect(): void {
    this.closedByCaller = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setState("closed");
  }

  public getState(): ConnectionState {
    return this.state;
  }

  public onMessage(listener: (data: string) => void): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  public onStateChange(listener: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  // -- internals -------------------------------------------------------

  private open(): void {
    this.setState("connecting");
    logger.info("Connecting", { url: this.url, attempt: this.reconnectAttempt });

    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setState("open");
      logger.info("Connected");
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      for (const listener of this.messageListeners) listener(event.data);
    };

    socket.onerror = () => {
      this.setState("error");
    };

    socket.onclose = () => {
      this.setState("closed");
      if (!this.closedByCaller) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    const delay = Math.min(
      this.baseBackoffMs * 2 ** this.reconnectAttempt,
      this.maxBackoffMs,
    );
    this.reconnectAttempt += 1;
    logger.warn("Connection lost — reconnecting", { delayMs: delay });
    this.reconnectTimer = setTimeout(() => this.open(), delay);
  }

  private setState(state: ConnectionState): void {
    this.state = state;
    for (const listener of this.stateListeners) listener(state);
  }
}
