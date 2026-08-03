# ADR-0009: Slice-Composed Zustand Store with Narrow Selector Subscriptions

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 1 — Renderer Foundation

## Context

The renderer must support "zero unnecessary React re-renders" as a hard
performance requirement, on top of a state surface that will keep growing
as new subsystems land (backend status, overlay state, GPU/performance
telemetry, docking layout today; agent task state, memory search, security
alerts, business-intelligence dashboards in later phases). The state
solution needs to (a) scale to many independent subsystems without one
growing "god store" file, and (b) guarantee that a change in one
subsystem's state never re-renders a component that only cares about a
different subsystem.

## Decision

A single Zustand store (`state/store.ts`), composed from independent
**slices** — one file per subsystem
(`slices/backendSlice.ts`, `slices/overlaySlice.ts`,
`slices/performanceSlice.ts`, `slices/uiSlice.ts`), combined with Zustand's
standard slice pattern (`StateCreator<Slice, [...], [], Slice>`, spread
together in `create()`). The store is wrapped in the
`subscribeWithSelector` middleware, and every component subscribes with a
**narrow selector** — `useJarvisStore(state => state.fps)`, never
`useJarvisStore(state => state)` — so Zustand's shallow reference check on
the selected value, not the whole store, determines whether the component
re-renders.

Non-React code (the `AnimationEngine`, `EventBusClient` handlers, the
`usePerformanceGovernor` hook's internals) reads/writes via
`useJarvisStore.getState()` / `useJarvisStore.setState()` directly, never
via the hook, since hooks are only valid inside React components.

## Rationale

- **Slices scale linearly, not combinatorially.** Adding the Memory
  subsystem's state in Phase 4 means adding `slices/memorySlice.ts` and one
  line in `store.ts`'s composition — no existing slice file changes, no
  existing selector breaks.
- **Selector-based subscriptions are the actual re-render guarantee.**
  Zustand (unlike Context) only notifies a component when its selected
  value changes by reference/equality — this is what makes "the FPS counter
  updates 10x/second without re-rendering the docking layout" true in
  practice, not just in intent. This is why the project convention is:
  every `useJarvisStore` call site selects the narrowest possible slice of
  state, never the whole store or even a whole slice object when a single
  field will do.
- **One store, not one-store-per-subsystem.** Multiple independent Zustand
  stores were considered and rejected: cross-subsystem reads (e.g. a widget
  that needs both `backendStatus` and `qualitySettings`) would require
  importing multiple store hooks with no unified mental model, and
  `getState()` snapshots used by non-React code would need to be composed
  manually at every call site.

## Consequences

- Every new slice must declare its `StateCreator` generic exactly as the
  existing ones do (`[["zustand/subscribeWithSelector", never]]` middleware
  tuple) — mismatched slice typing silently breaks TypeScript's inference
  for the combined store type.
- Code review should flag any `useJarvisStore(state => state)` or
  whole-slice-object selection where a narrower selector would do; this is
  a performance regression, not a style preference.
- Persistence (Phase 4, once the Memory subsystem exists) will be added as
  a Zustand middleware wrapping the existing composed store, not as a
  parallel state mechanism.

## Alternatives Considered

- **React Context per subsystem:** rejected — Context re-renders every
  consumer on any change to the provided value by default, which is the
  exact problem this ADR exists to avoid; achieving selector-level
  granularity with Context requires hand-rolling something that is
  functionally a worse version of Zustand.
- **Redux Toolkit:** rejected for Phase 1 — more boilerplate
  (actions/reducers/selectors as separate concerns) for no capability this
  project needs yet; Zustand's slice pattern already gives modular,
  independently-ownable state without it. Revisit only if a future phase
  needs Redux-specific tooling (time-travel debugging, middleware
  ecosystem) that Zustand genuinely lacks.
