import { ipcMain, type IpcMainInvokeEvent } from "electron";
import log from "electron-log/main";
import { IpcChannels, type IpcChannelName } from "@jarvis/contracts";
import type { WindowManager } from "../windows/WindowManager";
import type { OverlayWindow } from "../windows/OverlayWindow";
import type { BackendSupervisor } from "../backend/BackendSupervisor";
import type { PermissionGate } from "./permissions";

const logger = log.scope("IpcBridge");

export interface IpcBridgeDeps {
  windowManager: WindowManager;
  overlayWindow: OverlayWindow;
  backendSupervisor: BackendSupervisor;
  permissionGate: PermissionGate;
}

/**
 * Wires every entry in `IpcChannels` (packages/contracts/src/ipc-contracts.ts)
 * to a concrete handler, validating both the incoming request and the
 * outgoing response against the shared zod schema before it crosses the
 * process boundary.
 *
 * This is intentionally the ONLY file that calls `ipcMain.handle`. Adding a
 * channel means: (1) define it in the contracts package, (2) add a case
 * here. Nowhere else in the codebase should touch `ipcMain` directly — that
 * invariant is what keeps the IPC surface auditable as the system grows.
 */
export class IpcBridge {
  private readonly deps: IpcBridgeDeps;

  constructor(deps: IpcBridgeDeps) {
    this.deps = deps;
  }

  public registerAll(): void {
    this.handle("window.create", async (payload) => {
      const { window, createdNew } = this.deps.windowManager.openOrFocus(
        payload.kind,
        payload.focusIfExists,
      );
      return { windowId: window.id, kind: payload.kind, createdNew };
    });

    this.handle("overlay.setClickThrough", async (payload) => {
      const clickThrough = this.deps.overlayWindow.setClickThrough(
        payload.clickThrough,
      );
      return { clickThrough };
    });

    this.handle("backend.status", async () => {
      const status = this.deps.backendSupervisor.getStatus();
      return status;
    });

    this.handle("permission.request", async (payload) => {
      return this.deps.permissionGate.request(payload);
    });

    logger.info("All IPC channels registered", {
      channels: Object.keys(IpcChannels),
    });
  }

  public unregisterAll(): void {
    for (const channel of Object.keys(IpcChannels) as IpcChannelName[]) {
      ipcMain.removeHandler(channel);
    }
  }

  // -- internals -------------------------------------------------------

  /**
   * Type-safe wrapper: infers request/response types for `channel` from the
   * shared registry, parses the request with zod before invoking `handler`,
   * and parses the response before returning it to the renderer.
   */
  private handle<C extends IpcChannelName>(
    channel: C,
    handler: (
      payload: import("zod").infer<(typeof IpcChannels)[C]["request"]>,
      event: IpcMainInvokeEvent,
    ) => Promise<import("zod").infer<(typeof IpcChannels)[C]["response"]>>,
  ): void {
    const { request: requestSchema, response: responseSchema } =
      IpcChannels[channel];

    ipcMain.handle(channel, async (event, rawPayload) => {
      const parsedRequest = requestSchema.safeParse(rawPayload);
      if (!parsedRequest.success) {
        logger.error("IPC request failed validation", {
          channel,
          error: parsedRequest.error.flatten(),
        });
        throw new Error(`Invalid request payload for channel "${channel}"`);
      }

      const result = await handler(parsedRequest.data, event);

      const parsedResponse = responseSchema.safeParse(result);
      if (!parsedResponse.success) {
        logger.error("IPC response failed validation", {
          channel,
          error: parsedResponse.error.flatten(),
        });
        throw new Error(
          `Handler for channel "${channel}" produced an invalid response`,
        );
      }

      return parsedResponse.data;
    });
  }
}
