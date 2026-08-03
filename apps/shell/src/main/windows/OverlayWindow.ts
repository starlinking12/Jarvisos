import { BrowserWindow, screen } from "electron";
import log from "electron-log/main";

const logger = log.scope("OverlayWindow");

export interface OverlayWindowOptions {
  rendererEntry: string;
  devServerUrl?: string;
  preloadPath: string;
}

/**
 * The overlay is a single, full-screen, frameless, transparent,
 * always-on-top window used to render HUD elements (Arc Reactor glow,
 * ambient particles, contextual annotations) directly over the desktop.
 *
 * It defaults to click-through (mouseForwarding) so it never intercepts
 * input to underlying applications. Click-through is toggled off only for
 * the brief windows when the user is actively interacting with an overlay
 * element (e.g. the command palette invoked from within the overlay).
 *
 * This is intentionally a separate class from WindowManager: overlay
 * semantics (click-through, always-on-top, screen-capture visibility) are
 * fundamentally different from normal app windows and mixing them invites
 * bugs where a HUD accidentally becomes focusable/opaque.
 */
export class OverlayWindow {
  private window: BrowserWindow | null = null;
  private readonly options: OverlayWindowOptions;
  private clickThrough = true;

  constructor(options: OverlayWindowOptions) {
    this.options = options;
  }

  public getOrCreate(): BrowserWindow {
    if (this.window && !this.window.isDestroyed()) {
      return this.window;
    }

    const display = screen.getPrimaryDisplay();
    const win = new BrowserWindow({
      x: 0,
      y: 0,
      width: display.bounds.width,
      height: display.bounds.height,
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      hasShadow: false,
      skipTaskbar: true,
      resizable: false,
      movable: false,
      focusable: false,
      fullscreenable: false,
      backgroundColor: "#00000000",
      webPreferences: {
        preload: this.options.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });

    // Keep the overlay above fullscreen apps too, on platforms that support it.
    win.setAlwaysOnTop(true, "screen-saver");
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    win.setIgnoreMouseEvents(this.clickThrough, { forward: true });

    void this.load(win);

    win.on("closed", () => {
      logger.info("Overlay window closed");
      this.window = null;
    });

    this.window = win;
    logger.info("Overlay window created", { clickThrough: this.clickThrough });
    return win;
  }

  public setClickThrough(clickThrough: boolean): boolean {
    this.clickThrough = clickThrough;
    if (this.window && !this.window.isDestroyed()) {
      this.window.setIgnoreMouseEvents(clickThrough, { forward: true });
    }
    logger.info("Overlay click-through changed", { clickThrough });
    return this.clickThrough;
  }

  public isClickThrough(): boolean {
    return this.clickThrough;
  }

  public destroy(): void {
    if (this.window && !this.window.isDestroyed()) {
      this.window.close();
    }
    this.window = null;
  }

  private async load(win: BrowserWindow): Promise<void> {
    if (this.options.devServerUrl) {
      await win.loadURL(`${this.options.devServerUrl}#/overlay`);
    } else {
      await win.loadFile(this.options.rendererEntry, { hash: "/overlay" });
    }
    win.once("ready-to-show", () => win.show());
  }
}
