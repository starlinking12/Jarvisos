import { useJarvisStore } from "../state/store";
import { colorTokens } from "../theme/tokens";

const STATUS_COLOR: Record<string, string> = {
  ready: colorTokens.signal.success,
  starting: colorTokens.signal.secondary,
  degraded: colorTokens.signal.warning,
  crashed: colorTokens.signal.critical,
  stopped: colorTokens.text.tertiary,
};

/**
 * Displays live backend supervisor status (polled via IPC, updated by
 * `backend.health` events over the event bus) and the event-bus WebSocket
 * connection state. Selects each field narrowly so this widget only
 * re-renders when one of these specific values actually changes.
 */
export function BackendStatusWidget() {
  const status = useJarvisStore((state) => state.backendStatus);
  const uptimeMs = useJarvisStore((state) => state.backendUptimeMs);
  const restartCount = useJarvisStore((state) => state.backendRestartCount);
  const connectionState = useJarvisStore((state) => state.eventBusConnectionState);

  const uptimeLabel =
    uptimeMs === null ? "—" : `${Math.floor(uptimeMs / 60000)}m ${Math.floor((uptimeMs % 60000) / 1000)}s`;

  return (
    <dl className="jarvis-kv-list">
      <div className="jarvis-kv-list__row">
        <dt>Backend</dt>
        <dd style={{ color: STATUS_COLOR[status] ?? colorTokens.text.primary }}>{status}</dd>
      </div>
      <div className="jarvis-kv-list__row">
        <dt>Event bus</dt>
        <dd>{connectionState}</dd>
      </div>
      <div className="jarvis-kv-list__row">
        <dt>Uptime</dt>
        <dd>{uptimeLabel}</dd>
      </div>
      {restartCount > 0 && (
        <div className="jarvis-kv-list__row">
          <dt>Restarts</dt>
          <dd style={{ color: colorTokens.signal.warning }}>{restartCount}</dd>
        </div>
      )}
    </dl>
  );
}
