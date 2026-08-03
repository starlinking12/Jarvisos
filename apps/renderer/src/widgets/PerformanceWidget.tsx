import { useJarvisStore } from "../state/store";
import { colorTokens } from "../theme/tokens";

/**
 * Real-time FPS/frame-time/quality-tier readout. This is the visible face
 * of `PerformanceMonitor` + `QualityScaler` (core/performance,
 * core/gpu) — useful during development and, longer-term, as an optional
 * always-available diagnostics widget for end users troubleshooting
 * performance on their hardware.
 */
export function PerformanceWidget() {
  const fps = useJarvisStore((state) => state.fps);
  const frameTimeMs = useJarvisStore((state) => state.frameTimeMs);
  const quality = useJarvisStore((state) => state.qualitySettings);
  const gpu = useJarvisStore((state) => state.gpuCapabilities);

  const fpsColor =
    fps >= 55
      ? colorTokens.signal.success
      : fps >= 40
        ? colorTokens.signal.warning
        : colorTokens.signal.critical;

  return (
    <dl className="jarvis-kv-list">
      <div className="jarvis-kv-list__row">
        <dt>FPS</dt>
        <dd style={{ color: fpsColor }}>{fps.toFixed(0)}</dd>
      </div>
      <div className="jarvis-kv-list__row">
        <dt>Frame time</dt>
        <dd>{frameTimeMs.toFixed(2)} ms</dd>
      </div>
      <div className="jarvis-kv-list__row">
        <dt>Quality</dt>
        <dd>{quality.tier}</dd>
      </div>
      <div className="jarvis-kv-list__row">
        <dt>Particles</dt>
        <dd>{quality.particleCount}</dd>
      </div>
      <div className="jarvis-kv-list__row">
        <dt>GPU tier</dt>
        <dd>{gpu?.tier ?? "detecting…"}</dd>
      </div>
    </dl>
  );
}
