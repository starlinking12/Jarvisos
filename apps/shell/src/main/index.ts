import { app, BrowserWindow } from "electron";
import log from "electron-log/main";
import path from "node:path";

import { WindowManager } from "./windows/WindowManager";
import { OverlayWindow } from "./windows/OverlayWindow";
import { TrayManager } from "./tray/TrayManager";
import { GlobalShortcuts, DEFAULT_ACCELERATORS } from "./shortcuts/GlobalShortcuts";
import { BackendSupervisor } from "./backend/BackendSupervisor";
import { PermissionBridge } from "./backend/PermissionBridge";
import { PermissionGate } from "./ipc/permissions";
import { IpcBridge } from "./ipc/IpcBridge";

log.initialize();
log.transports.file.level = "info";
log.transports.console.level = process.env.NODE_ENV === "development" ? "debug" : "info";
const logger = log.scope("Main");

const isDev = process.env.NODE_ENV === "development";
const DEV_SERVER_URL = process.env.JARVIS_RENDERER_DEV_URL ?? "http://localhost:5173";
const RENDERER_ENTRY = path.join(__dirname, "../renderer/index.html");
const PRELOAD_PATH = path.join(__dirname, "../preload/index.js");
const ASSETS_DIR = path.join(__dirname, "../../assets");
const BACKEND_PORT = Number(process.env.JARVIS_BACKEND_PORT ?? 8137);

// Enforce single-instance: JARVIS OS is a system-level assistant, not a
// document editor — running two instances would double-spawn the backend
// and fight over global shortcuts/tray/overlay.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  logger.warn("Another instance is already running — quitting");
  app.quit();
  process.exit(0);
}

let windowManager: WindowManager;
let overlayWindow: OverlayWindow;
let trayManager: TrayManager;
let globalShortcuts: GlobalShortcuts;
let backendSupervisor: BackendSupervisor;
let permissionBridge: PermissionBridge;
let permissionGate: PermissionGate;
let ipcBridge: IpcBridge;

app.on("second-instance", () => {
  logger.info("Second instance attempted — focusing main HUD");
  windowManager?.openOrFocus("main-hud", true);
});

app.whenReady().then(async () => {
  logger.info("App ready — composing subsystems", {
    isDev,
    backendPort: BACKEND_PORT,
  });

  windowManager = new WindowManager({
    rendererEntry: RENDERER_ENTRY,
    devServerUrl: isDev ? DEV_SERVER_URL : undefined,
    preloadPath: PRELOAD_PATH,
  });

  overlayWindow = new OverlayWindow({
    rendererEntry: RENDERER_ENTRY,
    devServerUrl: isDev ? DEV_SERVER_URL : undefined,
    preloadPath: PRELOAD_PATH,
  });

  permissionGate = new PermissionGate();

  backendSupervisor = new BackendSupervisor({
    pythonPath: resolvePythonPath(),
    cwd: path.join(__dirname, "../../../backend"),
    module: "jarvis_backend.main",
    port: BACKEND_PORT,
  });

  trayManager = new TrayManager(ASSETS_DIR, {
    onShowHud: () => windowManager.openOrFocus("main-hud", true),
    onOpenSettings: () => windowManager.openOrFocus("settings", true),
    onToggleOverlay: () =>
      overlayWindow.setClickThrough(!overlayWindow.isClickThrough()),
    onQuit: () => app.quit(),
  });

  globalShortcuts = new GlobalShortcuts();
  globalShortcuts.registerAll([
    {
      id: "summon-command-palette",
      accelerator: DEFAULT_ACCELERATORS["summon-command-palette"],
      handler: () => windowManager.openOrFocus("command-palette", true),
    },
    {
      id: "toggle-overlay-interaction",
      accelerator: DEFAULT_ACCELERATORS["toggle-overlay-interaction"],
      handler: () =>
        overlayWindow.setClickThrough(!overlayWindow.isClickThrough()),
    },
    {
      id: "toggle-hud-visibility",
      accelerator: DEFAULT_ACCELERATORS["toggle-hud-visibility"],
      handler: () => {
        const hud = windowManager.get("main-hud");
        if (!hud) {
          windowManager.openOrFocus("main-hud", true);
        } else {
          hud.isVisible() ? hud.hide() : hud.show();
        }
      },
    },
  ]);

  ipcBridge = new IpcBridge({
    windowManager,
    overlayWindow,
    backendSupervisor,
    permissionGate,
  });
  ipcBridge.registerAll();

  permissionBridge = new PermissionBridge(BACKEND_PORT, permissionGate);
  permissionBridge.connect();

  backendSupervisor.on("statusChange", (status) => {
    trayManager.setBackendStatus(status);
  });

  trayManager.init();
  backendSupervisor.start();
  overlayWindow.getOrCreate();
  windowManager.openOrFocus("main-hud", true);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      windowManager.openOrFocus("main-hud", true);
    }
  });
});

app.on("window-all-closed", () => {
  // JARVIS OS lives in the tray — closing HUD windows must not quit the app.
  // Actual quit only happens via explicit tray "Quit" or Cmd/Ctrl+Q.
  if (process.platform !== "darwin") {
    // no-op by design; see comment above
  }
});

app.on("before-quit", () => {
  logger.info("App quitting — tearing down subsystems");
  globalShortcuts?.unregisterAll();
  ipcBridge?.unregisterAll();
  permissionBridge?.disconnect();
  backendSupervisor?.stop();
  overlayWindow?.destroy();
  windowManager?.closeAll();
  trayManager?.destroy();
});

/**
 * Resolves the Python interpreter path for the backend venv. Phase 0 keeps
 * this simple (env override or a conventional venv path); Phase 5 packaging
 * bundles a pinned Python runtime so this resolution becomes deterministic
 * across end-user machines.
 */
function resolvePythonPath(): string {
  if (process.env.JARVIS_PYTHON_PATH) return process.env.JARVIS_PYTHON_PATH;
  const venvPython =
    process.platform === "win32"
      ? path.join(__dirname, "../../../backend/.venv/Scripts/python.exe")
      : path.join(__dirname, "../../../backend/.venv/bin/python");
  return venvPython;
}
