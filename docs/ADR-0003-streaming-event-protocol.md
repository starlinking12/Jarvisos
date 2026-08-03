# ADR-0003: Streaming Protocol & the `ai.*`/`agent.*` Event Sequence

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 2 — Orchestrator + Agent Core + ModelRouter

## Context

Phase 1's event bus (ADR-0001, extended by the Phase 1 renderer↔backend
WebSocket refinement) already carries UI-facing telemetry
(`backend.health`, `orchestrator.message`, the coarse `agent.taskUpdate`).
Phase 2 introduces real AI calls and real agent task execution, both of
which need to be observable in real time — a streaming chat response must
render token-by-token in the HUD, and a multi-step agent task must be
visible as it plans and executes, not just as a final result. This
requires a larger, precisely-defined event vocabulary and an unambiguous
answer to "which component publishes which event, in what order."

## Decision

Nine new event types, defined identically in `events.ts` and `events.py`
(same discipline as every event since ADR-0001):

- `ai.request`, `ai.token`, `ai.response` — one model call's lifecycle.
  Published exclusively by `ModelRouter` (see ADR-0002) — no other
  component publishes these, so every model call in the system is
  observable the same way regardless of which subsystem triggered it.
- `agent.task.created`, `agent.plan`, `agent.step`, `agent.observe`,
  `agent.complete`, `agent.error` — one agent task's lifecycle. Published
  by `Orchestrator` (task/plan/step/complete/error) and `ToolExecutor`
  (observe) — see ADR-0008 for why those two components specifically.

**Ordering guarantee** for one task: `agent.task.created` always precedes
`agent.plan`; each `agent.step` (status=running) precedes its
`agent.observe`; the final `agent.step` sequence precedes
`orchestrator.message` (the actual response); `agent.complete` (or
`agent.error`) is always last. This is enforced by `Orchestrator`'s
strictly sequential `await`-based lifecycle (`handle_user_message`) — there
is no concurrent step execution in Phase 2, so no ordering race is
possible. (Concurrent step execution, if added in a later phase, would
need to revisit this guarantee explicitly.)

**Streaming**, concretely: `ModelRouter.stream()` is an async generator
yielding text deltas. For every delta, it publishes `ai.token` (one event
per token/chunk) *before* yielding to the caller. The caller
(`Orchestrator._synthesize_response`) re-publishes each delta as an
`orchestrator.message` event with `done: false`, then a final
`orchestrator.message` with `done: true` and an empty delta once the
stream ends. **Two distinct streaming events exist on purpose**:
`ai.token` is raw model-call telemetry (useful for a debug widget showing
literal token-by-token generation, or future latency-per-token metrics);
`orchestrator.message` is the user-facing chat stream. They are not
merged into one event because their consumers and lifetimes differ — a
`toolcall` or `summarize` task also produces `ai.token` events but never
produces `orchestrator.message` (only `chat`-task responses are shown to
the user, per the "only the Orchestrator communicates with the user"
rule — see ADR-0008).

**Correlation.** Every `agent.*` event for one task carries that task's
`taskId`. Every `ai.*` event carries a `requestId` (unique per model call)
and, when the call is part of an agent task, that task's `taskId` too — so
a HUD debug view can filter "every model call and every agent event
belonging to task X" from a single field, without needing a separate
correlation mechanism. Backend-side logs use the same `task_id` as
structlog's `correlation_id` contextvar (bound for the duration of
`Orchestrator.handle_user_message`), so logs and events share one
identifier end to end.

## Rationale

- **Fine-grained `agent.*` events alongside the coarse `agent.taskUpdate`
  from Phase 0/1, not replacing it:** `agent.taskUpdate` is a single
  rolling summary a HUD status widget can show without needing to
  understand plan/step/observe semantics at all (see
  `BackendStatusWidget` from Phase 1). The new events are what a *debug or
  audit* view needs — the full plan, every step's status transition, every
  observation. Collapsing these into one event type would force every
  consumer to either parse a complex payload for simple display needs, or
  lose the detail an audit view requires. Two granularities, two event
  families, no overlap in payload shape.
- **Publishing discipline (one component per event type) is what makes the
  ordering guarantee provable.** If any domain agent could publish
  `agent.step` directly, the strict sequencing `Orchestrator` provides
  would no longer hold, and consumers couldn't rely on event order at all.

## Consequences

- Any future event type follows the same rule stated here: exactly one
  component in the codebase is the publisher, stated in that event's ADR
  or its docstring, and code review enforces it.
- A HUD "agent activity" panel (not yet built — a natural Phase 3+ widget)
  can be built purely by subscribing to `agent.*` events filtered by
  `taskId`, with no additional backend API needed.
- `ai.token` volume is high-frequency (proportional to token count per
  response). The renderer's `EventBusClient` (Phase 1) already validates
  and fans out every event by type with no per-type special-casing, so no
  renderer-side change was needed to support this — new event types are
  purely additive to that layer, confirming the Phase 1 event-bus design
  scales to Phase 2's needs unmodified.

## Alternatives Considered

- **Single `ai.stream` event with a `kind` discriminator field instead of
  three separate types (`ai.request`/`ai.token`/`ai.response`):** rejected
  — the three states have genuinely different payload shapes (a request
  has no token/index, a token has no finish_reason/total_tokens), and
  zod/pydantic's discriminated unions already give us type-safe
  per-variant payloads "for free" at the `type` level; collapsing them
  would just move that discrimination into a second field for no benefit.
- **Batching `ai.token` events (e.g. every N tokens) to reduce event
  volume:** rejected for Phase 2 — premature optimization ahead of any
  measured performance problem; the renderer's WebSocket client has no
  observed difficulty with per-token events at realistic local-model
  token rates. Revisit if profiling in a later phase shows otherwise.
