import { globalShortcut } from "electron";
import log from "electron-log/main";

const logger = log.scope("GlobalShortcuts");

export type ShortcutId =
  | "summon-command-palette"
  | "toggle-overlay-interaction"
  | "toggle-hud-visibility";

export interface ShortcutBinding {
  id: ShortcutId;
  accelerator: string;
  handler: () => void;
}

/**
 * Thin, testable wrapper around Electron's `globalShortcut`. Centralizing
 * registration here means every system-wide hotkey in the product is
 * discoverable in one place, and default accelerators can be remapped later
 * (Phase 1 settings UI) without touching call sites.
 */
export class GlobalShortcuts {
  private readonly registered = new Map<ShortcutId, string>();

  public registerAll(bindings: ShortcutBinding[]): void {
    for (const binding of bindings) {
      this.register(binding);
    }
  }

  public register(binding: ShortcutBinding): boolean {
    const ok = globalShortcut.register(binding.accelerator, binding.handler);
    if (!ok) {
      logger.warn("Failed to register shortcut (likely in use by OS)", {
        id: binding.id,
        accelerator: binding.accelerator,
      });
      return false;
    }
    this.registered.set(binding.id, binding.accelerator);
    logger.info("Shortcut registered", {
      id: binding.id,
      accelerator: binding.accelerator,
    });
    return true;
  }

  public unregister(id: ShortcutId): void {
    const accelerator = this.registered.get(id);
    if (!accelerator) return;
    globalShortcut.unregister(accelerator);
    this.registered.delete(id);
  }

  public unregisterAll(): void {
    globalShortcut.unregisterAll();
    this.registered.clear();
    logger.info("All shortcuts unregistered");
  }
}

/** Default bindings, wired up from index.ts with real handlers. */
export const DEFAULT_ACCELERATORS: Record<ShortcutId, string> = {
  "summon-command-palette": "Alt+Space",
  "toggle-overlay-interaction": "Alt+Shift+O",
  "toggle-hud-visibility": "Alt+Shift+J",
};
