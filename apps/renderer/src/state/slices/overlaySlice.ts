import type { StateCreator } from "zustand";
import { invokeJarvis } from "../../core/ipc/jarvisBridge";
import { createLogger } from "../../core/logging/logger";

const logger = createLogger("OverlaySlice");

export interface OverlaySlice {
  clickThrough: boolean;
  /** Optimistically updates local state, then confirms with the main process. */
  toggleClickThrough: () => Promise<void>;
  setClickThroughLocal: (clickThrough: boolean) => void;
}

export const createOverlaySlice: StateCreator<
  OverlaySlice,
  [["zustand/subscribeWithSelector", never]],
  [],
  OverlaySlice
> = (set, get) => ({
  clickThrough: true,

  setClickThroughLocal: (clickThrough) => set({ clickThrough }),

  toggleClickThrough: async () => {
    const next = !get().clickThrough;
    set({ clickThrough: next }); // optimistic — the overlay window itself is the real source of truth

    try {
      const result = await invokeJarvis("overlay.setClickThrough", { clickThrough: next });
      set({ clickThrough: result.clickThrough });
    } catch (error) {
      logger.error("Failed to toggle click-through — reverting", { error: String(error) });
      set({ clickThrough: !next });
    }
  },
});
