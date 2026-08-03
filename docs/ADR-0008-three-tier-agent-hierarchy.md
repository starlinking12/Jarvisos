# ADR-0008: Three-Tier Agent Hierarchy — Orchestrator, Domain Agents, Tool Executors

**Status:** Accepted
**Date:** 2026-07-19
**Phase:** 2 — Orchestrator + Agent Core + ModelRouter

## Context

The project mandate specifies a multi-agent architecture with eight named
domain agents (Desktop, Vision, Research, Security, Memory, Earth,
Automation, Developer) plus an Orchestrator, and states a hard rule: "Only
the Orchestrator communicates with the user. All other agents operate
internally." It also requires governance (SafetyGate — ADR-0004) around
any action with real-world side effects. Phase 2 has to turn this from a
list of agent names into an actual execution architecture: something has
to decide *what* to do (planning), something has to decide *who* does each
piece (dispatch), and something has to be the single choke point through
which any side-effecting action passes (authorization + audit).

## Decision

Three tiers, strictly layered — a component in one tier only ever calls
downward, never sideways or upward:

1. **Orchestrator** (`agents/orchestrator.py`) — the only component
   permitted to publish `orchestrator.message` (the user-visible chat
   stream). Owns the full task lifecycle: creates the task in
   `TaskLedger`, invokes `Planner` to get a `Plan`, dispatches each
   `PlanStep` to the `DomainAgent` it's assigned to, then synthesizes the
   final response from the accumulated observations via `ModelRouter`.
2. **Domain Agents** (`agents/domain_agent.py`) — one per named agent
   identity (`EventSource.AGENT_*`). A domain agent never talks to the
   user and never invokes a tool handler directly; given a `PlanStep`, it
   either delegates to `ToolExecutor` (if the step names a tool it's
   allowed to use) or produces a reasoning-only observation via
   `ModelRouter`. All eight agents in Phase 2 are instances of one generic
   `DomainAgent` class, differentiated by data (`DomainAgentSpec`: allowed
   tools, system-prompt framing) rather than by subclassing — see
   `domain_agent.py`'s module docstring for why this is correct today and
   how individual agents graduate to bespoke subclasses when their
   respective phases (3, 4, 5) give them capabilities a generic
   reason-or-call-a-tool step cannot express.
3. **Tool Executors** (`agents/tool_executor.py` + `agents/tool_registry.py`)
   — `ToolExecutor` is the only component that ever calls a
   `ToolSpec.handler`. It enforces the `SafetyGate` check for any
   permission-scoped tool and publishes the resulting `agent.observe`
   event (ADR-0003) — so every tool invocation in the system, regardless
   of which domain agent triggered it, goes through the same
   authorization and observability path exactly once. `ToolRegistry` is
   the passive catalogue of what tools exist; `ToolExecutor` is the active
   authority over running them — the same registry/executor split as
   `WidgetRegistry` vs. widget rendering in the Phase 1 renderer, applied
   on the backend.

`Planner` sits alongside this hierarchy as the Orchestrator's collaborator
for the "what to do" question — the `Planner` protocol (ADR-0002-style
structural typing) is decoupled from any specific planning strategy;
`SimplePlanner` is today's real implementation, using `ModelRouter`'s
`reasoning` task type to decompose a goal into steps.

## Rationale

- **Strict downward-only calling is what makes "only the Orchestrator
  talks to the user" enforceable, not just a convention.** A domain agent
  has no reference to anything that could publish `orchestrator.message`;
  it only has a `ModelRouter` (for reasoning) and a `ToolExecutor` (for
  tool calls). The rule is structural, not just documented.
- **`ToolExecutor` as the sole tool-invocation choke point** is what makes
  `SafetyGate` (ADR-0004) actually universal rather than "universal as
  long as every domain agent remembers to check." One code path,
  reviewed once, applies to every tool call from every agent forever.
- **One generic `DomainAgent` class for all eight agents today** avoids
  writing eight files of identical logic before any of them has
  agent-specific *behavior* (as opposed to agent-specific *data* — which
  tools, which framing). Premature subclassing here would be speculative
  structure with no current behavioral difference to justify it — the
  same anti-duplication reasoning the project mandate applies everywhere
  else ("Do not duplicate logic across subsystems").

## Consequences

- Adding a ninth domain agent (unlikely, but structurally cheap) means one
  new entry in `build_default_agent_specs()` — no new class, no
  Orchestrator change.
- Giving an existing agent (e.g. Vision in Phase 5) real bespoke behavior
  means it graduates from `DomainAgent` to a `VisionAgent(DomainAgent)`
  subclass (or a distinct class satisfying the same call shape) at that
  point — a planned, not improvised, extension point.
- Any future "should agent X be allowed to do Y" question is answered by
  two independent, inspectable facts: `DomainAgentSpec.allowed_tools` (can
  this agent even attempt this tool) and `SafetyGate` policy (is this tool
  currently authorized to run at all) — not by reading procedural code to
  find out.
- The full event sequence a task produces (ADR-0003) is a direct
  reflection of this hierarchy: `agent.task.created`/`agent.plan`/
  `agent.step`/`agent.complete`/`agent.error` come from the Orchestrator
  tier, `agent.observe` comes from the Tool Executors tier — there is no
  event a Domain Agent publishes itself, consistent with "domain agents
  operate internally."

## Alternatives Considered

- **Flat agent architecture (Orchestrator calls tools directly, domain
  agents are just prompt templates):** rejected — collapses the
  authorization choke point (nothing would force every tool call through
  one gate) and makes "only the Orchestrator talks to the user" trivially
  true but meaningless, since there'd be nothing else in the system to
  compare it against.
- **Four-tier hierarchy splitting "Domain Agents" into "Reasoning Agents"
  and "Action Agents":** considered, rejected as premature — Phase 2's
  agents do both (reason when no tool applies, act when one does) via the
  same `handle_step` method; splitting them would anticipate a distinction
  that doesn't yet correspond to anything the codebase needs to treat
  differently.
- **Bespoke agent subclasses from day one for all eight agents:** rejected
  per Rationale — duplication without behavioral justification.
