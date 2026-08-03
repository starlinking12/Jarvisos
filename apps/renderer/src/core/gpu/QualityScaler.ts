import type { GpuTier } from "../gpu/GpuCapabilities";
import { createLogger } from "../logging/logger";

const logger = createLogger("QualityScaler");

export type QualityTier = "low" | "medium" | "high" | "ultra";

export interface QualitySettings {
  tier: QualityTier;
  particleCount: number;
  bloomEnabled: boolean;
  shadowsEnabled: boolean;
  resolutionScale: number; // multiplies devicePixelRatio for the R3F canvas
  antialias: boolean;
}

const QUALITY_LADDER: QualityTier[] = ["low", "medium", "high", "ultra"];

const SETTINGS_BY_TIER: Record<QualityTier, Omit<QualitySettings, "tier">> = {
  low: { particleCount: 150, bloomEnabled: false, shadowsEnabled: false, resolutionScale: 0.75, antialias: false },
  medium: { particleCount: 400, bloomEnabled: true, shadowsEnabled: false, resolutionScale: 1.0, antialias: true },
  high: { particleCount: 900, bloomEnabled: true, shadowsEnabled: true, resolutionScale: 1.0, antialias: true },
  ultra: { particleCount: 1800, bloomEnabled: true, shadowsEnabled: true, resolutionScale: 1.25, antialias: true },
};

function tierFromGpu(gpuTier: GpuTier): QualityTier {
  switch (gpuTier) {
    case "low":
      return "low";
    case "medium":
      return "medium";
    case "high":
      return "high";
  }
}

const TARGET_FPS = 60;
const DOWNGRADE_THRESHOLD_FPS = 48; // sustained below this -> step down
const UPGRADE_THRESHOLD_FPS = 58; // sustained above this -> step up
const HYSTERESIS_SAMPLES = 90; // ~1.5s at 60fps before acting, avoids flapping

/**
 * Adapts render quality at runtime based on a rolling average of measured
 * frame times from `PerformanceMonitor`. Starts from a GPU-capability-based
 * tier and steps up/down the quality ladder with hysteresis so a single
 * slow frame (GC pause, tab switch) never causes visible quality thrashing.
 */
export class QualityScaler {
  private tierIndex: number;
  private consecutiveLowSamples = 0;
  private consecutiveHighSamples = 0;
  private readonly listeners = new Set<(settings: QualitySettings) => void>();

  constructor(initialGpuTier: GpuTier) {
    const startTier = tierFromGpu(initialGpuTier);
    this.tierIndex = QUALITY_LADDER.indexOf(startTier);
    logger.info("Quality scaler initialized", { startTier });
  }

  public getSettings(): QualitySettings {
    const tier = QUALITY_LADDER[this.tierIndex]!;
    return { tier, ...SETTINGS_BY_TIER[tier] };
  }

  public onChange(listener: (settings: QualitySettings) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Feed a single frame's instantaneous FPS reading. */
  public reportFrame(fps: number): void {
    if (fps < DOWNGRADE_THRESHOLD_FPS) {
      this.consecutiveLowSamples += 1;
      this.consecutiveHighSamples = 0;
    } else if (fps > UPGRADE_THRESHOLD_FPS) {
      this.consecutiveHighSamples += 1;
      this.consecutiveLowSamples = 0;
    } else {
      this.consecutiveLowSamples = 0;
      this.consecutiveHighSamples = 0;
    }

    if (this.consecutiveLowSamples >= HYSTERESIS_SAMPLES) {
      this.stepDown();
      this.consecutiveLowSamples = 0;
    } else if (this.consecutiveHighSamples >= HYSTERESIS_SAMPLES * 2) {
      // Upgrading is more conservative than downgrading — prefer stable
      // lower quality over oscillation.
      this.stepUp();
      this.consecutiveHighSamples = 0;
    }
  }

  private stepDown(): void {
    if (this.tierIndex === 0) return;
    this.tierIndex -= 1;
    this.notify();
  }

  private stepUp(): void {
    if (this.tierIndex === QUALITY_LADDER.length - 1) return;
    this.tierIndex += 1;
    this.notify();
  }

  private notify(): void {
    const settings = this.getSettings();
    logger.info("Quality tier changed", { tier: settings.tier, targetFps: TARGET_FPS });
    for (const listener of this.listeners) listener(settings);
  }
}
