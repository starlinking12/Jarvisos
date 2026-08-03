# ADR-0012: Local-First Persistence Layer & the Permission Broker

**Status:** Accepted
**Date:** 2026-07-25
**Phase:** 4 — Memory Persistence + Security Center

## Context

Three things Phase 2/3 explicitly deferred now need real implementations:
`TaskLedger` and `SafetyGate`'s audit log were documented as
in-process/non-durable pending "Phase 3's persistence layer" (ADR-0004,
ADR-0007 — since renumbered to Phase 4 when Voice Engine took the Phase 3
slot); `LongTermMemory` had only a null-object default awaiting a real
implementation (ADR-0007); and `SafetyGate`'s `PROMPT` decision tier
resolved unconditionally to `DENY` because no channel existed for a
backend-originated permission request to reach the Electron-side
`PermissionGate` dialog (ADR-0004, ADR-0011).

## Decision

### Persistence: one SQLite database, `aiosqlite`-backed

A single `Database` class (`persistence/database.py`) wraps one SQLite
file (default `~/.jarvis/jarvis.db`), with `aiosqlite` giving it an
async-native interface matching the rest of the backend. One `Database`
instance, constructed once in `main.py`'s `lifespan`, injected into every
repository (`TaskRepository`, `AuditRepository`, `MemoryRepository`,
`SettingsRepository`, `SecurityRepository`) — the same "one shared
instance, injected everywhere" shape as `EventBus`.

**Every durability-consuming class keeps its Phase 2/3 public interface
identical**, per the compatibility promise those ADRs made:
- `TaskLedger(repository: TaskRepositoryProtocol | None = None)` —
  omitting the repository restores exact in-memory-only behavior; every
  Phase 2/3 test that constructs `TaskLedger()` with no arguments needed
  zero changes.
- `SafetyGate(policy, *, broker=None, audit_repository=None)` — same
  guarantee; `SafetyGate(SafetyPolicy.production_default())` (the form
  every existing test uses) is unaffected.
- `LongTermMemory`'s interface (`retrieve`/`store`) is unchanged;
  `SqliteLongTermMemory` is a new implementation alongside
  `NullLongTermMemory`, not a replacement of the interface.

Repository dependencies are expressed as `Protocol`s
(`TaskRepositoryProtocol`, `AuditRepositoryProtocol`,
`MemoryRepositoryProtocol`, `BaselineStoreProtocol`,
`SecurityRepositoryProtocol`) rather than direct imports of the concrete
repository classes — `agents/` and `memory/` depend on structural shapes,
not on `persistence/` as a hard import. This keeps the dependency
direction one-way (`persistence/` depends on `agents/`'s and `memory/`'s
*types* — `AgentTask`, `MemoryItem` — but never the reverse), consistent
with every other Protocol-based provider boundary in this codebase.

**Durability is best-effort, never blocking.** `TaskLedger`'s writes fire
via `asyncio.ensure_future` rather than being awaited inline — a
persistence failure is logged, never raised into agent execution.
`SafetyGate`'s audit write-through is wrapped in its own try/except for
the same reason. The in-memory state (already correct before any
persistence write happens) is always the source of truth for the current
process's lifetime; SQLite is the source of truth *across restarts*.

### Semantic + episodic memory + a minimal knowledge graph

`SqliteLongTermMemory` embeds every stored item via `ModelRouter`'s
`embed` task (ADR-0002) and ranks retrieval by cosine similarity — genuine
semantic search. Episodic retrieval (recency/time-range) uses the same
`memory_items` table, since every item already carries a timestamp — one
storage mechanism, two query patterns, not two separate subsystems. A
minimal knowledge graph (`memory_edges`: typed relationships between
items) is exposed via `add_relationship`/`related_items`, scoped
deliberately to what a single-user assistant's memory needs.

### Permission Broker: closing ADR-0004's `PROMPT` gap

