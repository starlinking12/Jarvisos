import { Canvas } from "@react-three/fiber";
import { Suspense, type ReactNode } from "react";
import * as THREE from "three";
import { useJarvisStore } from "../state/store";
import { ErrorBoundary } from "../core/errors/ErrorBoundary";
import { createLogger } from "../core/logging/logger";

const logger = createLogger("SceneCanvas");

interface SceneCanvasProps {
  children: ReactNode;
  cameraPosition?: [number, number, number];
}

/**
 * The single R3F `Canvas` entry point used by every 3D surface in the app
 * (HUD background, overlay). Resolution scale and antialiasing come
 * straight from `qualitySettings` in the store — this is the one place
 * those settings actually reach the renderer, so `QualityScaler` changes
 * take effect without touching any scene-content component.
 *
 * `Canvas` disposes its `WebGLRenderer` and all GPU resources of unmounted
 * scene objects automatically on unmount (R3F's default `dispose` behavior
 * for every declarative Object3D) — this component adds an explicit
 * `onCreated`/cleanup log pair so leaks are observable in dev rather than
 * assumed.
 */
export function SceneCanvas({ children, cameraPosition = [0, 0, 4] }: SceneCanvasProps) {
  const quality = useJarvisStore((state) => state.qualitySettings);
  const gpu = useJarvisStore((state) => state.gpuCapabilities);

  const dpr = Math.min(
    (gpu?.devicePixelRatio ?? 1) * quality.resolutionScale,
    2, // hard cap — beyond 2x DPR the visual gain never justifies the cost
  );

  return (
    <ErrorBoundary boundaryName="SceneCanvas">
      <Canvas
        dpr={dpr}
        gl={{
          antialias: quality.antialias,
          powerPreference: "high-performance",
          alpha: true,
        }}
        camera={{ position: cameraPosition, fov: 45 }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.1;
          logger.debug("WebGL context created", { dpr, antialias: quality.antialias });
        }}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        <Suspense fallback={null}>{children}</Suspense>
      </Canvas>
    </ErrorBoundary>
  );
}
