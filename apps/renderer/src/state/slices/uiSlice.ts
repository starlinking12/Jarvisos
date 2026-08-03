import type { StateCreator } from "zustand";
import type { DockZone } from "../../layout/WidgetRegistry";

export interface WidgetInstance {
  instanceId: string;
  widgetId: string;
  dock: DockZone;
  order: number;
  collapsed: boolean;
}

export interface UiSlice {
  widgetInstances: WidgetInstance[];
  commandPaletteOpen: boolean;
  openWidget: (widgetId: string, dock: DockZone) => void;
  closeWidget: (instanceId: string) => void;
  moveWidget: (instanceId: string, dock: DockZone, order: number) => void;
  toggleWidgetCollapsed: (instanceId: string) => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

let instanceCounter = 0;
function nextInstanceId(widgetId: string): string {
  instanceCounter += 1;
  return `${widgetId}-${instanceCounter}`;
}

export const createUiSlice: StateCreator<
  UiSlice,
  [["zustand/subscribeWithSelector", never]],
  [],
  UiSlice
> = (set) => ({
  widgetInstances: [],
  commandPaletteOpen: false,

  openWidget: (widgetId, dock) =>
    set((state) => {
      const order = state.widgetInstances.filter((w) => w.dock === dock).length;
      return {
        widgetInstances: [
          ...state.widgetInstances,
          { instanceId: nextInstanceId(widgetId), widgetId, dock, order, collapsed: false },
        ],
      };
    }),

  closeWidget: (instanceId) =>
    set((state) => ({
      widgetInstances: state.widgetInstances.filter((w) => w.instanceId !== instanceId),
    })),

  moveWidget: (instanceId, dock, order) =>
    set((state) => ({
      widgetInstances: state.widgetInstances.map((w) =>
        w.instanceId === instanceId ? { ...w, dock, order } : w,
      ),
    })),

  toggleWidgetCollapsed: (instanceId) =>
    set((state) => ({
      widgetInstances: state.widgetInstances.map((w) =>
        w.instanceId === instanceId ? { ...w, collapsed: !w.collapsed } : w,
      ),
    })),

  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
});
