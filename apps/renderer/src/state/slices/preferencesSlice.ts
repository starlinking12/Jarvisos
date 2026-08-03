import type { StateCreator } from "zustand";
import { loadPersistedSetting, savePersistedSetting } from "../persistence";
import { createLogger } from "../../core/logging/logger";

const logger = createLogger("PreferencesSlice");

const KEY_PERFORMANCE_OVERLAY_DEFAULT = "renderer.performanceOverlayVisibleDefault";
const KEY_OVERLAY_CLICK_THROUGH_DEFAULT = "renderer.overlayClickThroughDefault";

/**
 * Persisted, user-editable *default* preferences — distinct from
 * `overlaySlice`/`performanceSlice`'s live runtime state. A preference
 * here answers "what should this be set to on next startup"; the
 * corresponding runtime slice answers "what is it right now" (which may
 * differ, e.g. after the user toggles something mid-session without
 * saving a new default). This split mirrors this project's established
 * "config vs runtime state" separation (e.g. `RetrievalPipeline`'s
 * policy vs `ContextWindowManager`'s per-call fit) applied to the
 * renderer.
 *
 * Backed by the backend's `SettingsRepository` (ADR-0012) via
 * `state/persistence.ts` — completes the Phase 4 mandate: "Settings
 * gains persisted, user-editable preferences," which Phase 1's
 * `SettingsRoot` was explicitly built read-only pending.
 */
export interface PreferencesSlice {
  preferencesLoaded: boolean;
  performanceOverlayVisibleDefault: boolean;
  overlayClickThroughDefault: boolean;
  hydratePreferences: () => Promise<void>;
  setPerformanceOverlayVisibleDefault: (value: boolean) => Promise<void>;
  setOverlayClickThroughDefault: (value: boolean) => Promise<void>;
}

export const createPreferencesSlice: StateCreator<
  PreferencesSlice,
  [["zustand/subscribeWithSelector", never]],
  [],
  PreferencesSlice
> = (set) => ({
  preferencesLoaded: false,
  performanceOverlayVisibleDefault: false,
  overlayClickThroughDefault: true,

  hydratePreferences: async () => {
    const [performanceOverlayVisibleDefault, overlayClickThroughDefault] = await Promise.all([
      loadPersistedSetting(KEY_PERFORMANCE_OVERLAY_DEFAULT, false),
      loadPersistedSetting(KEY_OVERLAY_CLICK_THROUGH_DEFAULT, true),
    ]);
    set({
      performanceOverlayVisibleDefault,
      overlayClickThroughDefault,
      preferencesLoaded: true,
    });
    logger.info("Preferences hydrated", {
      performanceOverlayVisibleDefault,
      overlayClickThroughDefault,
    });
  },

  setPerformanceOverlayVisibleDefault: async (value) => {
    set({ performanceOverlayVisibleDefault: value });
    await savePersistedSetting(KEY_PERFORMANCE_OVERLAY_DEFAULT, value);
  },

  setOverlayClickThroughDefault: async (value) => {
    set({ overlayClickThroughDefault: value });
    await savePersistedSetting(KEY_OVERLAY_CLICK_THROUGH_DEFAULT, value);
  },
});
