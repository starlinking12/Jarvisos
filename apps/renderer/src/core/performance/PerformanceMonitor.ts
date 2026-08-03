import { createLogger } from "../logging/logger";

const logger = createLogger("PerformanceMonitor");

export interface FrameSample {
  fps: number;
  frameTimeMs: number;
  timestamp: number;
}

export type FrameListener = (sample: FrameSample) => void;

/**
 * Measures real frame time using `requestAnimationFrame`, independent of
 * React's render/commit cycle — React re-renders are not a proxy for actual
 * GPU/compositor performance, especially once the R3F canvas is doing most
 * of the work outside React's tree. This is the single source of truth that
 * `QualityScaler` and the performance HUD widget both subscribe to.
 *
 * Uses an exponential moving average to smooth instantaneous frame-to-frame
 * noise while still reacting quickly to sustained changes.
 */
export class PerformanceMonitor {
  private rafHandle: number | null = null;
  private lastTimestamp: number | null = null;
  private emaFrameTimeMs = 1000 / 60;
  private readonly emaAlpha = 0.1;
  private readonly listeners = new Set<FrameListener>();

  public start(): void {
    if (this.rafHandle !== null) return;
    logger.info("Performance monitor started");
    this.rafHandle = requestAnimationFrame(this.tick);
  }

  public stop(): void {
    if (this.rafHandle !== null) {
      cancelAnimationFrame(this.rafHandle);
      this.rafHandle = null;
    }
    this.lastTimestamp = null;
    logger.info("Performance monitor stopped");
  }

  public subscribe(listener: FrameListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private tick = (timestamp: number): void => {
    if (this.lastTimestamp !== null) {
      const delta = timestamp - this.lastTimestamp;
      // Ignore absurd deltas (tab was backgrounded / debugger paused) so a
      // single stall doesn't skew the moving average or trigger a false
      // quality downgrade.
      if (delta > 0 && delta < 1000) {
        this.emaFrameTimeMs =
          this.emaAlpha * delta + (1 - this.emaAlpha) * this.emaFrameTimeMs;

        const sample: FrameSample = {
          fps: 1000 / this.emaFrameTimeMs,
          frameTimeMs: this.emaFrameTimeMs,
          timestamp,
        };
        for (const listener of this.listeners) listener(sample);
      }
    }
    this.lastTimestamp = timestamp;
    this.rafHandle = requestAnimationFrame(this.tick);
  };
}
