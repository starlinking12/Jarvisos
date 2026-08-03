import { motionTokens } from "../theme/tokens";

type EasingCurve = readonly [number, number, number, number];

export interface AnimateOptions {
  from: number;
  to: number;
  /** Seconds. Defaults to `motionTokens.duration.base`. */
  duration?: number;
  easing?: EasingCurve;
  onUpdate: (value: number) => void;
  onComplete?: () => void;
}

/**
 * See ADR-0006. `AnimationEngine` handles animations that must be
 * coordinated OUTSIDE a single React component's lifecycle or a single R3F
 * `useFrame` — e.g. a docking panel sliding to a new zone while its widget
 * unmounts from one container and mounts into another, or a HUD-wide
 * "alert" pulse triggered by a backend security event. For animations fully
 * contained within one component's render output, prefer Framer Motion
 * (declarative, React-idiomatic). For per-frame 3D object animation inside
 * the R3F tree, prefer `useFrame` directly. This engine is the third
 * category: cross-cutting, store-triggered, imperative motion.
 *
 * Every animation is keyed by `target` — starting a new animation for a
 * target that's already animating cancels the previous one, so rapid state
 * changes (e.g. toggling a panel twice quickly) never fight each other or
 * leak rAF callbacks.
 */
export class AnimationEngine {
  private readonly active = new Map<string, { rafHandle: number }>();

  public animate(target: string, options: AnimateOptions): void {
    this.cancel(target);

    const duration = options.duration ?? motionTokens.duration.base;
    const easing = options.easing ?? motionTokens.easing.settle;
    const startTime = performance.now();
    const durationMs = duration * 1000;

    const step = (now: number): void => {
      const elapsed = now - startTime;
      const t = durationMs <= 0 ? 1 : Math.min(elapsed / durationMs, 1);
      const eased = cubicBezierEase(t, easing);
      const value = options.from + (options.to - options.from) * eased;
      options.onUpdate(value);

      if (t >= 1) {
        this.active.delete(target);
        options.onComplete?.();
        return;
      }

      const rafHandle = requestAnimationFrame(step);
      this.active.set(target, { rafHandle });
    };

    const rafHandle = requestAnimationFrame(step);
    this.active.set(target, { rafHandle });
  }

  public cancel(target: string): void {
    const running = this.active.get(target);
    if (running) {
      cancelAnimationFrame(running.rafHandle);
      this.active.delete(target);
    }
  }

  public cancelAll(): void {
    for (const target of this.active.keys()) this.cancel(target);
  }

  public isAnimating(target: string): boolean {
    return this.active.has(target);
  }
}

/**
 * Evaluates a cubic-bezier easing curve at `t` using Newton-Raphson
 * iteration on the x(t) parametric curve to find the matching parameter,
 * then evaluates y at that parameter — the same approach browsers use for
 * CSS `cubic-bezier()`, reimplemented here so AnimationEngine produces
 * frame values matching the CSS transitions defined with the same tokens.
 */
function cubicBezierEase(t: number, [x1, y1, x2, y2]: EasingCurve): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;

  const sampleCurveX = (u: number) =>
    3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u ** 2 * x2 + u ** 3;
  const sampleCurveY = (u: number) =>
    3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u ** 2 * y2 + u ** 3;
  const sampleCurveDerivativeX = (u: number) =>
    3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1) + 3 * u ** 2 * (1 - x2);

  let u = t;
  for (let i = 0; i < 8; i += 1) {
    const x = sampleCurveX(u) - t;
    const derivative = sampleCurveDerivativeX(u);
    if (Math.abs(derivative) < 1e-6) break;
    u -= x / derivative;
  }

  return sampleCurveY(Math.min(Math.max(u, 0), 1));
}

export const animationEngine = new AnimationEngine();
