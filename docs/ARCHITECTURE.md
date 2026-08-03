# JARVIS OS — Architecture & Project Memory

This file is the living source of truth for architecture, dependencies,
and file inventory. See **`ROADMAP.md`** for the phase-by-phase plan and
**the ADR log below** for individual architecture decisions in depth.

**Product posture:** JARVIS OS is engineered as a commercial-grade
product — every architectural decision is made as if it will ship to and
be supported for hundreds of thousands of end users. Contracts are
versioned deliberately, no subsystem is built in a way that blocks later
packaging/licensing work, and nothing is implemented as a demo shortcut
that would need to be rebuilt for production.

---

## 1. System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│                            Electron Shell (Node)                          │
│  WindowManager / OverlayWindow / TrayManager / GlobalShortcuts            │
│  BackendSupervisor (spawns/watches python child) ── IpcBridge             │
└──────────────────────────────┬──────────────────────────────────────────┘
                                │ contextBridge (native/high-impact actions only)
┌──────────────────────────────▼──────────────────────────────────────────┐
│                  Renderer (@jarvis/renderer — React/R3F)                  │
│  HudRoot / OverlayRoot / SettingsRoot / CommandPaletteRoot                │
│  EventBusClient ──(WS, read-only)──┐        POST /ai/chat ──(HTTP)──┐    │
└─────────────────────────────────────┼──────────────────────────────┼────┘
                                       │                              │
┌──────────────────────────────────────▼──────────────────────────────▼────┐
│                     Python Backend (FastAPI + asyncio)                    │
│                                                                             │
│  EventBus ── Orchestrator (top tier — sole user-facing component)         │
│                 │            ▲                                            │
│                 │            │ handle_user_message() — shared entry point │
│                 │            │ for both /ai/chat AND voice transcripts    │
│                 ├─ Planner   │                                            │
│                 ├─ TaskLedger│                                            │
│                 ├─ RetrievalPipeline (WorkingMemory + LongTermMemory)     │
│                 ▼            │                                            │
│         DomainAgent × 8 ─────┘                                            │
│                 ▼                                                          │
│         ToolExecutor + ToolRegistry (gated by SafetyGate) ── voice.speak  │
│                 ▼                                                          │
│         ModelRouter ── OllamaProvider / MockProvider                      │
│                                                                             │
│  ── Phase 3: VoiceEngine (state machine) ──────────────────────────────  │
│  WAKE_LISTENING → LISTENING → TRANSCRIBING → THINKING → SPEAKING          │
│  MicrophoneManager/SpeakerManager (sounddevice) ── AudioStreamingPipeline │
│  WebRtcVadProvider ── OpenWakeWordProvider ── WhisperCppProvider (STT)    │
│  PiperProvider (TTS) ── BargeInController (sub-150ms interrupt)           │
│  gated by SafetyGate's audio.microphone scope (ADR-0011)                  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Golden rule (unchanged since Phase 0):** Electron and Python never share
memory or call into each other directly. The renderer talks to the
backend via a read-only WebSocket event stream (Phase 1) and a direct
HTTP `POST /ai/chat` (Phase 2) — both bypass Electron's IPC bridge because
neither touches native/OS state. **Phase 3 adds no new renderer-facing
surface** — voice is entirely backend-internal, observable only through
the `voice.*` events already flowing over the existing WebSocket
connection; a future voice HUD widget needs zero new plumbing.

---

## 2. Monorepo Layout (current — Phase 0 + 1 + 2 + 3)

```
jarvis-os/
├── docs/
│   ├── ADR-0001 … ADR-0004, ADR-0006 … ADR-0011  (ADR-0005 reserved, Phase 5 plugin manifest)
│   ├── ARCHITECTURE.md (this file) / ROADMAP.md / CHANGELOG.md
├── apps/
│   ├── shell/, renderer/           # unchanged this phase
│   └── backend/
│       ├── pyproject.toml           # + [voice] extras group (Phase 3)
│       ├── src/jarvis_backend/
│       │   ├── main.py              # + build_voice_engine, OrchestratorBundle (Phase 3)
│       │   ├── config.py            # + voice_settings_json field (Phase 3)
│       │   ├── ai/, agents/, memory/, api/    # unchanged this phase
│       │   └── voice/               # NEW — 25 files (ADR-0010, ADR-0011)
│       │       ├── types.py           # AudioConfig/Frame, VoiceState, protocols
│       │       ├── config.py          # VoiceSettings (JSON-env-var pattern)
│       │       ├── voice_engine.py    # the state machine
│       │       ├── barge_in.py        # sub-150ms interrupt controller
│       │       ├── tools.py           # voice.speak → ToolRegistry
│       │       ├── audio/             # device_manager, microphone, speaker,
│       │       │                      # ring_buffer, pipeline (5 files)
│       │       ├── vad/               # provider, webrtc_vad_provider,
│       │       │                      # audio_processing (AGC/NS/AEC) (3 files)
│       │       ├── wake_word/         # provider, openwakeword_provider (2 files)
│       │       ├── stt/               # provider, whisper_cpp_provider (2 files)
│       │       └── tts/               # provider, piper_provider (2 files)
│       └── tests/                   # 26 files total, +7 voice tests this phase
└── packages/
    └── contracts/         # + voice.* events (9 new types) + audio.microphone
                            # PermissionScope (Phase 3), both TS and Python
```

