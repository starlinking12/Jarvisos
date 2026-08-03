import { Tray, Menu, nativeImage } from "electron";
import log from "electron-log/main";
import path from "node:path";
import type { BackendStatus } from "@jarvis/contracts";

const logger = log.scope("TrayManager");

export interface TrayManagerCallbacks {
  onShowHud: () => void;
  onOpenSettings: () => void;
  onToggleOverlay: () => void;
  onQuit: () => void;
}

/**
 * Owns the system tray icon and its context menu. Reflects backend status
 * via icon state and exposes quick actions without requiring a window to be
 * open — important for an "always available" AI OS.
 */
export class TrayManager {
  private tray: Tray | null = null;
  private readonly iconDir: string;
  private readonly callbacks: TrayManagerCallbacks;
  private lastStatus: BackendStatus = "starting";

  constructor(iconDir: string, callbacks: TrayManagerCallbacks) {
    this.iconDir = iconDir;
    this.callbacks = callbacks;
  }

  public init(): void {
    const icon = this.iconFor("starting");
    this.tray = new Tray(icon);
    this.tray.setToolTip("JARVIS OS — starting…");
    this.tray.setContextMenu(this.buildMenu());
    this.tray.on("click", () => this.callbacks.onShowHud());
    logger.info("Tray initialized");
  }

  public setBackendStatus(status: BackendStatus): void {
    this.lastStatus = status;
    if (!this.tray) return;
    this.tray.setImage(this.iconFor(status));
    this.tray.setToolTip(`JARVIS OS — ${this.statusLabel(status)}`);
    this.tray.setContextMenu(this.buildMenu());
  }

  public destroy(): void {
    this.tray?.destroy();
    this.tray = null;
  }

  // -- internals -------------------------------------------------------

  private buildMenu(): Menu {
    return Menu.buildFromTemplate([
      {
        label: `Status: ${this.statusLabel(this.lastStatus)}`,
        enabled: false,
      },
      { type: "separator" },
      { label: "Show HUD", click: () => this.callbacks.onShowHud() },
      {
        label: "Toggle Overlay Interaction",
        click: () => this.callbacks.onToggleOverlay(),
      },
      { label: "Settings…", click: () => this.callbacks.onOpenSettings() },
      { type: "separator" },
      {
        label: "Quit JARVIS OS",
        click: () => this.callbacks.onQuit(),
        accelerator: "CmdOrCtrl+Q",
      },
    ]);
  }

  private statusLabel(status: BackendStatus): string {
    switch (status) {
      case "starting":
        return "Starting…";
      case "ready":
        return "Ready";
      case "degraded":
        return "Degraded";
      case "crashed":
        return "Backend Crashed";
      case "stopped":
        return "Stopped";
    }
  }

  private iconFor(status: BackendStatus): Electron.NativeImage {
    // Phase 0: single neutral icon. Per-status icon assets land in Phase 1
    // alongside the rest of the visual design system.
    const iconPath = path.join(this.iconDir, "tray-icon.png");
    const image = nativeImage.createFromPath(iconPath);
    return image.isEmpty() ? nativeImage.createEmpty() : image;
  }
}
