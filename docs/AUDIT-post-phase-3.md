# Post-Phase-3 Architecture Audit

**Date:** 2026-07-24
**Scope:** Phases 0–3 (full codebase: contracts, shell, renderer, backend)
**Purpose:** Verify architectural consistency before Phase 4 begins, per
the project mandate's "review the existing architecture... before
generating code" requirement, applied here as a standalone gate rather
than an implicit pre-check.

## Method

Every finding below was produced by an actual scripted check against the
codebase (AST parsing for Python, regex-based structural checks for TS),
not by inspection or assertion. Scripts and their exact output are not
reproduced here for brevity, but every check is re-runnable.

## Findings

### 1. ADR cross-reference integrity
Every `ADR-XXXX` reference across all source and doc files (Python, TS,
Markdown) resolves to an ADR file that actually exists (excluding
ADR-0005, intentionally reserved for Phase 5's plugin manifest). Every
existing ADR file is referenced from at least one place in the code or
docs. **Result: clean, no orphaned references either direction.**

### 2. Contract parity (TypeScript ↔ Python)
- `JarvisEvent` discriminated union: 22/22 event type literals match
  exactly between `events.ts` and `events.py`.
- `PermissionScope` enum: 6/6 values match exactly between
  `ipc-contracts.ts` and `safety_gate.py`'s Python mirror.
**Result: zero drift.** The review-discipline-only drift-prevention
approach (no automated CI check yet — tracked as an open follow-up since
Phase 1) has held through three phases of additions.

### 3. Unused modules / dead code
- Every one of the 56 backend source modules is imported from at least
  one other module or test (2 apparent misses were confirmed false
  positives — `routes_health`/`ws_events`, imported via `from . import
  routes_ai, routes_health, ws_events`, a pattern the naive AST-import
  scanner doesn't specially handle).
- Every public top-level class/function that appears only once in the
  full-text corpus was confirmed to be either a pytest test function
  (discovered by pytest, not referenced by name), a FastAPI route handler
  (registered via decorator, not called directly), or a fixture (matched
  by parameter name, not literal reference) — no genuine dead application
  code found.
**Result: no dead code identified.**

### 4. Duplicate abstractions / overlapping responsibilities
No duplicate class names exist anywhere in the Python backend (56 files)
or in exported TypeScript classes/interfaces (renderer + shell +
contracts). Deliberately *parallel* patterns exist by design and are
each documented as such where introduced — `ToolRegistry` (backend tool
catalogue) vs. `WidgetRegistry` (renderer widget catalogue) are the same
registry/executor architectural shape applied to two different layers,
not duplicated logic; `WorkingMemory` vs. `TaskLedger` vs. `SafetyGate`'s
audit log are three distinct concerns (session context, task history,
authorization decisions) that ADR-0004/ADR-0007 each explicitly justify
keeping separate rather than merging.
**Result: no accidental duplication found.**

### 5. Composition-root / DI boundary integrity
Every concrete provider class (`OllamaProvider`, `MockProvider`,
`WebRtcVadProvider`, `OpenWakeWordProvider`, `WhisperCppProvider`,
`PiperProvider`, `MicrophoneManager`, `SpeakerManager`) is instantiated
in exactly one place outside of tests: `main.py`'s composition root
(`build_orchestrator`/`build_provider`/`build_voice_engine`). The single
apparent exception (a match inside `ollama_provider.py` itself) was
confirmed to be a docstring code example, not a real instantiation.
**Result: composition-root discipline holds across all three phases of
provider additions.**

### 6. Typing completeness
Zero functions across the 56-file backend source tree lack a return type
annotation. Every occurrence of `Any` or `# type: ignore` (9 and 12
respectively) is confined to the exact boundary where an untyped native
library without type stubs is wrapped (`sounddevice`, `webrtcvad`,
`openwakeword`) — none leaks into application logic (`ai/`, `agents/`,
`memory/`, `api/`). On the TypeScript side, exactly one `any` exists
(`EventBusClient`'s internal type-erased listener storage map — the
public `on<T>()` API remains fully generic), and zero `@ts-expect-error`/
`@ts-ignore` directives exist anywhere in the renderer or shell.
**Result: typing discipline is intact and the few necessary escapes are
narrowly scoped and load-bearing, not convenience shortcuts.**

### 7. Event-publishing discipline (ADR-0003, ADR-0010)
Every one of the 19 checked event classes (`Agent*Event`, `Ai*Event`,
`Voice*Event`, `OrchestratorMessageEvent`) is constructed from exactly
one file in the entire backend. The "exactly one component is the sole
publisher of a given event family" rule established in ADR-0003 and
extended by ADR-0010 for `voice.*` has zero violations across three
phases of additions.
**Result: perfect single-publisher discipline, no drift.**

### 8. ADR-claim-to-code verification
Spot-checked five specific, falsifiable claims made across ADR-0004,
ADR-0007, and ADR-0011 against the current code:
- `SafetyGate`'s `PROMPT` decision resolves to `DENY` — confirmed.
- `SafetyPolicy.production_default()` is default-deny — confirmed.
- `main.py` wires `NullLongTermMemory()` as the `RetrievalPipeline`'s
  long-term memory — confirmed.
- `VoiceEngine.start()` gates on `PermissionScope.AUDIO_MICROPHONE`
  before opening the microphone — confirmed.
- `ToolExecutor` is the sole caller of `ToolSpec.handler` anywhere in the
  codebase — confirmed (exactly one call site).
**Result: no semantic drift between documented decisions and actual
behavior on any checked claim.**

## Conclusion

No corrective action items were identified. Phases 0–3 remain internally
consistent: contracts match implementation, ADRs match code, no dead code
or duplicate abstractions were introduced, typing discipline is intact,
and architectural boundaries (composition root, single-publisher events)
have held under three phases of additive change. See the accompanying
**Architecture Health Report** for forward-looking priorities.
