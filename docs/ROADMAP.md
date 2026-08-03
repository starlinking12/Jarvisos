# JARVIS OS — Roadmap

This is the authoritative phase-by-phase roadmap. `ARCHITECTURE.md` links
here rather than duplicating it. Each phase begins only after the previous
phase's deliverables, docs, and tests are reviewed and approved.

---

## Phase 0 — Foundational Architecture ✅ Complete

Monorepo (pnpm + Turborepo), process/IPC boundaries, `packages/contracts`
(the shared TS/Python schema source), Electron main-process skeleton
(`WindowManager`, `OverlayWindow`, `TrayManager`, `GlobalShortcuts`,
`BackendSupervisor`, `IpcBridge`, `PermissionGate`), Python backend
skeleton (FastAPI + `EventBus` + health route).

## Phase 1 — Renderer Foundation ✅ Complete

React + Vite + React Three Fiber renderer; Arc Reactor core with a custom
holographic shader; particle field; transparent click-through overlay;
glassmorphism/token design system; Zustand state architecture
(ADR-0009); `EventBusClient` + `WebSocketClient`; docking layout + plugin-
ready `WidgetRegistry`; GPU detection + automatic quality scaling;
performance monitor; three-tier animation system (ADR-0006); error
boundaries; renderer logging.

## Phase 2 — Orchestrator + Agent Core + ModelRouter ✅ Complete — Finalized & Approved

**ModelRouter** (ADR-0002): `ModelProvider` protocol, `OllamaProvider`,
`MockProvider`, task-based routing (`chat`/`reasoning`/`toolcall`/
`summarize`/`embed`), fallback chains with retry, capability negotiation,
`ContextWindowManager`, `WarmModelManager`.

**Agent framework** (ADR-0008): three-tier hierarchy — `Orchestrator` (top,
sole user-facing tier), `DomainAgent` × 8 named agents (middle),
`ToolExecutor` + `ToolRegistry` (bottom, sole tool-invocation choke
point). `SimplePlanner` (LLM-driven plan decomposition). `TaskLedger` +
`SafetyGate` for governance (ADR-0004, default-deny policy).

**Memory integration** (ADR-0007): `WorkingMemory` (real, in-process),
`LongTermMemory` interface + `NullLongTermMemory` (real null-object
default, Phase 4 gets a real implementation behind the same interface),
`RetrievalPipeline` (working memory + long-term hits + summarization-based
compression).

**Event bus** (ADR-0003): `ai.request`/`ai.token`/`ai.response` and
`agent.task.created`/`agent.plan`/`agent.step`/`agent.observe`/
`agent.complete`/`agent.error`, all implemented and genuinely emitted
(not just declared) by the Orchestrator lifecycle.

