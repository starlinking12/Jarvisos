import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { createBackendSlice, type BackendSlice } from "./slices/backendSlice";
import { createOverlaySlice, type OverlaySlice } from "./slices/overlaySlice";
import { createPerformanceSlice, type PerformanceSlice } from "./slices/performanceSlice";
import { createPreferencesSlice, type PreferencesSlice } from "./slices/preferencesSlice";
import { createUiSlice, type UiSlice } from "./slices/uiSlice";

/**
 * See ADR-0009 for the full rationale. Summary: one store, composed from
 * independent slices (one per subsystem), using the `subscribeWithSelector`
 * middleware so every consumer subscribes to a narrow selector rather than
 * the whole store. Zustand only re-renders a component when its selected
 * slice of state changes by reference, so `useJarvisStore(s => s.fps)`
 * never re-renders when `widgetInstances` changes, and vice versa — this is
 * what keeps "zero unnecessary re-renders" true as the store grows.
 *
 * New subsystems get a new slice file, composed here. Nothing about
 * existing slices changes when a new one is added — this is the store-level
 * expression of the "every subsystem must be replaceable" principle.
 * `PreferencesSlice` (Phase 4) is the first slice to prove this in
 * practice: it was added with zero changes to `BackendSlice`,
 * `OverlaySlice`, `PerformanceSlice`, or `UiSlice`.
 */
export type JarvisStore = BackendSlice &
  OverlaySlice &
  PerformanceSlice &
  PreferencesSlice &
  UiSlice;

export const useJarvisStore = create<JarvisStore>()(
  subscribeWithSelector((...args) => ({
    ...createBackendSlice(...args),
    ...createOverlaySlice(...args),
    ...createPerformanceSlice(...args),
    ...createPreferencesSlice(...args),
    ...createUiSlice(...args),
  })),
);

/**
 * Non-hook accessor for use outside React (event bus handlers, the
 * AnimationEngine, etc.) where calling a hook isn't valid.
 */
export function getJarvisState(): JarvisStore {
  return useJarvisStore.getState();
}
