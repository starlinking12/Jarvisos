/**
 * IPC Contracts — the ONLY allowed shape for renderer <-> Electron-main
 * communication.
 *
 * Rules (enforced by ADR-0001 / ARCHITECTURE.md §3):
 *  - Renderers call these via `window.jarvis.invoke(channel, payload)`,
 *    which is a thin wrapper around `ipcRenderer.invoke`.
 *  - Every channel has a request schema and a response schema. Nothing is
 *    sent across the bridge without being parsed by the corresponding zod
 *    schema on both ends.
 *  - Adding a new IPC capability means adding an entry here FIRST, then
 *    implementing the handler in `apps/shell/src/main/ipc/IpcBridge.ts`.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Channel: window.create — request the shell open/focus a managed HUD window
// ---------------------------------------------------------------------------
export const WindowKind = z.enum([
  "main-hud",
  "overlay",
  "settings",
  "command-palette",
]);
export type WindowKind = z.infer<typeof WindowKind>;

export const WindowCreateRequest = z.object({
  kind: WindowKind,
  focusIfExists: z.boolean().default(true),
});
export type WindowCreateRequest = z.infer<typeof WindowCreateRequest>;

export const WindowCreateResponse = z.object({
  windowId: z.number().int(),
  kind: WindowKind,
  createdNew: z.boolean(),
});
export type WindowCreateResponse = z.infer<typeof WindowCreateResponse>;

// ---------------------------------------------------------------------------
// Channel: overlay.setClickThrough — toggle click-through on the overlay HUD
// ---------------------------------------------------------------------------
export const OverlaySetClickThroughRequest = z.object({
  clickThrough: z.boolean(),
});
export type OverlaySetClickThroughRequest = z.infer<
  typeof OverlaySetClickThroughRequest
>;

export const OverlaySetClickThroughResponse = z.object({
  clickThrough: z.boolean(),
});
export type OverlaySetClickThroughResponse = z.infer<
  typeof OverlaySetClickThroughResponse
>;

// ---------------------------------------------------------------------------
// Channel: backend.status — query Python backend supervisor state
// ---------------------------------------------------------------------------
export const BackendStatus = z.enum([
  "starting",
  "ready",
  "degraded",
  "crashed",
  "stopped",
]);
export type BackendStatus = z.infer<typeof BackendStatus>;

export const BackendStatusResponse = z.object({
  status: BackendStatus,
  pid: z.number().int().nullable(),
  uptimeMs: z.number().int().nonnegative().nullable(),
  restartCount: z.number().int().nonnegative(),
});
export type BackendStatusResponse = z.infer<typeof BackendStatusResponse>;

// ---------------------------------------------------------------------------
// Channel: permission.request — gate a high-impact native action
// ---------------------------------------------------------------------------
export const PermissionScope = z.enum([
  "filesystem.write",
  "process.control",
  "network.egress",
  "automation.input", // synthetic mouse/keyboard
  "shell.execute",
  "audio.microphone", // activating live microphone capture (Phase 3 voice engine)
]);
export type PermissionScope = z.infer<typeof PermissionScope>;

export const PermissionRequest = z.object({
  scope: PermissionScope,
  reason: z.string().min(1),
  requestedBy: z.string().min(1), // agent or subsystem identifier
});
export type PermissionRequest = z.infer<typeof PermissionRequest>;

export const PermissionDecision = z.object({
  granted: z.boolean(),
  scope: PermissionScope,
  rememberForSession: z.boolean().default(false),
});
export type PermissionDecision = z.infer<typeof PermissionDecision>;

// ---------------------------------------------------------------------------
// Registry — maps channel name to {request, response} schema pair.
// Used by IpcBridge.ts to validate at the handler boundary, and can be used
// to generate a typed `window.jarvis` client for the preload script.
// ---------------------------------------------------------------------------
export const IpcChannels = {
  "window.create": {
    request: WindowCreateRequest,
    response: WindowCreateResponse,
  },
  "overlay.setClickThrough": {
    request: OverlaySetClickThroughRequest,
    response: OverlaySetClickThroughResponse,
  },
  "backend.status": {
    request: z.void(),
    response: BackendStatusResponse,
  },
  "permission.request": {
    request: PermissionRequest,
    response: PermissionDecision,
  },
} as const;

export type IpcChannelName = keyof typeof IpcChannels;
