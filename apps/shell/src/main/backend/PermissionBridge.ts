import WebSocket from "ws";
import log from "electron-log/main";
import { JarvisEvent } from "@jarvis/contracts";
import type { PermissionGate } from "../ipc/permissions";

const logger = log.scope("PermissionBridge");

/**
 * The shell-side half of the backend→shell permission RPC (ADR-0012).
 * `SafetyGate`'s `PROMPT` tier (Python, `agents/permission_broker.py`)
 * publishes a `permission.request` event when it needs an interactive
 * decision; this class is a dedicated WebSocket subscriber to the
 * backend's event stream (separate from `IpcBridge`'s renderer-facing
 * concerns — this connection exists purely to feed `PermissionGate`,
 * matching `BackendSupervisor`'s "one collaborator, one job" shape) that
 * reacts specifically to that event type, shows the existing
 * `PermissionGate` dialog, and POSTs the answer back.
 *
 * Reuses `PermissionGate.request()` unchanged — from `PermissionGate`'s
 * point of view, a backend-originated request and a renderer-originated
 * one (via `IpcBridge`'s `permission.request` IPC channel — a different,
 * pre-existing concept with the same name coincidentally) are identical;
 * both are just "ask the user, show one dialog, return one decision."
 */
export class PermissionBridge {
  private readonly backendPort: number;
  private readonly permissionGate: PermissionGate;
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private closedByCaller = false;

  constructor(backendPort: number, permissionGate: PermissionGate) {
    this.backendPort = backendPort;
    this.permissionGate = permissionGate;
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
  }

  private open(): void {
    const url = `ws://127.0.0.1:${this.backendPort}/ws/events`;
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.on("open", () => {
      this.reconnectAttempt = 0;
      logger.info("Connected to backend event stream", { url });
    });

    socket.on("message", (data: WebSocket.RawData) => {
      void this.handleMessage(data.toString());
    });

    socket.on("error", (error) => {
      logger.warn("Backend event stream error", { error: String(error) });
    });

    socket.on("close", () => {
      if (!this.closedByCaller) this.scheduleReconnect();
    });
  }

  private scheduleReconnect(): void {
    const delay = Math.min(500 * 2 ** this.reconnectAttempt, 15_000);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => this.open(), delay);
  }

  private async handleMessage(raw: string): Promise<void> {
    let parsedJson: unknown;
    try {
      parsedJson = JSON.parse(raw);
    } catch {
      return; // not JSON — not our concern, IpcBridge/renderer clients handle their own parsing
    }

    const result = JarvisEvent.safeParse(parsedJson);
    if (!result.success || result.data.type !== "permission.request") {
      return; // every other event type is for the renderer, not this bridge
    }

    const { requestId, scope, reason, requestedBy } = result.data.payload;
    logger.info("Permission request received from backend", { requestId, scope, requestedBy });

    const decision = await this.permissionGate.request({ scope, reason, requestedBy });

    await this.postDecision(requestId, decision.granted);
  }

  private async postDecision(requestId: string, granted: boolean): Promise<void> {
    const url = `http://127.0.0.1:${this.backendPort}/agent/permission-decision`;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requestId, granted }),
      });
      if (!response.ok) {
        logger.warn("Backend rejected permission decision", {
          requestId,
          status: response.status,
        });
      }
    } catch (error) {
      logger.error("Failed to POST permission decision to backend", {
        requestId,
        error: String(error),
      });
    }
  }
}
