import * as THREE from "three";
import { extend, type ReactThreeFiber } from "@react-three/fiber";
import { shaderMaterial } from "@react-three/drei";

/**
 * A restrained holographic material: fresnel-driven rim brightening (so
 * geometry reads as "energy" rather than solid plastic) plus a slow-moving
 * horizontal scanline. Deliberately subtle — intensity and scanline opacity
 * are low by default; this is meant to feel like an aerospace instrument
 * readout, not a sci-fi movie prop.
 */
const HolographicMaterialImpl = shaderMaterial(
  {
    uTime: 0,
    uColor: new THREE.Color("#4fd8ff"),
    uOpacity: 0.85,
    uFresnelPower: 2.2,
    uScanlineSpeed: 0.35,
    uScanlineDensity: 18.0,
    uPulse: 1.0,
  },
  /* vertex shader */ `
    varying vec3 vNormal;
    varying vec3 vViewDir;
    varying vec2 vUv;

    void main() {
      vUv = uv;
      vec4 worldPosition = modelMatrix * vec4(position, 1.0);
      vec4 viewPosition = viewMatrix * worldPosition;
      vNormal = normalize(normalMatrix * normal);
      vViewDir = normalize(-viewPosition.xyz);
      gl_Position = projectionMatrix * viewPosition;
    }
  `,
  /* fragment shader */ `
    uniform float uTime;
    uniform vec3 uColor;
    uniform float uOpacity;
    uniform float uFresnelPower;
    uniform float uScanlineSpeed;
    uniform float uScanlineDensity;
    uniform float uPulse;

    varying vec3 vNormal;
    varying vec3 vViewDir;
    varying vec2 vUv;

    void main() {
      float fresnel = pow(1.0 - clamp(dot(normalize(vNormal), normalize(vViewDir)), 0.0, 1.0), uFresnelPower);

      float scan = sin((vUv.y * uScanlineDensity) - uTime * uScanlineSpeed * 6.2831853);
      float scanline = smoothstep(0.85, 1.0, scan) * 0.25;

      float breathing = 0.85 + 0.15 * sin(uTime * 0.6) * uPulse;

      vec3 color = uColor * (0.35 + fresnel * 1.4 + scanline) * breathing;
      float alpha = uOpacity * (0.25 + fresnel * 0.9 + scanline);

      gl_FragColor = vec4(color, clamp(alpha, 0.0, 1.0));
    }
  `,
);

extend({ HolographicMaterialImpl });

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace -- required
  // shape for augmenting R3F v8's JSX intrinsic element catalogue.
  namespace JSX {
    interface IntrinsicElements {
      holographicMaterialImpl: ReactThreeFiber.Object3DNode<
        InstanceType<typeof HolographicMaterialImpl>,
        typeof HolographicMaterialImpl
      >;
    }
  }
}

export { HolographicMaterialImpl };
export type HolographicMaterialInstance = InstanceType<typeof HolographicMaterialImpl>;
