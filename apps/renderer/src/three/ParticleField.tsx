import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useJarvisStore } from "../state/store";
import { colorTokens } from "../theme/tokens";

const FIELD_RADIUS = 6;

/**
 * Ambient background particles using a single `THREE.Points` object with a
 * per-vertex drift computed in `useFrame` — one draw call regardless of
 * count, and the buffer is allocated once at the maximum quality tier's
 * particle count then only partially drawn (`drawRange`) when the active
 * quality tier calls for fewer, so quality downgrades never reallocate
 * GPU buffers mid-session.
 */
export function ParticleField() {
  const pointsRef = useRef<THREE.Points>(null);
  const velocitiesRef = useRef<Float32Array | null>(null);

  const MAX_PARTICLES = 1800;

  const geometry = useRef<THREE.BufferGeometry>();
  if (!geometry.current) {
    const positions = new Float32Array(MAX_PARTICLES * 3);
    const velocities = new Float32Array(MAX_PARTICLES * 3);
    for (let i = 0; i < MAX_PARTICLES; i += 1) {
      const radius = FIELD_RADIUS * Math.cbrt(Math.random());
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);

      velocities[i * 3] = (Math.random() - 0.5) * 0.02;
      velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.02;
      velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.02;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.current = geo;
    velocitiesRef.current = velocities;
  }

  useFrame((_state, delta) => {
    const geo = geometry.current;
    const velocities = velocitiesRef.current;
    if (!geo || !velocities) return;

    const activeCount = useJarvisStore.getState().qualitySettings.particleCount;
    geo.setDrawRange(0, Math.min(activeCount, MAX_PARTICLES));

    const positionAttr = geo.getAttribute("position") as THREE.BufferAttribute;
    const positions = positionAttr.array as Float32Array;

    for (let i = 0; i < Math.min(activeCount, MAX_PARTICLES); i += 1) {
      const ix = i * 3;
      positions[ix] += velocities[ix]! * delta * 10;
      positions[ix + 1] += velocities[ix + 1]! * delta * 10;
      positions[ix + 2] += velocities[ix + 2]! * delta * 10;

      const distSq =
        positions[ix]! ** 2 + positions[ix + 1]! ** 2 + positions[ix + 2]! ** 2;
      if (distSq > FIELD_RADIUS ** 2) {
        // Recycle particles that drift out of the field back to the center
        // area, keeping density visually constant without ever growing the
        // buffer.
        positions[ix] *= 0.05;
        positions[ix + 1] *= 0.05;
        positions[ix + 2] *= 0.05;
      }
    }

    positionAttr.needsUpdate = true;

    if (pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.01;
    }
  });

  return (
    <points ref={pointsRef} geometry={geometry.current} frustumCulled={false}>
      <pointsMaterial
        color={colorTokens.signal.primary}
        size={0.02}
        sizeAttenuation
        transparent
        opacity={0.5}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
