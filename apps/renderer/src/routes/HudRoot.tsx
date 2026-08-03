import { useEffect } from "react";
import { AppShell } from "../layout/AppShell";
import { registerCoreWidgets } from "../widgets/registerCoreWidgets";
import { useJarvisStore } from "../state/store";

/**
 * The main HUD window's root route. Registers core widgets and opens the
 * default docked set on first mount — a real, working default layout
 * rather than an empty shell, so the app is immediately useful without
 * requiring the user to manually add every widget.
 */
export function HudRoot() {
  useEffect(() => {
    registerCoreWidgets();

    const { widgetInstances, openWidget } = useJarvisStore.getState();
    if (widgetInstances.length === 0) {
      openWidget("core.backend-status", "right");
      openWidget("core.performance", "right");
    }
  }, []);

  return <AppShell />;
}