---

## 3. Process & IPC Boundaries (unchanged this phase)

No new boundaries — see Phase 2's table (§3 in prior revisions). Phase 3's
`VoiceEngine` runs entirely within the backend process; its only external
surface is the `voice.*` events it publishes to the same `EventBus` every
other backend subsystem already uses, consumed identically by whichever
client (main process, renderer) is subscribed to the WebSocket stream —
no voice-specific transport was added.

---

## 4. Dependencies (cumulative — Phase 0 + 1 + 2 + 3)

### Python — `apps/backend`, new `[voice]` extras group (Phase 3)
| Package | Purpose | Required for |
|---|---|---|
| `numpy` | Audio sample arrays, DSP (AGC) | Core voice functionality |
| `sounddevice` | PortAudio bindings — mic capture, speaker playback | `MicrophoneManager`, `SpeakerManager` |
| `webrtcvad` | Voice activity detection | `WebRtcVadProvider`, barge-in |
| `openwakeword` | Wake-word detection | `OpenWakeWordProvider` |

**Not pip packages** (external binaries, invoked via subprocess — see
ADR-0010): whisper.cpp (`whisper-cli`/`main` binary, user-built or
downloaded) and Piper (`piper` binary, `pip install piper-tts` or a
release download both work since only the binary is invoked, not a
Python API).

All four `[voice]` packages are optional — installing JARVIS OS without
`pip install "jarvis-backend[voice]"` and without setting
`JARVIS_VOICE_SETTINGS_JSON`'s `enabled: true` runs identically to a
Phase 2 build. No core dependency changed.

### TypeScript / Node — unchanged this phase.

