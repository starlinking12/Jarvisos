import type { StateCreator } from "zustand";
import type { BackendStatus } from "@jarvis/contracts";
import type { ConnectionState } from "../../core/events/WebSocketClient";

export interface BackendSlice {
  backendStatus: BackendStatus;
  backendUptimeMs: number | null;
  backendRestartCount: number;
  eventBusConnectionState: ConnectionState;
  setBackendStatus: (status: BackendStatus, uptimeMs: number | null, restartCount: number) => void;
  setEventBusConnectionState: (state: ConnectionState) => void;
}

export const createBackendSlice: StateCreator<
  BackendSlice,
  [["zustand/subscribeWithSelector", never]],
  [],
  BackendSlice
> = (set) => ({
  backendStatus: "starting",
  backendUptimeMs: null,
  backendRestartCount: 0,
  eventBusConnectionState: "closed",

  setBackendStatus: (status, uptimeMs, restartCount) =>
    set({ backendStatus: status, backendUptimeMs: uptimeMs, backendRestartCount: restartCount }),

  setEventBusConnectionState: (state) => set({ eventBusConnectionState: state }),
});
