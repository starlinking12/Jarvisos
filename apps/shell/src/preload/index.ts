import { contextBridge, ipcRenderer } from "electron";
import type { IpcChannelName, IpcChannels } from "@jarvis/contracts";

/**
 * The ONLY surface a renderer ever touches. `contextIsolation: true` and
 * `nodeIntegration: false` are enforced on every BrowserWindow (see
 * WindowManager/OverlayWindow), so this is the sole crossing point between
 * renderer JS and the main process.
 *
 * `invoke` is generic over the shared IpcChannels registry so renderer code
 * gets full type safety without ever importing Electron or Node APIs
 * directly.
 */
const jarvisApi = {
  invoke: <C extends IpcChannelName>(
    channel: C,
    payload: import("zod").infer<(typeof IpcChannels)[C]["request"]>,
  ): Promise<import("zod").infer<(typeof IpcChannels)[C]["response"]>> => {
    return ipcRenderer.invoke(channel, payload);
  },
};

contextBridge.exposeInMainWorld("jarvis", jarvisApi);

export type JarvisApi = typeof jarvisApi;
