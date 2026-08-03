# Changelog

## Phase 3 — Voice Engine

### Added files

**Docs**
- `docs/ADR-0010-voice-engine-architecture.md`
- `docs/ADR-0011-barge-in-and-microphone-permission.md`

**Backend — `voice/` (25 files)**
- `voice/__init__.py`, `voice/types.py`, `voice/config.py`,
  `voice/voice_engine.py`, `voice/barge_in.py`, `voice/tools.py`
- `voice/audio/__init__.py`, `voice/audio/device_manager.py`,
  `voice/audio/microphone.py`, `voice/audio/speaker.py`,
  `voice/audio/ring_buffer.py`, `voice/audio/pipeline.py`
- `voice/vad/__init__.py`, `voice/vad/provider.py`,
  `voice/vad/webrtc_vad_provider.py`, `voice/vad/audio_processing.py`
- `voice/wake_word/__init__.py`, `voice/wake_word/provider.py`,
  `voice/wake_word/openwakeword_provider.py`
- `voice/stt/__init__.py`, `voice/stt/provider.py`,
  `voice/stt/whisper_cpp_provider.py`
- `voice/tts/__init__.py`, `voice/tts/provider.py`,
  `voice/tts/piper_provider.py`

**Backend — tests (7 files)**
- `tests/test_ring_buffer.py`, `tests/test_audio_processing.py`,
  `tests/test_voice_config.py`, `tests/test_whisper_cpp_provider.py`,
  `tests/test_piper_provider.py`, `tests/test_barge_in.py`,
  `tests/test_voice_engine_integration.py`

**Total added: 34 files** (2 docs, 25 voice source files, 7 test files).

### Modified files

- `packages/contracts/src/ipc-contracts.ts` — added `audio.microphone` to
  the `PermissionScope` enum.
- `packages/contracts/src/events.ts` — added `VoiceWakePayload` through
  `VoiceErrorPayload` (9 payload types) and 9 new `JarvisEvent`
  discriminated-union variants (`voice.wake` through `voice.error`).
- `packages/contracts/python/jarvis_contracts/events.py` — mirrored all of
  the above in pydantic v2.
- `packages/contracts/python/jarvis_contracts/__init__.py` — exports
  updated for the new voice event/payload classes.
- `apps/backend/src/jarvis_backend/agents/safety_gate.py` — added
  `AUDIO_MICROPHONE` to the Python `PermissionScope` mirror.
- `apps/backend/src/jarvis_backend/config.py` — added `voice_settings_json`
  field.
- `apps/backend/src/jarvis_backend/main.py` — added `OrchestratorBundle`
  (changing `build_orchestrator`'s return type from a tuple to a named
  bundle, since `build_voice_engine` needs access to `tool_registry` and
  `safety_gate` alongside the orchestrator), `build_provider`'s
  composition extended with `build_voice_engine`, and `lifespan` wired to
  start/stop the voice engine when enabled.
- `apps/backend/tests/test_main_composition.py` — updated for
  `OrchestratorBundle`'s new return shape.
- `apps/backend/pyproject.toml` — added `[voice]` optional-dependencies
  group (`numpy`, `sounddevice`, `webrtcvad`, `openwakeword`) and the
  `live_voice_hardware` pytest marker.
- `docs/ROADMAP.md` — Phase 3 inserted as Voice Engine; all subsequent
  phases renumbered (old Phase 3 "Memory Persistence + Security Center" →
  Phase 4, old Phase 4 → Phase 5, old Phase 5+ → Phase 6+).
- `docs/ADR-0004-task-ledger-safety-gate.md`, `docs/ADR-0007-memory-integration.md`,
  `docs/ADR-0009-state-architecture.md` — forward-looking "Phase 3"
  references (written when memory persistence was expected to be Phase 3)
  corrected to "Phase 4" to stay consistent with the renumbered roadmap.
  Each ADR's own "**Phase:**" header (recording when the decision was
  made) is unchanged — only forward references to *future* phase numbers
  were corrected.
- `docs/ARCHITECTURE.md` — full rewrite for Phase 3 (system diagram,
  folder tree, dependency table, testing strategy, ADR log, file
  inventory).

### Dependencies added

| Package | Scope | Reason |
|---|---|---|
| `numpy` | Core `[voice]` extra | Audio sample arrays, DSP (AGC) |
| `sounddevice` | Core `[voice]` extra | PortAudio bindings — mic capture, speaker playback |
| `webrtcvad` | Core `[voice]` extra | Voice activity detection |
| `openwakeword` | Core `[voice]` extra | Wake-word detection |

All four are optional (`pip install "jarvis-backend[voice]"`), not core
dependencies — see ADR-0010. whisper.cpp and Piper are external binaries
invoked via subprocess, not pip packages (Piper's official `piper-tts`
package is a valid install path for its bundled binary; whisper.cpp
requires a user build or a project release download).

### Remaining TODOs (tracked in `ARCHITECTURE.md` §9)

