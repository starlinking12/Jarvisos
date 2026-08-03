# ADR-0007: Memory Integration — Working Memory, a Stable Long-Term Interface, and Retrieval

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 2 — Orchestrator + Agent Core + ModelRouter (interface); Phase 4 (persistence)

## Context

The Orchestrator needs conversational context to respond coherently across
turns, and the project mandate specifies a full memory subsystem
(conversation, semantic, episodic memory, knowledge graph — Phase 4) that
does not exist yet. Phase 2 needs *something* working today (the
Orchestrator cannot wait for Phase 4 to hold a conversation), but building
against a Phase-2-only shape that Phase 4 would have to replace — forcing
every Phase 2 call site to change — would violate "every subsystem must be
replaceable" in the specific direction that matters most here: replacing
the *implementation* without touching the *interface*.

## Decision

Three layers, in `apps/backend/src/jarvis_backend/memory/`:

1. **`WorkingMemory`** — a real, fully-functional per-conversation message
   buffer (bounded by message count), in-process and non-durable. This is
   not a stand-in; it is the correct implementation for short-term,
   current-session context, and does not change when Phase 4 adds
   long-term storage — the two are genuinely different concerns (session
   context vs. durable knowledge).
2. **`LongTermMemory`** — an abstract interface (`retrieve`/`store`)
   defined now, ahead of any real implementation. `NullLongTermMemory` is
   the Phase 2 default: a genuine null-object implementation (always
   returns no results, always accepts and discards writes with a
   well-formed return value) — not a stub that raises
   `NotImplementedError`. Every caller that awaits `retrieve()` gets a
   real, empty result and proceeds normally; no caller special-cases
   "long-term memory isn't built yet."
3. **`RetrievalPipeline`** — assembles the message list the Orchestrator
   hands to `ModelRouter`, combining working memory, long-term memory hits
   (currently always empty via `NullLongTermMemory`), and context
   compression: once a conversation's working memory exceeds a threshold
   message count, the oldest portion is summarized (via `ModelRouter`'s
   `summarize` task type) into a single system message rather than sent
   verbatim, keeping the message list bounded across very long
   conversations independent of any specific model's context window.

**Division of labor with `ContextWindowManager`** (ADR-0002): retrieval
policy (what to include, when to compress) is a `RetrievalPipeline`
concern; the final hard token-budget fit for whichever specific model
`ModelRouter` resolves to is `ContextWindowManager`'s concern, applied
after routing. Neither duplicates the other — retrieval doesn't know about
per-model token budgets, and `ContextWindowManager` doesn't know about
long-term memory or summarization.

## Rationale

- **Null object over `NotImplementedError` stub**, specifically because a
  stub would force `RetrievalPipeline` and `Orchestrator` to branch on
  "does long-term memory exist yet" — exactly the kind of
  phase-awareness-leaking-into-business-logic this project's phased
  structure is designed to avoid. `NullLongTermMemory` is boring, correct,
  and Phase-3-ready: swapping in a real embedding-search implementation
  changes zero lines outside `memory/long_term.py` and whatever
  constructs it in `main.py`.
- **Defining the full interface now, not deferring it to Phase 4**, means
  Phase 2 code (`RetrievalPipeline`, `Orchestrator`) is written against
  the *real* Phase 4 shape from day one — no Phase 2→4 migration of call
  sites, only a Phase 4 migration of one class's internals.
- **Compression via summarization, not just truncation**, because
  `ContextWindowManager`'s truncation (ADR-0002) already handles the hard
  "must fit in N tokens" case; what it cannot do is preserve *meaning*
  from dropped messages. A long conversation that's been truncated loses
  information; one that's been summarized-then-truncated retains a
  compressed account of what was lost. Both mechanisms exist because they
  solve different problems (hard budget vs. information loss), not because
  one is a lesser version of the other.

## Consequences

- Phase 4's actual persistence work (episodic/semantic memory, knowledge
  graph, per the project mandate) is scoped narrowly: implement
  `LongTermMemory` for real (a concrete class alongside
  `NullLongTermMemory`, both satisfying the same interface), wire it into
  `main.py`'s composition root instead of `NullLongTermMemory`. No other
  file changes.
- `SafetyGate`'s audit log (ADR-0004) and `TaskLedger`'s task history are
  both currently non-durable for the same reason `WorkingMemory` is —
  Phase 4's persistence layer is the natural place to make all three
  durable together, rather than each inventing its own storage mechanism
  ahead of that.
- `RetrievalPipeline`'s compression threshold (currently a constructor
  default, not exposed via `Settings`) should graduate to typed config
  once Phase 4's Settings work extends `ResourceLimits`-style
  configuration to memory — tracked as a Phase 4 follow-up, not a Phase 2
  gap, since no user-facing need for tuning it exists yet.

## Alternatives Considered

- **Skip the `LongTermMemory` interface entirely in Phase 2, add it whole
  in Phase 4:** rejected per Rationale — would require modifying
  `RetrievalPipeline` and `Orchestrator`'s construction in Phase 4 instead
  of only `main.py`, and risks the interface being designed reactively
  around whatever Phase 4's specific persistence choice turns out to be,
  rather than being designed for genuine swappability from the start.
- **A single `Memory` god-class instead of `WorkingMemory` +
  `LongTermMemory` + `RetrievalPipeline`:** rejected — same reasoning as
  ADR-0004's ledger/gate split: three concerns (session buffer, durable
  interface, assembly policy) with different lifetimes and replacement
  timelines are clearer as three collaborating classes than one class with
  three responsibilities.
