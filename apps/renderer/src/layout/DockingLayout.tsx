import { AnimatePresence } from "framer-motion";
import { useMemo } from "react";
import { useJarvisStore } from "../state/store";
import { Widget } from "./Widget";
import type { DockZone } from "./WidgetRegistry";
import type { WidgetInstance } from "../state/slices/uiSlice";

/**
 * Four fixed dock zones laid out with CSS grid — left rail, right rail,
 * bottom rail, and a floating layer for freely-positioned panels
 * (positioning for `floating` is Phase 2; Phase 1 stacks them in the
 * top-right as a placeholder-free, functional default).
 *
 * Selects `widgetInstances` narrowly and groups locally with `useMemo`
 * rather than storing pre-grouped state, keeping the store's shape simple
 * (a flat array) while still avoiding recomputation on unrelated state
 * changes.
 */
export function DockingLayout() {
  const widgetInstances = useJarvisStore((state) => state.widgetInstances);

  const byZone = useMemo(() => {
    const grouped: Record<DockZone, WidgetInstance[]> = {
      left: [],
      right: [],
      bottom: [],
      floating: [],
    };
    for (const instance of widgetInstances) {
      grouped[instance.dock].push(instance);
    }
    for (const zone of Object.keys(grouped) as DockZone[]) {
      grouped[zone].sort((a, b) => a.order - b.order);
    }
    return grouped;
  }, [widgetInstances]);

  return (
    <div className="jarvis-docking-layout">
      <div className="jarvis-dock-zone jarvis-dock-zone--left">
        <AnimatePresence>
          {byZone.left.map((instance) => (
            <Widget key={instance.instanceId} instance={instance} />
          ))}
        </AnimatePresence>
      </div>

      <div className="jarvis-dock-zone jarvis-dock-zone--right">
        <AnimatePresence>
          {byZone.right.map((instance) => (
            <Widget key={instance.instanceId} instance={instance} />
          ))}
        </AnimatePresence>
      </div>

      <div className="jarvis-dock-zone jarvis-dock-zone--bottom">
        <AnimatePresence>
          {byZone.bottom.map((instance) => (
            <Widget key={instance.instanceId} instance={instance} />
          ))}
        </AnimatePresence>
      </div>

      <div className="jarvis-dock-zone jarvis-dock-zone--floating">
        <AnimatePresence>
          {byZone.floating.map((instance) => (
            <Widget key={instance.instanceId} instance={instance} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
