import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import "./HolographicMaterial";
import type { HolographicMaterialInstance } from "./HolographicMaterial";
import { useJarvisStore } from "../state/store";
import { colorTokens } from "../theme/tokens";

interface RingSpec {
  radius: number;
  tube: number;
  speed: number;
  color: string;
}

const RINGS: RingSpec[] = [
  { radius: 1.6, tube: 0.03, speed: 0.08, color: colorTokens.signal.primary },
  { radius: 1.3, tube: 0.02, speed: -0.14, color: colorTokens.signal.secondary },
  { radius: 1.0, tube: 0.025, speed: 0.22, color: colorTokens.signal.primary },
];

/**
 * The Arc Reactor core: three counter-rotating holographic rings around a
 * pulsing core sphere. This is the idle centerpiece of the HUD — it must
 * never look frozen (per the design philosophy) even with zero user
 * interaction, so its animation is entirely time-driven inside `useFrame`
 * rather than reacting to discrete state changes.
 *
 * Backend status subtly modulates the core's pulse rate: calm/slow when
 * `ready`, faster and slightly desaturated toward amber when `degraded` or
 * `crashed` — a genuine status indicator, not decoration. React never
 * re-renders for this; the status is read directly from the store inside
 * the frame loop and applied to material uniforms/mesh transforms.
 */
export function ArcReactorCore() {
  const groupRef = useRef<THREE.Group>(null);
  const coreMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const ringMaterialRefs = useRef<(HolographicMaterialInstance | null)[]>([]);

  const ringGeometries = useMemo(
    () => RINGS.map((ring) => new THREE.TorusGeometry(ring.radius, ring.tube, 16, 128)),
    [],
  );

  useFrame((state, delta) => {
    const backendStatus = useJarvisStore.getState().backendStatus;
    const isHealthy = backendStatus === "ready";
    const pulseRateMultiplier = isHealthy ? 1.0 : 2.2;

    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.05;
    }

    ringMaterialRefs.current.forEach((material, index) => {
      if (!material) return;
      material.uTime = state.clock.elapsedTime * pulseRateMultiplier;
      const ring = RINGS[index]!;
      material.uColor.set(isHealthy ? ring.color : colorTokens.signal.warning);
    });

    if (coreMaterialRef.current) {
      const pulse = 0.6 + 0.4 * Math.sin(state.clock.elapsedTime * pulseRateMultiplier * 0.8);
      coreMaterialRef.current.emissiveIntensity = pulse;
    }

    if (groupRef.current) {
      RINGS.forEach((ring, index) => {
        const mesh = groupRef.current!.children[index + 1] as THREE.Mesh | undefined;
        if (mesh) mesh.rotation.z += delta * ring.speed;
      });
    }
  });

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[0.55, 48, 48]} />
        <meshStandardMaterial
          ref={coreMaterialRef}
          color={colorTokens.signal.primary}
          emissive={colorTokens.signal.primary}
          emissiveIntensity={1}
          roughness={0.2}
          metalness={0.1}
          toneMapped={false}
        />
      </mesh>

      {RINGS.map((ring, index) => (
        <mesh key={ring.radius} geometry={ringGeometries[index]} rotation={[Math.PI / 2.4, 0, 0]}>
          <holographicMaterialImpl
            ref={(instance: HolographicMaterialInstance | null) => {
              ringMaterialRefs.current[index] = instance;
            }}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            side={THREE.DoubleSide}
          />
        </mesh>
      ))}

      <pointLight color={colorTokens.signal.primary} intensity={2.2} distance={4} decay={2} />
    </group>
  );
}