1. Real-time noise suppression/echo cancellation are real null-object
   passthroughs, not a native NS/AEC backend — tracked as Phase 5 (ADR-0010).
2. `audio.microphone` inherits the `PROMPT`→`DENY` limitation from
   ADR-0004 — no interactive consent dialog yet, config-only override
   (ADR-0011).
3. `WhisperCppProvider`'s streaming is word-level pseudo-streaming
   (decode-time, not capture-time) — documented behavior, not a gap
   (ADR-0010).
4. No live hardware smoke test yet — `live_voice_hardware` marker is
   registered and ready; Phase 3's fakes already achieve full
   state-machine coverage without one.
5. Same sandbox limitation as Phase 2: no live `pytest`/`mypy` run
   performed here — verified via `py_compile` + tokenization + import-
   resolution scripts instead (82 files, zero unresolved references).
   **Action required before merge:** `pip install -e ".[dev,voice]" &&
   pytest && mypy src`.
6. All Phase 1/2 carried-over TODOs remain open (see `ARCHITECTURE.md` §9).

---

## Phase 2 — Orchestrator + Agent Core + ModelRouter

### Added files

**Docs**
- `docs/ADR-0002-model-router.md`
- `docs/ADR-0003-streaming-event-protocol.md`
- `docs/ADR-0004-task-ledger-safety-gate.md`
- `docs/ADR-0007-memory-integration.md`
- `docs/ADR-0008-three-tier-agent-hierarchy.md`
- `docs/ROADMAP.md`

**Backend — `ai/` (ModelRouter subsystem)**
- `apps/backend/src/jarvis_backend/ai/__init__.py`
- `apps/backend/src/jarvis_backend/ai/types.py`
- `apps/backend/src/jarvis_backend/ai/context_window.py`
- `apps/backend/src/jarvis_backend/ai/warm_pool.py`
- `apps/backend/src/jarvis_backend/ai/ollama_provider.py`
- `apps/backend/src/jarvis_backend/ai/mock_provider.py`
- `apps/backend/src/jarvis_backend/ai/router.py`

**Backend — `agents/` (three-tier agent framework)**
- `apps/backend/src/jarvis_backend/agents/__init__.py`
- `apps/backend/src/jarvis_backend/agents/types.py`
- `apps/backend/src/jarvis_backend/agents/tool_registry.py`
- `apps/backend/src/jarvis_backend/agents/tool_executor.py`
- `apps/backend/src/jarvis_backend/agents/safety_gate.py`
- `apps/backend/src/jarvis_backend/agents/task_ledger.py`
- `apps/backend/src/jarvis_backend/agents/planner.py`
- `apps/backend/src/jarvis_backend/agents/domain_agent.py`
- `apps/backend/src/jarvis_backend/agents/orchestrator.py`
- `apps/backend/src/jarvis_backend/agents/tools/__init__.py`
- `apps/backend/src/jarvis_backend/agents/tools/system_tools.py`

**Backend — `memory/` (memory integration)**
- `apps/backend/src/jarvis_backend/memory/__init__.py`
- `apps/backend/src/jarvis_backend/memory/types.py`
- `apps/backend/src/jarvis_backend/memory/working_memory.py`
- `apps/backend/src/jarvis_backend/memory/long_term.py`
- `apps/backend/src/jarvis_backend/memory/retrieval.py`

**Backend — API**
- `apps/backend/src/jarvis_backend/api/routes_ai.py`

**Backend — tests**
- `apps/backend/tests/conftest.py`
- `apps/backend/tests/test_context_window.py`
- `apps/backend/tests/test_warm_pool.py`
- `apps/backend/tests/test_mock_provider.py`
- `apps/backend/tests/test_model_router.py`
- `apps/backend/tests/test_tool_registry.py`
- `apps/backend/tests/test_safety_gate.py`
- `apps/backend/tests/test_task_ledger.py`
- `apps/backend/tests/test_tool_executor.py`
- `apps/backend/tests/test_planner.py`
- `apps/backend/tests/test_domain_agent.py`
- `apps/backend/tests/test_working_memory.py`
- `apps/backend/tests/test_retrieval.py`
- `apps/backend/tests/test_event_bus.py`
- `apps/backend/tests/test_orchestrator_integration.py`
- `apps/backend/tests/test_main_composition.py`
- `apps/backend/tests/test_api_routes_ai.py`
- `apps/backend/tests/test_ollama_provider_live.py`

**Total added: 39 files** (6 docs, 26 backend source files including
`api/routes_ai.py`, 17 test modules + `conftest.py`).

### Modified files

- `packages/contracts/src/events.ts` — added `AiTaskType`, `AiRequestPayload`,
  `AiTokenPayload`, `AiResponsePayload`, `AgentTaskCreatedPayload`,
  `PlanStepSchema`, `AgentPlanPayload`, `AgentStepPayload`,
  `AgentObservePayload`, `AgentCompletePayload`, `AgentErrorPayload`, and
  extended the `JarvisEvent` discriminated union with 9 new variants
  (`ai.request`, `ai.token`, `ai.response`, `agent.task.created`,
  `agent.plan`, `agent.step`, `agent.observe`, `agent.complete`,
  `agent.error`).
