import type { ReactNode } from "react";
import { SceneCanvas } from "../three/SceneCanvas";
import { ArcReactorCore } from "../three/ArcReactorCore";
import { ParticleField } from "../three/ParticleField";
import { DockingLayout } from "./DockingLayout";

interface AppShellProps {
  /** Extra content rendered above the docking layout, e.g. command palette overlays. */
  children?: ReactNode;
}

/**
 * Composes the two visual layers every full window shares: the 3D scene
 * background (Arc Reactor + particle field, GPU-first, `pointerEvents: none`
 * so it never intercepts input) and the docking layout foreground where
 * widgets live. Overlay and Settings windows compose their own roots
 * directly rather than reusing this — the HUD is the only window with the
 * full reactor + docking experience.
 */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="jarvis-app-shell">
      <div className="jarvis-scene-background">
        <SceneCanvas>
          <ambientLight intensity={0.3} />
          <ArcReactorCore />
          <ParticleField />
        </SceneCanvas>
      </div>

      <DockingLayout />
      {children}
    </div>
  );
}
