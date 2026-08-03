import { useEffect, useState } from "react";
import { ThemeProvider } from "./theme/ThemeProvider";
import { ErrorBoundary } from "./core/errors/ErrorBoundary";
import { usePerformanceGovernor } from "./core/performance/usePerformanceGovernor";
import { EventBusClient } from "./core/events/EventBusClient";
import { invokeJarvis, isElectronHost } from "./core/ipc/jarvisBridge";
import { useJarvisStore } from "./state/store";
import { createLogger } from "./core/logging/logger";
import { HudRoot } from "./routes/HudRoot";
import { OverlayRoot } from "./routes/OverlayRoot";
import { SettingsRoot } from "./routes/SettingsRoot";
import { CommandPaletteRoot } from "./routes/CommandPaletteRoot";

const logger = createLogger("App");

type Route = "hud" | "overlay" | "settings" | "command-palette";

function resolveRoute(): Route {
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.startsWith("/overlay")) return "overlay";
  if (hash.startsWith("/settings")) return "settings";
  if (hash.startsWith("/command-palette")) return "command-palette";
  return "hud";
}

const BACKEND_PORT = Number(import.meta.env.VITE_JARVIS_BACKEND_PORT ?? 8137);
const EVENT_BUS_URL = `ws://127.0.0.1:${BACKEND_PORT}/ws/events`;

const BACKEND_STATUS_POLL_MS = 3000;

/**
 * Root component, mounted once per BrowserWindow. Each window (HUD,
 * overlay, settings, command palette) is a distinct Vite/Electron load of
 * the same bundle, differentiated only by the URL hash WindowManager sets
 * when loading it — see `WindowManager.loadRoute` / `OverlayWindow.load` in
 * the shell. This keeps exactly one renderer bundle to build and cache,
 * per ADR-0001's "no duplicated logic across subsystems" rule.
 */
export function App() {
  const [route] = useState<Route>(resolveRoute);
  const isScene = route === "hud" || route === "overlay";

  usePerformanceGovernor(isScene);
  useEventBusConnection();
  useBackendStatusPolling();
  usePreferencesHydration(route);

  return (
    <ThemeProvider>
      <ErrorBoundary boundaryName={`Route:${route}`}>
        {route === "hud" && <HudRoot />}
        {route === "overlay" && <OverlayRoot />}
        {route === "settings" && <SettingsRoot />}
        {route === "command-palette" && <CommandPaletteRoot />}
      </ErrorBoundary>
    </ThemeProvider>
  );
}

function usePreferencesHydration(route: Route): void {
  useEffect(() => {
    void (async () => {
      await useJarvisStore.getState().hydratePreferences();
      const {
        performanceOverlayVisibleDefault,
        overlayClickThroughDefault,
        performanceOverlayVisible,
        togglePerformanceOverlay,
        clickThrough,
        toggleClickThrough,
      } = useJarvisStore.getState();

      // Applying a persisted default only ever changes runtime state when
      // it actually differs — never forces an unnecessary IPC round trip
      // or toggle animation on windows where the value already matches.
      if (performanceOverlayVisibleDefault !== performanceOverlayVisible) {
        togglePerformanceOverlay();
      }
      if (route === "overlay" && overlayClickThroughDefault !== clickThrough) {
        void toggleClickThrough();
      }
    })();
  }, [route]);
}

function useEventBusConnection(): void {
  useEffect(() => {
    const client = new EventBusClient(EVENT_BUS_URL);

    const unsubscribeState = client.onConnectionStateChange((state) => {
      useJarvisStore.getState().setEventBusConnectionState(state);
    });

    const unsubscribeHealth = client.on("backend.health", (event) => {
      useJarvisStore
        .getState()
        .setBackendStatus(
          event.payload.status === "ok" ? "ready" : "degraded",
          event.payload.uptimeMs,
          useJarvisStore.getState().backendRestartCount,
        );
    });

    client.connect();
    logger.info("Event bus client connecting", { url: EVENT_BUS_URL });

    return () => {
      unsubscribeState();
      unsubscribeHealth();
      client.disconnect();
    };
  }, []);
}

function useBackendStatusPolling(): void {
  useEffect(() => {
    if (!isElectronHost()) {
      logger.warn("Not running inside Electron — backend status polling disabled");
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const status = await invokeJarvis("backend.status", undefined);
        if (!cancelled) {
          useJarvisStore.getState().setBackendStatus(status.status, status.uptimeMs, status.restartCount);
        }
      } catch (error) {
        logger.error("Backend status poll failed", { error: String(error) });
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), BACKEND_STATUS_POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);
}