**API:** `POST /ai/chat` — the renderer's direct entry point for
submitting a user message (content, not a native action, so it bypasses
Electron's IPC bridge per the Phase 1 ADR-0001 refinement).

**Tests:** 18 test modules covering unit (context window, warm pool, tool
registry, safety gate, task ledger, planner, domain agent, working memory,
retrieval, event bus), mock-provider-specific tests, full orchestrator
integration tests (event-sequence assertions, tool dispatch, planning
failure fallback, multi-turn conversation), `main.py` composition-root
tests, an API-level test for `/ai/chat`, and auto-skipping live-Ollama
validation tests.

## Phase 3 — Voice Engine ✅ Complete — Finalized & Approved

Real-time, local-first voice pipeline, fully integrated with the existing
`EventBus`, `Orchestrator`, `ToolRegistry`, and `SafetyGate`:

- **Audio subsystem:** `AudioDeviceManager`, `MicrophoneManager`/
  `SpeakerManager` (`sounddevice`), `RingBuffer` (thread-safe callback→asyncio
  bridge), `AudioStreamingPipeline` (VAD-based speech segmentation).
- **Wake word:** `OpenWakeWordProvider` — configurable wake words,
  sensitivity, consecutive-frame + refractory-period false-positive
  mitigation.
- **VAD:** `WebRtcVadProvider` (hangover-smoothed for STT segmentation) +
  `SoftwareAgc` (real RMS-based automatic gain control) + documented
  null-object noise suppression/echo cancellation extension points.
- **STT:** `WhisperCppProvider` — subprocess-based, word-level
  pseudo-streaming partials, language detection, timestamps.
- **TTS:** `PiperProvider` — subprocess-based streaming synthesis, voice
  selection, a real (rate) and a documented-for-later (style/pitch)
  control surface.
- **Barge-in:** `BargeInController` — hangover-free VAD path, direct
  `SpeakerManager.stop()` call, ~41ms worst-case latency (target: <150ms).
- **`VoiceEngine`:** the full state machine (`IDLE → WAKE_LISTENING →
  LISTENING → TRANSCRIBING → THINKING → SPEAKING`), delegating every
  conversational turn to the existing `Orchestrator.handle_user_message()`
  — voice is a second entry point into the same pipeline `POST /ai/chat`
  uses, not a parallel one.
- **New permission scope:** `audio.microphone`, added to both the TS and
  Python `PermissionScope` mirrors, gated by `SafetyGate` before the
  microphone ever opens.
- **New event family:** `voice.wake`/`listening`/`partial`/`final`/
  `thinking`/`speaking`/`finished`/`interrupted`/`error`.
- **Tests:** 7 new hardware-independent test modules (26 total for the
  backend), including a full `VoiceEngine` state-machine integration test
  using fakes for every hardware-backed provider protocol.

See ADR-0010 (architecture) and ADR-0011 (barge-in & permission model).

## Phase 4 — Memory Persistence + Security Center ✅ Complete — Finalized & Approved

Durable local-first persistence (SQLite-backed) for long-term memory,
task history, and security audit logs; a real backend→shell permission
RPC completing the `SafetyGate` `PROMPT` tier; a Security Center with
real process/startup/registry/scheduled-task/file-integrity/network
monitoring backed by the `security.alert` events that have existed
unused since Phase 0; persisted, user-editable Settings. See ADR-0012+
for the detailed decisions as they're written.

- Real `LongTermMemory` implementation (episodic + semantic memory,
  knowledge graph) behind the ADR-0007 interface — replaces
  `NullLongTermMemory` in `main.py`'s composition root only.
- Durable storage for `TaskLedger` and `SafetyGate`'s audit log (currently
  in-process/non-durable — see ADR-0004, ADR-0007 consequences).
- Backend→shell permission RPC: the missing link for `SafetyGate`'s
  `PROMPT`-tier decisions to reach the Electron-side `PermissionGate`
  dialog (`apps/shell/src/main/ipc/permissions.ts`) — currently resolves
  to `DENY` (see ADR-0004).
- Security Center: process/startup/registry/scheduled-task/file-integrity/
  network monitoring, backed by real `security.alert` events (schema has
  existed unused since Phase 0).
- Settings gains persisted, user-editable preferences (Phase 1's
  `SettingsRoot` is currently read-only pending this).
- Zustand gains a persistence middleware (per ADR-0009) once there's
  something durable to persist to.

## Phase 5 — Desktop Intelligence + Automation + Packaging

- Desktop Agent gains real window/UI-control recognition (graduates from
  generic `DomainAgent` to a bespoke subclass — see ADR-0008
  consequences).
- Automation Agent gains real desktop automation tools, gated by
  `SafetyGate`'s `automation.input` scope (now enforceable end-to-end
  once Phase 4's permission RPC exists).
- `electron-builder` packaging/distribution; resolves the renderer
  production-build-output-path gap noted in Phase 1's follow-ups.
- Plugin system: `WidgetRegistry` (renderer) and `ToolRegistry` (backend)
  are already plugin-shaped; this phase adds the loader and manifest
  format (reserved as ADR-0005).

## Phase 6+ — Vision, Earth, Business Intelligence

- Vision Agent: real image/screen interpretation tooling.
- Earth Agent: CesiumJS-based geospatial visualization.
- Business Intelligence modules (analytics, financial dashboards, market
  research, content planning) per the project mandate, with
  irreversible/spending actions gated by `SafetyGate` the same way
  automation actions are.
- Third-party plugin SDK, building on Phase 5's plugin loader.
