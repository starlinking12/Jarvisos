# ADR-0006: Three-Tier Animation Architecture

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 1 — Renderer Foundation

## Context

The design philosophy mandates that JARVIS OS "feel alive": every animation
communicates state, nothing appears or disappears abruptly, and easing must
be intentional and consistent everywhere — a docking panel, a HUD alert
pulse, and a 3D ring rotation should all feel like they belong to the same
physical system. The renderer has three genuinely different kinds of motion
to support, and using one tool for all of them either fights React's render
model or fights the 3D frame loop.

## Decision

Three animation mechanisms are used, each for a distinct category of
motion, unified only by shared tokens (`theme/tokens.ts` →
`motionTokens.duration` / `motionTokens.easing`):

1. **Framer Motion** — for animations fully contained within one React
   component's own render output: a widget entering/leaving the DOM, a
   panel's collapse/expand height transition, list reordering. Declarative,
   React-idiomatic, automatically handles exit animations via
   `AnimatePresence`.
2. **`useFrame` (React Three Fiber)** — for per-frame animation of objects
   already inside the R3F scene tree: the Arc Reactor's rotation and pulse,
   particle drift. Runs inside R3F's own render loop, colocated with the
   3D object it animates.
3. **`AnimationEngine`** (`three/AnimationEngine.ts`) — for animation that
   must be triggered imperatively from OUTSIDE any single component's
   lifecycle: a store action or an incoming backend event driving a
   cross-cutting visual change (e.g., a HUD-wide alert pulse triggered by a
   `security.alert` event, or a panel that needs to animate while
   simultaneously unmounting from one docking zone and mounting into
   another). Keyed by a `target` string so restarting an animation for the
   same target cancels the previous one — rapid-fire state changes never
   fight each other or leak `requestAnimationFrame` callbacks.

All three read the same `motionTokens.easing` cubic-bezier tuples.
`AnimationEngine` reimplements the bezier evaluation itself (Newton-Raphson
on the parametric curve, matching how browsers evaluate CSS
`cubic-bezier()`) specifically so its output matches what the same token
produces as a CSS transition — a "settle" curve looks and feels identical
whether it's animating a DOM element's opacity or a `THREE.Object3D`'s
material uniform.

## Rationale

- **Right tool per render target.** Framer Motion cannot animate `THREE.*`
  objects; `useFrame` has no concept of component mount/unmount and would
  require manual bookkeeping to survive a widget moving between docking
  zones; neither has a clean answer for "animate this in response to an
  event with no associated component." Three tools, three non-overlapping
  jobs — no logic duplication because no two of them solve the same
  problem.
- **Single token source prevents visual drift.** Without unified tokens,
  three animation systems easily accrete three different "house styles"
  over time. Every duration and curve traces back to one file.

## Consequences

- Any new animation need is a routing decision, not a new mechanism:
  "does this live entirely inside one component's render? → Framer Motion.
  Is it a per-frame 3D object update? → `useFrame`. Does it cross component
  boundaries or originate from the store/event bus? → `AnimationEngine`."
- `AnimationEngine` is a plain class, not a React hook, deliberately — it
  must be callable from non-component code (store actions, event bus
  handlers) without violating the rules of hooks.

## Alternatives Considered

- **GSAP for everything:** rejected — would still need a separate
  React-lifecycle-aware layer for enter/exit animations (GSAP has no
  built-in concept of "this DOM node is about to unmount"), so it wouldn't
  actually collapse to one mechanism; it would just replace
  `AnimationEngine`'s bezier math with a heavier dependency for no
  architectural simplification.
- **Framer Motion's `useAnimationControls` for cross-component
  coordination:** rejected for the store/event-triggered case — it still
  requires each participating component to hold a controls ref and wire it
  up, which reintroduces the coupling `AnimationEngine`'s target-keyed,
  fire-and-forget API avoids.
