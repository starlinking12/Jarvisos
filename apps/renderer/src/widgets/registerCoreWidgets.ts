import { WidgetRegistry } from "../layout/WidgetRegistry";
import { BackendStatusWidget } from "./BackendStatusWidget";
import { PerformanceWidget } from "./PerformanceWidget";

let registered = false;

/**
 * Registers every core (first-party) widget. Idempotent — safe to call from
 * both `App.tsx` and any test harness that mounts widgets in isolation.
 * Third-party plugin widgets (Phase 5+) register through the same
 * `WidgetRegistry.register` call from their own loader, never here.
 */
export function registerCoreWidgets(): void {
  if (registered) return;
  registered = true;

  WidgetRegistry.register({
    id: "core.backend-status",
    title: "Backend",
    component: BackendStatusWidget,
    defaultDock: "right",
    defaultSize: { width: 260, height: 160 },
  });

  WidgetRegistry.register({
    id: "core.performance",
    title: "Performance",
    component: PerformanceWidget,
    defaultDock: "right",
    defaultSize: { width: 260, height: 200 },
  });
}