Still deferred (unchanged from Phase 1's follow-ups): CesiumJS,
`@react-three/postprocessing`.

---

## 5. Setup (Phase 3 additions)

```bash
# Core setup unchanged — see Phase 2's instructions above/in git history.

# To enable voice:
cd apps/backend
pip install -e ".[dev,voice]"

# Build/obtain whisper.cpp and Piper binaries (not pip-installable):
#   whisper.cpp: https://github.com/ggerganov/whisper.cpp — build `whisper-cli`,
#     download a ggml model (e.g. ggml-base.en.bin) into models/
#   Piper: pip install piper-tts (bundles a `piper` binary), or download a
#     release from https://github.com/rhasspy/piper — download a voice
#     .onnx model into voices/

# Enable + configure voice via env var (JSON):
export JARVIS_VOICE_SETTINGS_JSON='{"enabled": true}'

# SafetyGate denies audio.microphone by default (ADR-0011) — voice will
# start but immediately publish voice.error until a SafetyPolicy override
# is configured allowing it (interactive approval lands in Phase 4):
# see main.py's build_orchestrator / SafetyPolicy construction.
```

---

## 6. Testing Strategy (Phase 3 additions)

7 new test modules, all hardware-independent (no real audio device,
webrtcvad/openwakeword install, or whisper.cpp/Piper binary required):
- `test_ring_buffer.py` — write/read correctness, overflow, wraparound
  (pure numpy).
- `test_audio_processing.py` — `SoftwareAgc` gain behavior, null-object
  NS/AEC passthrough, `AudioProcessingChain` composition (pure numpy).
- `test_voice_config.py` — `VoiceSettings` defaults and JSON overrides
  (pure pydantic).
- `test_whisper_cpp_provider.py` — binary-not-found error, WAV-writing
  helper, timestamp parsing (no whisper.cpp binary needed — tests use a
  fake executable file for the "binary exists" path and pure-function
  tests for parsing logic).
- `test_piper_provider.py` — binary-not-found error, voice listing,
  unknown-voice error (same fake-executable pattern).
- `test_barge_in.py` — `RawSpeechDetector`, `BargeInController`,
  `race_playback_against_barge_in`, all with fakes satisfying the exact
  shapes those classes depend on.
- `test_voice_engine_integration.py` — the full `VoiceEngine` state
  machine (wake → listen → transcribe → think → speak, plus the barge-in
  interrupt path and the microphone-permission-denied path), with fakes
  for every hardware-backed protocol (`AudioSource`/`AudioSink`/
  `VadProvider`/`WakeWordProvider`/`SttProvider`/`TtsProvider`) and a
  **real** `Orchestrator` (via `conftest.py`'s existing `MockProvider`-backed
  fixtures) — genuinely exercises the Voice Engine ↔ Orchestrator
  integration end to end.

This hardware independence is a direct payoff of ADR-0010's
protocol-based provider design: `VoiceEngine`/`AudioStreamingPipeline`/
`BargeInController` depend on `AudioSource`/`AudioSink`/`VadProvider`
protocols, never on the concrete `MicrophoneManager`/`SpeakerManager`/
`WebRtcVadProvider` classes, so fakes satisfying those protocols are
sufficient for full state-machine coverage in CI with zero native
dependencies.

A `live_voice_hardware` pytest marker is registered (mirroring
`live_ollama`) for future tests that do want to exercise real hardware/
native providers — none exist yet, since Phase 3's fakes already achieve
full state-machine coverage without needing them; a live smoke test
against real `sounddevice`/`webrtcvad`/`openwakeword` is a reasonable
Phase 4+ addition once real deployment feedback identifies gaps the fakes
don't cover.

**Verification performed this phase** (same method as Phase 2, since this
sandbox still has no PyPI/npm access): `py_compile` across all 82 Python
files (56 backend src + 26 tests, up from 50/19 respectively at the end
of Phase 2), full tokenization pass, and the same two scripted
import-resolution checks (cross-package via `__init__.py` exports,
absolute/relative module resolution to real definitions) — **zero
unresolved references found**, including across the new `voice/` package
and its 7 new test modules. Three pre-existing checker false positives
(top-level `try/except` assignments invisible to the naive AST scan,
confirmed by manual inspection) are noted, not treated as real issues.
**Action required before merge, same as Phase 2:** run
`pip install -e ".[dev,voice]" && pytest && mypy src` in a networked
environment.

---

## 7. ADR Log

| ID | Title | Status |
|---|---|---|
| [ADR-0001](./ADR-0001-electron-python-architecture.md) | Electron shell + Python AI backend, contract-first & event-driven | Accepted |
| [ADR-0002](./ADR-0002-model-router.md) | ModelRouter — provider abstraction & task-based routing | Accepted |
| [ADR-0003](./ADR-0003-streaming-event-protocol.md) | Streaming protocol & the `ai.*`/`agent.*` event sequence | Accepted |
| [ADR-0004](./ADR-0004-task-ledger-safety-gate.md) | Task Ledger & SafetyGate — agent governance | Accepted |
| [ADR-0006](./ADR-0006-animation-engine.md) | Three-tier animation architecture | Accepted |
| [ADR-0007](./ADR-0007-memory-integration.md) | Memory integration — working memory, long-term interface, retrieval | Accepted |
| [ADR-0008](./ADR-0008-three-tier-agent-hierarchy.md) | Three-tier agent hierarchy — Orchestrator, Domain Agents, Tool Executors | Accepted |
| [ADR-0009](./ADR-0009-state-architecture.md) | Slice-composed Zustand store with narrow selector subscriptions | Accepted |
| [ADR-0010](./ADR-0010-voice-engine-architecture.md) | Voice Engine architecture — provider abstractions & subsystem integration | Accepted |
| [ADR-0011](./ADR-0011-barge-in-and-microphone-permission.md) | Barge-in design & the `audio.microphone` permission model | Accepted |
| [ADR-0012](./ADR-0012-persistence-and-permission-broker.md) | Local-first persistence layer & the permission broker | Accepted |
| [ADR-0013](./ADR-0013-security-center.md) | Security Center — monitors, threat scoring, platform scope | Accepted |

*(ADR-0005 remains reserved for Phase 5's plugin manifest format.)*

---

## 8. Roadmap

See **`ROADMAP.md`**. Phase 3 (Voice Engine) is complete; Phase 4 (Memory
Persistence + Security Center) is next, pending approval.

---

## 9. Known Follow-Ups (cumulative — carried + new)

**Carried from Phase 1/2 (still open):** bloom postprocessing not wired;
renderer WS port convention-based; renderer production build output path
not wired to shell; TS↔Python contract drift prevention is review-only;
`SafetyGate` `PROMPT`-tier resolves to `DENY` (no backend→shell permission
RPC yet); `TaskLedger`/audit log/`WorkingMemory` non-durable;
`RetrievalPipeline` compression threshold not yet in typed `Settings`.

**New this phase:**
- Real-time noise suppression and echo cancellation are `NullNoiseSuppressor`/
  `NullEchoCanceller` (real null-object passthroughs, not placeholders —
  see `vad/audio_processing.py`'s module docstring) until a native NS/AEC
  backend (WebRTC APM, RNNoise, or similar) is integrated — tracked as a
  Phase 5 item alongside other native-dependency work.
- `audio.microphone` permission scope inherits the same `PROMPT`→`DENY`
  limitation as every other scope (ADR-0004) — enabling voice today
  requires an explicit `SafetyPolicy` config override, not an in-the-moment
  consent dialog. Same root cause as the carried-over item above, now with
  a second scope depending on its resolution.
- `WhisperCppProvider`'s "streaming partials" are word-level pseudo-streaming
  (whisper.cpp decodes the already-captured utterance and emits words as
  it decodes them — see ADR-0010) rather than mid-capture incremental
  transcription; genuinely low-latency, but distinct from an ASR engine
  that transcribes while audio is still arriving. A future streaming-native
  ASR provider could improve on this without any `SttProvider` protocol
  change.
- No live smoke test against real audio hardware/native voice
  dependencies exists yet (see §6) — the `live_voice_hardware` pytest
  marker is registered and ready for one once real deployment feedback
  identifies what it should specifically cover.

---

## 10. File Inventory

| Area | Status |
|---|---|
| `apps/shell/*`, `apps/renderer/*` | Unchanged this phase |
| `packages/contracts/*` | ✅ Modified — 9 `voice.*` event types + `audio.microphone` scope (TS + Python) |
| `apps/backend/src/jarvis_backend/config.py` | ✅ Modified — `voice_settings_json` field |
| `apps/backend/src/jarvis_backend/main.py` | ✅ Modified — `build_voice_engine`, `OrchestratorBundle` |
| `apps/backend/src/jarvis_backend/agents/safety_gate.py` | ✅ Modified — `AUDIO_MICROPHONE` scope |
| `apps/backend/src/jarvis_backend/voice/` (25 files) | ✅ New |
| `apps/backend/tests/` (+7 voice test files) | ✅ New |
| `apps/backend/pyproject.toml` | ✅ Modified — `[voice]` extras, `live_voice_hardware` marker |
| `docs/ADR-0010`, `docs/ADR-0011` | ✅ New |
| `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md` | ✅ Updated |

Total backend source files: **56** (was 31 at end of Phase 2). Total
backend test files: **26** (was 19). Total docs: **13**.

---

## 11. Phase 4 Addendum — Memory Persistence + Security Center

**New subsystems:** `persistence/` (Database + 5 repositories, SQLite via
`aiosqlite`), `security/` (6 monitors + ThreatScorer + SecurityCenter),
`agents/permission_broker.py`, `memory/sqlite_long_term_memory.py`.

**Modified:** `TaskLedger` and `SafetyGate` gained optional
Protocol-typed repository/broker dependencies with zero breaking changes
(every Phase 2/3 call site and test is unaffected — see ADR-0012).
`main.py` now constructs a `Database` in `lifespan` and passes it through
`build_orchestrator`. `config.Settings` gained `db_path`,
`security_settings_json`. Shell gained `PermissionBridge.ts` (backend↔shell
permission RPC). Renderer gained `PreferencesSlice` + `state/persistence.ts`
(backend-API-backed settings) and `SettingsRoot` is now genuinely editable.

**New contracts:** `permission.request` event (TS + Python, verified
parity), `audio.microphone`-adjacent `PermissionRequestScope` mirror.

**New dependencies:** `aiosqlite` (core), `numpy` (promoted core→ from
voice-only), `psutil` (new `[security]` extras).

**New ADRs:** ADR-0012 (persistence + permission broker), ADR-0013
(Security Center).

**Verification:** 110 Python files compile; cross-package import
resolution checked against all 16 package `__init__.py` files, zero
unresolved references. Same sandbox limitation as every prior phase — no
live `pytest`/`mypy` run; run `pip install -e ".[dev,voice,security]" &&
pytest && mypy src` before merging.

**Known follow-ups:** vector search is brute-force cosine similarity
(fine at current scale, revisit if corpus grows — ADR-0012); knowledge
graph is minimal by design, not general-purpose; Security Center's
Windows-specific monitors (startup/registry/scheduled-task) are
no-ops on non-Windows platforms by design (ADR-0013); `PermissionBridge`
reconnects with backoff but has no test coverage from the TS side (no TS
test runner configured yet in this project — tracked as a Phase 5 gap).
