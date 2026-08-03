import { useEffect } from "react";
import { detectGpuCapabilities } from "../gpu/GpuCapabilities";
import { QualityScaler } from "../gpu/QualityScaler";
import { PerformanceMonitor } from "./PerformanceMonitor";
import { useJarvisStore } from "../../state/store";
import { createLogger } from "../logging/logger";

const logger = createLogger("PerformanceGovernor");

/**
 * Bridges the three performance subsystems (GPU capability detection, real
 * frame-time measurement, automatic quality scaling) into the zustand
 * store, so every widget/scene component just reads
 * `useJarvisStore(s => s.qualitySettings)` without knowing any of this
 * machinery exists. Mount exactly once, at the app root — see App.tsx.
 */
export function usePerformanceGovernor(enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;

    const capabilities = detectGpuCapabilities();
    useJarvisStore.getState().setGpuCapabilities(capabilities);

    const scaler = new QualityScaler(capabilities.tier);
    useJarvisStore.getState().setQualitySettings(scaler.getSettings());

    const unsubscribeScaler = scaler.onChange((settings) => {
      useJarvisStore.getState().setQualitySettings(settings);
    });

    const monitor = new PerformanceMonitor();
    const unsubscribeMonitor = monitor.subscribe((sample) => {
      useJarvisStore.getState().setFrameSample(sample.fps, sample.frameTimeMs);
      scaler.reportFrame(sample.fps);
    });
    monitor.start();

    logger.info("Performance governor active", { initialTier: capabilities.tier });

    return () => {
      monitor.stop();
      unsubscribeMonitor();
      unsubscribeScaler();
    };
  }, [enabled]);
}
