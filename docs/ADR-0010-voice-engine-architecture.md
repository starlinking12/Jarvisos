# ADR-0010: Voice Engine Architecture — Provider Abstractions & Subsystem Integration

**Status:** Accepted
**Date:** 2026-07-21
**Phase:** 3 — Voice Engine

## Context

The project mandate requires a full local-first voice pipeline — audio
device I/O, wake-word detection, voice activity detection, streaming
speech-to-text, streaming text-to-speech — that integrates with every
subsystem Phase 2 already built (`EventBus`, `ModelRouter`, `Orchestrator`,
`ToolRegistry`, `SafetyGate`) rather than existing as a parallel,
disconnected feature. It also mandates that "individual providers (STT,
TTS, wake-word engine, VAD, noise suppression, audio backend) can be
replaced without modifying higher-level application logic" — the same
replaceability requirement ADR-0002 established for `ModelRouter`,
extended here to every voice-specific engine.

## Decision

**Six provider protocols**, one per swappable engine, all structurally
typed (`typing.Protocol`, the same pattern as `ModelProvider` in
`ai/types.py`): `AudioSource`/`AudioSink` (audio I/O), `VadProvider`,
`WakeWordProvider`, `SttProvider`, `TtsProvider`. Each has exactly one
Phase 3 concrete implementation:

| Protocol | Phase 3 implementation | Backing technology |
|---|---|---|
| `AudioSource` | `MicrophoneManager` | `sounddevice` (PortAudio) |
| `AudioSink` | `SpeakerManager` | `sounddevice` (PortAudio) |
| `VadProvider` | `WebRtcVadProvider` | `webrtcvad` |
| `WakeWordProvider` | `OpenWakeWordProvider` | `openwakeword` |
| `SttProvider` | `WhisperCppProvider` | whisper.cpp (subprocess) |
| `TtsProvider` | `PiperProvider` | Piper (subprocess) |

**`VoiceEngine`** (`voice/voice_engine.py`) is the composition point — a
single state machine (`VoiceState`: IDLE → WAKE_LISTENING → LISTENING →
TRANSCRIBING → THINKING → SPEAKING, with barge-in as a state-preserving
interrupt — see ADR-0011) that depends only on the six protocols above,
never on a concrete provider class. `main.py`'s `build_voice_engine`
constructs the concrete providers and injects them, mirroring
`build_orchestrator`'s existing composition-root pattern from Phase 2.

**Subsystem integration, concretely:**
- **EventBus:** `VoiceEngine` publishes the full `voice.*` event sequence
  (`voice.wake`/`listening`/`partial`/`final`/`thinking`/`speaking`/
  `finished`/`interrupted`/`error`) at every state transition — the same
  "one component is the sole publisher of a given event family" discipline
  ADR-0003 established for `ai.*`/`agent.*` events.
- **ModelRouter:** `VoiceEngine` does not call `ModelRouter` directly for
  the conversational turn — it delegates entirely to `Orchestrator`
  (below), which already owns all `ModelRouter` interaction. This keeps
  "only the Orchestrator talks to the model for conversational responses"
  true regardless of whether the request originated from text (Phase 2)
  or voice (Phase 3).
- **Orchestrator:** the final transcript from STT is handed to
  `Orchestrator.handle_user_message()` — the exact same method
  `routes_ai.py`'s `POST /ai/chat` calls. Voice is a second *entry point*
  into the same conversational pipeline, not a parallel pipeline; a voice
  conversation and a typed conversation sharing a `conversation_id` share
  working memory identically.
- **ToolRegistry:** `voice/tools.py` registers `voice.speak`, letting any
  domain agent make the assistant speak proactively (see ADR-0008's
  three-tier hierarchy — this is a normal `ToolSpec`, executed through the
  same `ToolExecutor` choke point as every other tool).

**Optional native dependencies.** `sounddevice`, `webrtcvad`,
`openwakeword` live in a `[voice]` extras group (`pyproject.toml`), not
core dependencies — installing JARVIS OS without ever enabling voice
should not require building native audio bindings. Every provider
lazy-imports its dependency and raises a clear, actionable error
(`AudioBackendUnavailableError`, `WebRtcVadUnavailableError`,
`OpenWakeWordUnavailableError`, `WhisperCppBinaryNotFoundError`,
`PiperBinaryNotFoundError`) only when actually instantiated without it —
never at import time. `build_voice_engine` catches any such failure and
degrades to "voice disabled for this run" with a logged warning, rather
than crashing the whole backend.

**whisper.cpp and Piper via subprocess, not a Python binding.** Both are
invoked as external binaries (configurable path, resolved via `PATH` or
an absolute path) rather than through a Python C-extension binding. This
keeps their native build/toolchain requirements (CMake, a C++ compiler,
platform-specific acceleration backends) entirely outside this project's
Python dependency graph — a user builds whisper.cpp/Piper once, following
each project's own install instructions, and points JARVIS OS at the
resulting binary.

## Rationale

- **Protocol-based providers, not ABCs**, for the same reason as
  `ModelProvider` (ADR-0002): zero required-import coupling for a future
  provider (e.g. a Silero VAD, a Whisper-API-based STT, a neural
  emotion-capable TTS), and structural typing makes fakes trivial to
  write for hardware-independent tests (see §Testing in
  `ARCHITECTURE.md` and `test_voice_engine_integration.py`).
- **Subprocess over Python bindings for whisper.cpp/Piper** trades a
  small amount of per-call process-spawn overhead for a much smaller,
  more portable Python dependency footprint — appropriate given both are
  invoked at most once per utterance (STT) or per response (TTS), not in
  a tight per-frame loop where spawn overhead would matter.
- **Voice as a second entry point into the existing `Orchestrator`, not a
  parallel pipeline**, is what makes "every component must integrate with
  the existing... Orchestrator" true in the strongest sense: there is
  exactly one place conversational logic lives, regardless of input
  modality. This also means every future Orchestrator capability (tool
  use, memory, multi-step planning) is automatically available to voice
  interactions with zero additional Phase 3 code.

## Consequences

- Swapping any one voice engine (e.g. openWakeWord → a different
  wake-word model) is a `main.py`/`voice/config.py` change — no
  `VoiceEngine` code changes, per the mandate's explicit replaceability
  requirement.
- A JARVIS OS build with `[voice]` extras uninstalled and voice disabled
  in config starts and runs identically to a Phase 2 build — voice is
  strictly additive, never a hard requirement.
- Text and voice conversations sharing `conversation_id`-keyed working
  memory means a future "continue this voice conversation by typing"
  feature requires no new plumbing — it already works via existing
  `WorkingMemory` semantics (ADR-0007).

## Alternatives Considered

- **A separate `VoiceOrchestrator` distinct from `Orchestrator`:**
  rejected — would duplicate planning/tool-dispatch/memory-retrieval logic
  that `Orchestrator` already owns, violating "no duplicated logic across
  subsystems" for no clear benefit; voice-specific behavior (wake word,
  VAD, STT, TTS, barge-in) is entirely upstream/downstream of the
  conversational turn itself, not part of it.
- **Bundling a Python STT/TTS library (e.g. `faster-whisper`,
  `TTS`/Coqui) instead of subprocess-wrapped whisper.cpp/Piper:**
  rejected for Phase 3 — the mandate specifically names whisper.cpp and
  Piper, both C++/native projects without first-class pip-installable
  Python bindings mature enough to prefer over subprocess invocation;
  this can be revisited per-provider without touching the `SttProvider`/
  `TtsProvider` protocol if a compelling binding emerges later.
