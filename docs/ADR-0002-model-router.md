# ADR-0002: ModelRouter — Provider Abstraction & Task-Based Routing

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 2 — Orchestrator + Agent Core + ModelRouter

## Context

Per the project mandate: "Use Ollama, Qwen, DeepSeek... Every model must be
replaceable. No subsystem should depend directly on a specific model."
Every AI-consuming subsystem in the backend (Orchestrator response
synthesis, Planner's reasoning calls, domain agents' reasoning-only steps,
future memory summarization/embedding) needs to call a model without
knowing which model, which provider, or even which machine it's running
on — and needs that call to degrade gracefully (fall back to another model)
rather than fail outright when a specific model is unavailable, overloaded,
or slow to load.

## Decision

A single `ModelRouter` (`apps/backend/src/jarvis_backend/ai/router.py`) is
the only entry point any subsystem uses to call a model. It is built from
five composed pieces, each independently replaceable:

1. **`ModelProvider` protocol** (`ai/types.py`) — structural typing (a
   `Protocol`, not an ABC), so a provider satisfies the interface by shape
   alone with no required base-class import. `OllamaProvider` and
   `MockProvider` both implement it today; a future `LlamaCppProvider` or
   hosted-API provider would too, without either existing provider
   changing.
2. **Task-based routing** (`config.RoutingConfig`) — every call specifies
   an `AiTaskType` (`chat`, `reasoning`, `toolcall`, `summarize`, `embed`),
   not a model name. The routing table maps each task type to an ordered
   list of (provider, model) targets. This is what lets the Planner use a
   different, more deliberate model for `reasoning` than the Orchestrator
   uses for conversational `chat`, purely via config — no code branches on
   task type inside any caller.
3. **Capability negotiation** — before using a routing target,
   `ModelRouter` checks `provider.capabilities(model)` against what the
   call actually needs (e.g. `supports_streaming` for `stream()`,
   `supports_embeddings` for `embed()`). A target that can't do what's
   asked is skipped in favor of the next fallback target, rather than
   failing after the request is already in flight.
4. **Fallback chain with retry** — each target gets up to
   `RetryPolicy.max_retries` attempts (exponential backoff, capped) before
   `ModelRouter` advances to the next target in the chain. Only once every
   target in the chain is exhausted does `stream()`/`embed()` raise
   `NoHealthyProviderError` to the caller.
5. **`WarmModelManager`** (`ai/warm_pool.py`) — tracks per-(provider,
   model) last-use time and proactively re-issues a lightweight `warm()`
   call after an idle threshold, so a real request doesn't pay a cold-load
   penalty it didn't have to.

`ContextWindowManager` (`ai/context_window.py`) is invoked per-target,
after a target is selected but before the request is sent, using that
target's own `max_context_tokens` — a router-level concern distinct from
`RetrievalPipeline`'s retrieval/compression policy (see ADR-0007).

## Rationale

- **Task-based routing over model-based routing** means callers express
  *intent* ("this is a reasoning call") not *mechanism* ("use
  deepseek-r1"). Swapping which model handles reasoning — even swapping
  providers entirely — is a config change, matching "every model must be
  replaceable" literally, not just in spirit.
- **Protocol over ABC** for `ModelProvider` keeps provider implementations
  free of any required import from this project's own class hierarchy —
  relevant if a provider package is ever split out or shared.
- **Fallback chains, not a single provider with generic retry**, because
  the realistic failure mode for a local-first product isn't "the network
  blipped" (retry handles that) but "this specific model isn't pulled/
  loaded/healthy on this machine" — which retrying the same target cannot
  fix, but trying a different target can.

## Consequences

- Every new AI-consuming subsystem calls `ModelRouter.stream()` /
  `.complete()` / `.embed()` — never a provider directly. Code review
  should flag any direct `OllamaProvider`/`MockProvider` usage outside
  `ai/`, `main.py`'s composition root, and tests.
- Routing config changes (adding a fallback target, repointing a task type
  at a different model) never require a code change — only the
  `JARVIS_ROUTING_JSON` env var (or the built-in default in `config.py`).
- `ModelRouter` publishes the full `ai.request`/`ai.token`/`ai.response`
  event sequence itself (see ADR-0003) — callers never publish these
  events directly, keeping exactly one place responsible for AI-call
  observability regardless of which subsystem initiated the call.

## Alternatives Considered

- **LangChain / LlamaIndex model abstraction layers:** rejected — both
  bring far more surface area (chains, agents, retrievers) than this
  project needs, and neither's provider abstraction natively expresses
  "task-type-based fallback chains with capability negotiation" the way
  this ADR requires; adopting one would mean fighting its abstractions to
  get this behavior rather than the reverse.
- **A single provider with no fallback, retry only:** rejected per
  Rationale above — doesn't address the dominant real-world local-model
  failure mode.
- **Model-name-based routing (caller specifies "qwen2.5" directly):**
  rejected — this is exactly the coupling "every model must be
  replaceable" prohibits; it would leak model choice into every call site
  instead of centralizing it in `RoutingConfig`.
