import { SceneCanvas } from "../three/SceneCanvas";
import { ParticleField } from "../three/ParticleField";
import { useJarvisStore } from "../state/store";

/**
 * The overlay window's content: ambient particles drifting over the whole
 * desktop, plus a small corner affordance for toggling click-through mode
 * (see OverlayWindow.ts / overlaySlice.ts). Everything except the toggle
 * button has `pointerEvents: none` so it never blocks interaction with
 * whatever the user is doing on the desktop underneath — click-through is
 * the overlay's default and near-permanent state.
 */
export function OverlayRoot() {
  const clickThrough = useJarvisStore((state) => state.clickThrough);
  const toggleClickThrough = useJarvisStore((state) => state.toggleClickThrough);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <SceneCanvas cameraPosition={[0, 0, 6]}>
        <ambientLight intensity={0.2} />
        <ParticleField />
      </SceneCanvas>

      <button
        type="button"
        onClick={() => void toggleClickThrough()}
        className="jarvis-glass-panel jarvis-overlay-toggle"
        style={{ pointerEvents: "auto" }}
        aria-pressed={!clickThrough}
      >
        {clickThrough ? "Click-through: ON" : "Click-through: OFF"}
      </button>
    </div>
  );
}
