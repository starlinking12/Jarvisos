import type { IpcChannelName, IpcChannels } from "@jarvis/contracts";
import { createLogger } from "../logging/logger";

const logger = createLogger("JarvisBridge");

/**
 * The shape exposed on `window.jarvis` by `apps/shell/src/preload/index.ts`.
 * Declared here (not imported from the shell package) so the renderer never
 * depends on Electron/Node types — it only needs the channel registry from
 * `@jarvis/contracts`, which is framework-agnostic.
 */
declare global {
  interface Window {
    jarvis?: {
      invoke: <C extends IpcChannelName>(
        channel: C,
        payload: import("zod").infer<(typeof IpcChannels)[C]["request"]>,
      ) => Promise<import("zod").infer<(typeof IpcChannels)[C]["response"]>>;
    };
  }
}

/**
 * Calls a main-process IPC channel. Throws a clear error if the renderer is
 * running outside Electron (e.g. `vite dev` opened in a plain browser tab
 * for UI-only iteration) instead of failing with a confusing
 * "undefined is not a function".
 */
export async function invokeJarvis<C extends IpcChannelName>(
  channel: C,
  payload: import("zod").infer<(typeof IpcChannels)[C]["request"]>,
): Promise<import("zod").infer<(typeof IpcChannels)[C]["response"]>> {
  if (!window.jarvis) {
    logger.warn(
      "window.jarvis is unavailable — running outside Electron. IPC calls are no-ops.",
      { channel },
    );
    throw new Error(
      `Cannot invoke "${channel}": renderer is not running inside the JARVIS Electron shell.`,
    );
  }

  return window.jarvis.invoke(channel, payload);
}

export function isElectronHost(): boolean {
  return typeof window.jarvis !== "undefined";
}
