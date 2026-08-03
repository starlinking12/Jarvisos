import { BrowserWindow, screen } from "electron";
import log from "electron-log/main";
import type { WindowKind } from "@jarvis/contracts";

const logger = log.scope("WindowManager");

export interface WindowManagerOptions {
  /** Absolute path to the renderer's built index.html (Vite output). */
  rendererEntry: string;
  /** Base dev server URL, used instead of rendererEntry when set (dev mode). */
  devServerUrl?: string;
  /** Absolute path to the compiled preload script. */
  preloadPath: string;
}

interface WindowSpec {
  kind: WindowKind;
  build: () => BrowserWindow;
}

/**
 * Owns the lifecycle of every managed BrowserWindow in the shell (excluding
 * the overlay, which has its own class due to click-through/always-on-top
 * behavior — see OverlayWindow.ts).
 *
 * Single responsibility: create-or-focus semantics per WindowKind, and
 * tear-down on quit. Nothing here knows about IPC contracts or the backend —
 * those are wired in from index.ts via composition.
 */
export class WindowManager {
  private readonly windows = new Map<WindowKind, BrowserWindow>();
  private readonly options: WindowManagerOptions;

  constructor(options: WindowManagerOptions) {
    this.options = options;
  }

  /** Returns the existing window for `kind`, creating it if necessary. */
  public openOrFocus(kind: WindowKind, focusIfExists = true): {
    window: BrowserWindow;
    createdNew: boolean;
  } {
    const existing = this.windows.get(kind);
    if (existing && !existing.isDestroyed()) {
      if (focusIfExists) {
        existing.show();
        existing.focus();
      }
      return { window: existing, createdNew: false };
    }

    const spec = this.specFor(kind);
    const win = spec.build();
    this.registerLifecycle(kind, win);
    this.windows.set(kind, win);
    logger.info(`Window created`, { kind, id: win.id });
    return { window: win, createdNew: true };
  }

  public get(kind: WindowKind): BrowserWindow | undefined {
    const win = this.windows.get(kind);
    return win && !win.isDestroyed() ? win : undefined;
  }

  public closeAll(): void {
    for (const [kind, win] of this.windows) {
      if (!win.isDestroyed()) {
        logger.info(`Closing window on shutdown`, { kind });
        win.close();
      }
    }
    this.windows.clear();
  }

  // -- internals -------------------------------------------------------

  private registerLifecycle(kind: WindowKind, win: BrowserWindow): void {
    win.on("closed", () => {
      logger.info(`Window closed`, { kind, id: win.id });
      this.windows.delete(kind);
    });
  }

  private specFor(kind: WindowKind): WindowSpec {
    switch (kind) {
      case "main-hud":
        return { kind, build: () => this.buildMainHud() };
      case "settings":
        return { kind, build: () => this.buildSettings() };
      case "command-palette":
        return { kind, build: () => this.buildCommandPalette() };
      case "overlay":
        throw new Error(
          "Overlay windows are owned by OverlayWindow, not WindowManager. " +
            "Use OverlayWindow.getOrCreate() instead.",
        );
      default: {
        const exhaustive: never = kind;
        throw new Error(`Unhandled window kind: ${String(exhaustive)}`);
      }
    }
  }

  private baseWindow(overrides: Electron.BrowserWindowConstructorOptions = {}) {
    return new BrowserWindow({
      show: false,
      backgroundColor: "#00000000",
      webPreferences: {
        preload: this.options.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        spellcheck: false,
      },
      ...overrides,
    });
  }

  private async loadRoute(win: BrowserWindow, route: string): Promise<void> {
    if (this.options.devServerUrl) {
      await win.loadURL(`${this.options.devServerUrl}#${route}`);
    } else {
      await win.loadFile(this.options.rendererEntry, { hash: route });
    }
    win.once("ready-to-show", () => win.show());
  }

  private buildMainHud(): BrowserWindow {
    const display = screen.getPrimaryDisplay();
    const win = this.baseWindow({
      width: Math.min(1440, display.workAreaSize.width),
      height: Math.min(900, display.workAreaSize.height),
      minWidth: 960,
      minHeight: 600,
      frame: false,
      titleBarStyle: "hidden",
      transparent: true,
      title: "JARVIS",
    });
    void this.loadRoute(win, "/hud");
    return win;
  }

  private buildSettings(): BrowserWindow {
    const win = this.baseWindow({
      width: 900,
      height: 640,
      resizable: true,
      title: "JARVIS — Settings",
    });
    void this.loadRoute(win, "/settings");
    return win;
  }

  private buildCommandPalette(): BrowserWindow {
    const display = screen.getPrimaryDisplay();
    const width = 640;
    const win = this.baseWindow({
      width,
      height: 72,
      x: Math.round((display.workAreaSize.width - width) / 2),
      y: Math.round(display.workAreaSize.height * 0.18),
      frame: false,
      transparent: true,
      resizable: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      title: "JARVIS — Command",
    });
    win.on("blur", () => win.hide());
    void this.loadRoute(win, "/command-palette");
    return win;
  }
}