- `packages/contracts/python/jarvis_contracts/events.py` — mirrored all of
  the above in pydantic v2, alias-compatible (camelCase wire format) with
  the TS source.
- `packages/contracts/python/jarvis_contracts/__init__.py` — exports
  updated for the new event/payload classes.
- `apps/backend/src/jarvis_backend/config.py` — rewritten: added
  `ProviderConfig`, `RoutingTarget`, `RoutingRule`, `RoutingConfig`,
  `RetryPolicy`, `ResourceLimits`, JSON-env-var-driven with built-in
  defaults matching the project's Ollama/Qwen/DeepSeek mandate.
- `apps/backend/src/jarvis_backend/main.py` — rewritten as the Phase 2
  composition root: `build_provider`, `build_orchestrator`, FastAPI
  `lifespan` wiring provider health checks and graceful shutdown.
- `apps/backend/src/jarvis_backend/api/__init__.py` — wired in
  `routes_ai.router`.
- `apps/backend/pyproject.toml` — `httpx` promoted from dev-only to a core
  dependency; added `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`,
  `live_ollama` marker).

### Dependencies added

| Package | Scope | Reason |
|---|---|---|
| `httpx` | Core (was dev-only) | `OllamaProvider` needs it at runtime for streaming NDJSON from Ollama's HTTP API |

No new TypeScript/Node dependencies. No new Python dev dependencies (all
were already anticipated in Phase 0's `[dev]` extras: `pytest`,
`pytest-asyncio`, `httpx`, `ruff`, `mypy`).

### Remaining TODOs (tracked in `ARCHITECTURE.md` §9, not silently dropped)

1. **SafetyGate `PROMPT`-tier → `DENY` fallback** — no backend→shell
   permission RPC exists yet; scoped to Phase 4 (ADR-0004).
2. **Non-durable state** — `TaskLedger`, `SafetyGate`'s audit log, and
   `WorkingMemory` are all in-process only; Phase 4's persistence layer
   addresses all three together (ADR-0007).
3. **`RetrievalPipeline` compression threshold** not yet exposed via typed
   `Settings` — deferred pending an actual tuning need (ADR-0007).
4. **Contract drift prevention** (TS ↔ Python `events.ts`/`events.py`) is
   still review-discipline-only, no automated CI check — carried from
   Phase 1.
5. **No live `pytest`/`mypy` run performed** — this sandbox has no
   network access to PyPI. Verification performed instead: `py_compile`
   across every file, full tokenization pass, and two scripted
   import-resolution checks (cross-package via `__init__.py` exports, and
   absolute/relative module resolution to real definitions) — all passed
   with zero issues found. **Action required before merge:** run
   `pip install -e ".[dev]" && pytest && mypy src` in a networked
   environment.
6. Carried from Phase 1, still open: bloom postprocessing not wired,
   renderer WS port is convention-based not dynamically delivered,
   renderer production build output path not wired to shell's expected
   location (Phase 4 packaging concern).

---

## Phase 4 — Memory Persistence + Security Center

**Added:** `persistence/` (database.py + 5 repositories), `security/`
(types, config, 6 monitors, threat_scoring, security_center, __init__),
`agents/permission_broker.py`, `memory/sqlite_long_term_memory.py`,
`api/routes_permission.py`, `api/routes_settings.py`,
`apps/shell/src/main/backend/PermissionBridge.ts`,
`apps/renderer/src/state/persistence.ts`,
`apps/renderer/src/state/slices/preferencesSlice.ts`,
`docs/ADR-0012...md`, `docs/ADR-0013...md`, 4 new backend test files
(`test_persistence.py`, `test_permission_broker.py`,
`test_security_center.py`, plus existing suite extended).

**Modified:** `agents/task_ledger.py` (durable write-through, Protocol-typed,
backward-compatible), `agents/safety_gate.py` (PermissionBroker + audit
persistence, backward-compatible), `main.py` (full Phase 4 composition
root), `config.py` (+db_path, +security_settings_json), `memory/__init__.py`,
`api/__init__.py`, `packages/contracts/{src,python}` (permission.request
event, verified TS/Python parity), `apps/shell/src/main/index.ts` (wires
PermissionBridge), `apps/shell/src/main/ipc/permissions.ts` (updated
docstring), `apps/renderer/src/state/store.ts` (+PreferencesSlice),
`apps/renderer/src/routes/SettingsRoot.tsx` (now editable/persisted),
`pyproject.toml` (+aiosqlite, numpy promoted core, +[security] extras).

**Dependencies added:** `aiosqlite>=0.20.0` (core), `numpy` promoted from
voice-only to core, `psutil>=6.0.0` (new `[security]` extras).

**Remaining TODOs:** brute-force vector search (fine at current scale);
minimal-by-design knowledge graph; Windows-only monitors no-op elsewhere
by design; no TS-side test coverage for PermissionBridge; same
no-live-pytest sandbox limitation as every prior phase.
