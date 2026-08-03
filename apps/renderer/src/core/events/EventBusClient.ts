import { JarvisEvent, type JarvisEventType } from "@jarvis/contracts";
import { WebSocketClient, type ConnectionState } from "./WebSocketClient";
import { createLogger } from "../logging/logger";

const logger = createLogger("EventBusClient");

type TypedListener<T extends JarvisEventType> = (
  event: Extract<JarvisEvent, { type: T }>,
) => void;

/**
 * Renderer-side counterpart to the backend's `EventBus`
 * (apps/backend/src/jarvis_backend/event_bus.py). Every message received
 * over the WebSocket is validated against the shared `JarvisEvent` zod
 * schema before any subscriber sees it — an invalid or drifted payload is
 * logged and dropped rather than silently misinterpreted.
 *
 * This is the ONLY place in the renderer that parses raw socket data. All
 * other code — widgets, layout, three.js scenes — subscribes via `on()` and
 * works with fully-typed, validated `JarvisEvent` objects.
 */
export class EventBusClient {
  private readonly transport: WebSocketClient;
  private readonly listeners = new Map<JarvisEventType, Set<TypedListener<any>>>();
  private readonly wildcardListeners = new Set<(event: JarvisEvent) => void>();

  constructor(wsUrl: string) {
    this.transport = new WebSocketClient({ url: wsUrl });
    this.transport.onMessage((raw) => this.handleRaw(raw));
  }

  public connect(): void {
    this.transport.connect();
  }

  public disconnect(): void {
    this.transport.disconnect();
  }

  public getConnectionState(): ConnectionState {
    return this.transport.getState();
  }

  public onConnectionStateChange(listener: (state: ConnectionState) => void): () => void {
    return this.transport.onStateChange(listener);
  }

  /** Subscribe to a specific event type, fully typed by discriminant. */
  public on<T extends JarvisEventType>(type: T, listener: TypedListener<T>): () => void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
    return () => this.listeners.get(type)?.delete(listener);
  }

  /** Subscribe to every event, regardless of type — used by logging/devtools widgets. */
  public onAny(listener: (event: JarvisEvent) => void): () => void {
    this.wildcardListeners.add(listener);
    return () => this.wildcardListeners.delete(listener);
  }

  // -- internals -------------------------------------------------------

  private handleRaw(raw: string): void {
    let parsedJson: unknown;
    try {
      parsedJson = JSON.parse(raw);
    } catch {
      logger.error("Received non-JSON event payload", { raw });
      return;
    }

    const result = JarvisEvent.safeParse(parsedJson);
    if (!result.success) {
      logger.error("Event failed contract validation — dropped", {
        error: result.error.flatten(),
      });
      return;
    }

    const event = result.data;
    for (const listener of this.wildcardListeners) listener(event);
    const typed = this.listeners.get(event.type);
    if (typed) {
      for (const listener of typed) listener(event);
    }
  }
}
