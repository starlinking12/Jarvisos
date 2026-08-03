import type { StateCreator } from "zustand";
import type { QualitySettings } from "../../core/gpu/QualityScaler";
import type { GpuCapabilities } from "../../core/gpu/GpuCapabilities";

export interface PerformanceSlice {
  fps: number;
  frameTimeMs: number;
  gpuCapabilities: GpuCapabilities | null;
  qualitySettings: QualitySettings;
  performanceOverlayVisible: boolean;
  setFrameSample: (fps: number, frameTimeMs: number) => void;
  setGpuCapabilities: (capabilities: GpuCapabilities) => void;
  setQualitySettings: (settings: QualitySettings) => void;
  togglePerformanceOverlay: () => void;
}

const DEFAULT_QUALITY: QualitySettings = {
  tier: "medium",
  particleCount: 400,
  bloomEnabled: true,
  shadowsEnabled: false,
  resolutionScale: 1,
  antialias: true,
};

export const createPerformanceSlice: StateCreator<
  PerformanceSlice,
  [["zustand/subscribeWithSelector", never]],
  [],
  PerformanceSlice
> = (set) => ({
  fps: 60,
  frameTimeMs: 16.67,
  gpuCapabilities: null,
  qualitySettings: DEFAULT_QUALITY,
  performanceOverlayVisible: false,

  // NOTE: this fires up to ~10x/sec from PerformanceMonitor's EMA, not every
  // frame — components that render FPS text should still select narrowly
  // (`useJarvisStore(s => s.fps)`) so unrelated state changes don't cause
  // them to re-render, and vice versa.
  setFrameSample: (fps, frameTimeMs) => set({ fps, frameTimeMs }),

  setGpuCapabilities: (capabilities) => set({ gpuCapabilities: capabilities }),

  setQualitySettings: (settings) => set({ qualitySettings: settings }),

  togglePerformanceOverlay: () =>
    set((state) => ({ performanceOverlayVisible: !state.performanceOverlayVisible })),
});
