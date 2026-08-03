# ADR-0004: Task Ledger & SafetyGate — Agent Governance

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 2 — Orchestrator + Agent Core + ModelRouter

## Context

Once agents can execute tools (Phase 2 introduces the first real ones,
Phase 4+ adds higher-impact ones like filesystem/automation/shell), two
governance questions become unavoidable: "what happened, in order, for
this task" (auditability) and "is this specific action currently allowed"
(authorization). The project mandate requires both explicitly: "Track
every generated file... every architecture decision" at the documentation
level, and "Automation that sends emails, spends money, publishes content,
or makes irreversible changes must require explicit user approval" at the
runtime level. Neither can be bolted on later without touching every
tool-invoking call site, so both need to exist from the moment tools do.

## Decision

Two separate, single-purpose components, deliberately not merged into one
"agent governance" class:

**`TaskLedger`** (`agents/task_ledger.py`) is the authoritative record of
every task's lifecycle — creation, plan assignment, each observation,
completion. Every mutation is audit-logged via structlog with the task id
bound as `correlation_id`. It answers "what happened" — a pure record,
with no authority to prevent anything.

**`SafetyGate`** (`agents/safety_gate.py`) is the sole authority for
whether a tool invocation carrying a `PermissionScope`
(`filesystem.write`, `process.control`, `network.egress`,
`automation.input`, `shell.execute`) is allowed to proceed. It answers "is
this allowed" — a pure authorization check, with no responsibility for
recording history (though every decision it makes is itself audit-logged,
since a denied/allowed decision is part of the task's history that
`TaskLedger` would otherwise miss).

`ToolExecutor` (the Tool Executors tier — see ADR-0008) is the only
component that calls both: it asks `SafetyGate.check()` before invoking a
gated tool's handler, and calls `TaskLedger.record_observation()` after,
regardless of outcome.

**`SafetyGate`'s Phase 2 policy is default-deny.** `SafetyPolicy` has a
`default` (production default: `DENY`) and per-scope `overrides`. A
`PROMPT`-tier scope — intended for "ask the user interactively" — resolves
to `DENY` in Phase 2, stated plainly in `safety_gate.py`'s module
docstring: no RPC channel yet exists for a backend-originated permission
request to reach the Electron-side `PermissionGate` dialog
(`apps/shell/src/main/ipc/permissions.ts`), which today only serves
renderer-initiated requests. Building that channel is scoped to Phase 4's
Security Center, alongside the `security.alert` event plumbing that
already exists as an unused contract since Phase 0.

## Rationale

- **Separate classes because they have different failure semantics.** If
  `TaskLedger` fails to record something, the task still proceeded
  correctly — a logging concern. If `SafetyGate` fails to deny something
  it should have denied, that's a security incident. Merging them risks a
  bug in one degrading the guarantees of the other; keeping them apart
  means `SafetyGate`'s logic is small enough to review and reason about in
  isolation.
- **Default-deny, not default-allow-with-a-warning,** because Phase 2 has
  no interactive approval UI wired up yet (see Decision). Default-allow
  would mean every gated tool silently succeeds until Phase 4 builds the
  approval flow — the opposite of what a permission gate is for. A
  correctly-scoped `DENY` is not a placeholder; it's the only safe default
  in the absence of a working approval mechanism, and it fails loud (an
  audit-logged denial) rather than silent.
- **Audit logging via structlog contextvars, not a bespoke audit-log
  table**, because Phase 2 has no persistence layer yet (that's Phase 4's
  Memory subsystem — see ADR-0007) — structured logs are durable via
  whatever log aggregation the deployment already has, and the
  `correlation_id` convention means they're just as queryable as a
  database table would be once one exists, without inventing a
  Phase-2-only storage mechanism that Phase 4 would then have to migrate
  away from.

## Consequences

- Every new tool with real-world side effects (filesystem, network,
  process, input synthesis, shell) MUST declare a `permission_scope` on
  its `ToolSpec` — a tool with side effects and no scope is a bug, not a
  convenience.
- `SafetyPolicy.production_default()` is what `main.py`'s composition root
  uses; tests are free to construct a permissive `SafetyPolicy` for
  fixtures that need to exercise gated tools without a real approval flow
  (see `apps/backend/tests/test_tool_executor.py`).
- When Phase 4 builds the backend→shell permission RPC, only
  `SafetyGate.check()`'s handling of the `PROMPT` decision kind changes —
  everything that calls `SafetyGate` (currently just `ToolExecutor`) needs
  no change, since the `PermissionCheckResult` shape it returns is already
  stable.

## Alternatives Considered

- **One `AgentGovernance` class combining ledger + gate:** rejected per
  Rationale above (different failure semantics, easier isolated review as
  two classes).
- **Default-allow with a loud warning log for ungated actions in Phase 2:**
  rejected — "loud in the log, silent to the user" is exactly the failure
  mode a safety gate exists to prevent; a log line does not stop an
  irreversible action.
- **Immediate build-out of the full backend→shell permission RPC in Phase
  2** (rather than deferring to Phase 4): rejected — no tool that actually
  needs interactive approval exists yet (Phase 2's two real tools are both
  zero-risk, unscoped); building the RPC now would be speculative
  plumbing for a UI flow with nothing real to test it against. Phase 4
  pairs it with the Security Center and the first tools that genuinely
  need it (filesystem writes, automation input).