`PermissionBroker` (`agents/permission_broker.py`) publishes a
`permission.request` event with a unique `request_id` and awaits a
matching `asyncio.Future`, bounded by a timeout that resolves to `False`
(deny) if unanswered. The Electron shell's `PermissionBridge`
(`apps/shell/src/main/backend/PermissionBridge.ts`) subscribes to the
backend's event stream, shows the existing `PermissionGate` dialog on
`permission.request`, and POSTs the decision to the backend's new
`POST /agent/permission-decision` endpoint, which resolves the broker's
pending future. `SafetyGate`'s `PROMPT` tier now calls
`PermissionBroker.request_decision()` when a broker is configured — with
no broker (e.g. most tests), `PROMPT` still resolves to `DENY` exactly as
before, so this is purely additive.

## Rationale

- **SQLite over a client-server database:** matches "local-first,"
  "offline-first," "privacy-by-default" directly — no server process, no
  network configuration, no additional attack surface, fully sufficient
  for one user's data volume.
- **One database, repositories per concern, not one repository per
  table:** repositories group by *consumer* (`TaskRepository` serves
  `TaskLedger`, `MemoryRepository` serves `SqliteLongTermMemory`), not by
  raw table — a repository's public methods are the operations its
  consumer actually needs, not a generic CRUD wrapper around a table.
- **Protocol-typed repository dependencies, not concrete imports:**
  identical reasoning to every other provider boundary in this
  project — `agents/task_ledger.py` doesn't need to know SQLite exists to
  be durability-capable; a future non-SQLite backend (unlikely, but the
  point is architectural, not speculative) would satisfy the same
  Protocol with zero changes to `TaskLedger`.
- **Best-effort, non-blocking persistence writes:** an agent task's
  correctness must never depend on database write latency or
  availability — the in-memory ledger is authoritative for the running
  process; SQLite exists for the *next* process (restart survival) and
  for queryability, not as a synchronous dependency of normal operation.
- **Timeout-bound `DENY` for unanswered permission requests:** identical
  posture to every other "absence of a definite ALLOW" rule in this
  project (ADR-0004) — a user who doesn't respond has not granted
  anything.

## Consequences

- `main.py`'s `build_orchestrator(settings, database=None)` now accepts
  an optional `Database` — every unit test that omits it gets Phase 2/3
  behavior unchanged; `lifespan` always passes a connected one.
- `agents/permission_broker.py` is always constructed (cheap — an empty
  pending-requests dict until first use), even when no `PROMPT`-tier
  scope is configured — harmless, and means enabling `PROMPT` for a scope
  later is a pure config change with no code/wiring change needed.
- The knowledge graph is intentionally not general-purpose — a future
  need for complex graph traversal/queries (multi-hop reasoning over
  relationships) would be a deliberate upgrade to a real graph database,
  not an incremental extension of `memory_edges`.
- Settings persistence (`SettingsRepository`, `GET/PUT /settings/{key}`)
  uses the same `Database`, completing "Settings gains persisted,
  user-editable preferences" — the renderer's Zustand persistence
  middleware (see the renderer-side follow-up) reads/writes through this
  API.

## Alternatives Considered

- **A dedicated embedded vector database (e.g. Chroma, LanceDB) instead
  of SQLite + brute-force cosine similarity:** rejected for Phase 4 — a
  single user's memory corpus (thousands, not millions, of items) makes
  brute-force cosine similarity over a BLOB-stored embedding column fast
  enough that a dedicated vector index would be premature optimization;
  revisit if profiling on real usage shows otherwise.
- **A full graph database (Neo4j, etc.) for the knowledge graph:**
  rejected — operationally heavier (a separate server process) than
  "local-first" should require for what a single-user assistant's
  relationship data actually needs; the minimal SQLite-backed edge table
  is the right scope today.
- **Synchronous (awaited) persistence writes in `TaskLedger`/
  `SafetyGate`:** rejected per Rationale — would make agent execution
  latency depend on disk I/O for no correctness benefit, since the
  in-memory state is already authoritative.
