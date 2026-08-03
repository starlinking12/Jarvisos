import { AnimatePresence, motion } from "framer-motion";
import { WidgetRegistry } from "./WidgetRegistry";
import { useJarvisStore } from "../state/store";
import { ErrorBoundary } from "../core/errors/ErrorBoundary";
import { motionTokens } from "../theme/tokens";
import type { WidgetInstance } from "../state/slices/uiSlice";

interface WidgetProps {
  instance: WidgetInstance;
}

/**
 * Chrome shared by every docked widget: glass panel styling, title bar,
 * collapse/close controls, and an error boundary isolating the widget's own
 * content from the rest of the HUD. `WidgetDefinition.component` renders
 * inside — it never needs to know about docking, collapse state, or chrome.
 *
 * Enter/exit is animated with Framer Motion (fully contained within this
 * component's own render output), consistent with `AnimationEngine`'s
 * division of labor documented in ADR-0006.
 */
export function Widget({ instance }: WidgetProps) {
  const definition = WidgetRegistry.get(instance.widgetId);
  const closeWidget = useJarvisStore((state) => state.closeWidget);
  const toggleCollapsed = useJarvisStore((state) => state.toggleWidgetCollapsed);

  if (!definition) {
    return null; // A widget instance referencing an unregistered id (e.g. a
    // plugin that failed to load) simply renders nothing rather than
    // crashing the dock — the plugin loader is responsible for surfacing
    // that failure elsewhere (Phase 5).
  }

  const Content = definition.component;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.98 }}
      transition={{
        duration: motionTokens.duration.base,
        ease: motionTokens.easing.settle,
      }}
      className="jarvis-glass-panel jarvis-holographic jarvis-widget"
      style={{ width: definition.defaultSize.width }}
    >
      <div className="jarvis-widget__titlebar">
        <span className="jarvis-widget__title">{definition.title}</span>
        <div className="jarvis-widget__actions">
          <button
            type="button"
            aria-label={instance.collapsed ? "Expand" : "Collapse"}
            onClick={() => toggleCollapsed(instance.instanceId)}
            className="jarvis-widget__action-button"
          >
            {instance.collapsed ? "+" : "–"}
          </button>
          <button
            type="button"
            aria-label="Close widget"
            onClick={() => closeWidget(instance.instanceId)}
            className="jarvis-widget__action-button"
          >
            ×
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {!instance.collapsed && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: motionTokens.duration.fast, ease: motionTokens.easing.standard }}
            className="jarvis-widget__content"
          >
            <ErrorBoundary boundaryName={`Widget:${definition.id}`}>
              <Content />
            </ErrorBoundary>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
