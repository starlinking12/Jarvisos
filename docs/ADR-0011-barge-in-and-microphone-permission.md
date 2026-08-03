# ADR-0011: Barge-In Design & the `audio.microphone` Permission Model

**Status:** Accepted
**Date:** 2026-07-21
**Phase:** 3 — Voice Engine

## Context

Two requirements from the Phase 3 mandate are both genuinely
security/latency-critical rather than routine feature work: barge-in must
interrupt TTS playback the moment the user speaks, targeting under 150ms,
and every privileged operation must remain "auditable, permission-aware,
and compatible with the existing SafetyGate architecture." Activating a
live microphone is unambiguously a privileged, privacy-sensitive
operation — arguably the single most sensitive capability this project
has introduced since ADR-0004 established `SafetyGate` — and needed a
`PermissionScope` of its own, which did not exist before Phase 3.

## Decision

### Barge-in

`BargeInController` (`voice/barge_in.py`) runs a **hangover-free** VAD
check (`RawSpeechDetector`, wrapping the same underlying `webrtcvad.Vad`
engine `WebRtcVadProvider` uses, exposed via its new `raw_engine`
property) concurrently with TTS playback, via
`race_playback_against_barge_in` (`asyncio.wait(..., FIRST_COMPLETED)`).
The moment speech is detected, `SpeakerManager.stop()` is called directly
— no event, no queue, no async handoff between detection and the actual
audio halt.

**Deliberately not reusing `WebRtcVadProvider.is_speech()`** (the same
instance used for STT segmentation) — that method applies hangover
smoothing (a configurable window of trailing frames, so a single silent
frame mid-utterance doesn't fragment an utterance into multiple
`SpeechSegment`s for STT). That smoothing is correct for segmentation and
actively counterproductive for barge-in: it would add exactly the
hangover window's duration as extra interrupt latency, working against
the sub-150ms target for a benefit (segment continuity) that has no
meaning in the barge-in context.

**Latency budget** (see `barge_in.py`'s module docstring for the full
breakdown): ~20ms VAD frame + ~1ms inference + one output-callback period
(~10-20ms) ≈ 41ms worst case, well under the 150ms target with margin for
OS scheduling jitter.

**"Resume listening without restarting the pipeline"** is implemented
literally: the microphone's `sounddevice.InputStream` is never stopped or
recreated between `VoiceState` transitions — only *which part* of
`VoiceEngine`'s state machine is consuming its frame stream changes (see
`voice_engine.py`'s module docstring on single-consumer sequencing). On a
barge-in, `VoiceEngine` transitions directly from `SPEAKING` to
`LISTENING` (not back through `WAKE_LISTENING`), since the user is
already actively speaking — waiting for a fresh wake word would be an
unnecessary, user-hostile round trip.

### The `audio.microphone` permission scope

A new `PermissionScope` value, added identically to both the TypeScript
source (`packages/contracts/src/ipc-contracts.ts`) and its Python mirror
(`agents/safety_gate.py`) in the same commit, per the drift-prevention
discipline established in ADR-0001/ADR-0004. `VoiceEngine.start()` calls
`SafetyGate.check(PermissionScope.AUDIO_MICROPHONE, ...)` before ever
opening the microphone stream; a denial means the engine never starts,
publishing `voice.error` instead.

Under `SafetyGate`'s Phase 2 default-deny policy (ADR-0004), this means
voice is **denied by default** until explicitly allowed via
`SafetyPolicy` configuration — consistent with treating microphone access
with at least as much caution as the other high-impact scopes
(`filesystem.write`, `shell.execute`, etc.), arguably more, since a live
microphone is a standing capability (continuously active while
`WAKE_LISTENING`), not a single discrete action like a file write.

## Rationale

- **A separate raw, hangover-free VAD path for barge-in, reusing the
  underlying engine rather than a second VAD instance**, keeps CPU cost
  low (one loaded `webrtcvad.Vad` model, not two) while giving barge-in
  exactly the signal characteristics it needs — the two consumers
  (`WebRtcVadProvider.is_speech()` for segmentation,
  `RawSpeechDetector.is_speech()` for barge-in) are cheap wrappers around
  one shared native engine, not duplicated VAD logic.
- **Direct `SpeakerManager.stop()` call from within `BargeInController`,
  not an event-mediated interrupt**, is a deliberate exception to this
  project's usual "coordinate through the EventBus" pattern — event
  publication and subscription both add scheduling latency
  (`asyncio.Queue` handoff, subscriber wakeup), which barge-in's latency
  budget cannot absorb. The `voice.interrupted` event is still published
  (for HUD/observability), but *after* the stop has already happened, not
  as the mechanism that causes it.
- **Denying microphone access by default** treats "is always listening for
  a wake word" as the security-relevant state it actually is — a
  standing microphone-open capability is a materially different risk
  profile than a one-shot permission-gated action, and default-deny
  (with the same "resolves to DENY, not silently ALLOW, in the absence of
  a configured policy" posture ADR-0004 already established) is the only
  safe default here too.

## Consequences

- Any future audio-consuming feature (e.g. a Phase 5+ ambient-sound
  classification agent) reuses the same `AUDIO_MICROPHONE` scope rather
  than inventing a new one — one scope covers "is the microphone
  active," regardless of which subsystem activated it.
- Because `SafetyGate`'s `PROMPT`-tier resolves to `DENY` until Phase 4's
  backend→shell permission RPC exists (ADR-0004), an end-user-facing
  "allow JARVIS to listen" consent flow is not yet interactive — enabling
  voice today requires an explicit `SafetyPolicy` override in
  configuration, not an in-the-moment approval dialog. This is the same
  known limitation ADR-0004 already flagged, now with a second real
  scope depending on its resolution — tracked as a Phase 4 item, not
  newly introduced here.
- `WebRtcVadProvider.raw_engine` is a narrow, deliberately-documented
  exception to "prefer `is_speech()`" — any future caller reaching for
  `raw_engine` outside `BargeInController`'s specific latency-driven
  use case should be treated as a design smell in code review.

## Alternatives Considered

- **A dedicated barge-in VAD instance, separate `webrtcvad.Vad` model
  load, instead of sharing `WebRtcVadProvider`'s engine:** rejected —
  `webrtcvad.Vad` is stateless per call (no internal buffering that
  sharing would corrupt), so a second instance would only add memory/init
  cost with no isolation benefit.
- **Publishing `voice.interrupted` and having `VoiceEngine`'s event
  handler call `stop()` in response:** rejected per Rationale — this is
  exactly the extra latency hop the 150ms budget cannot afford; measured
  against `SpeakerManager.stop()`'s own ~20ms bound, even a fast
  event-loop round trip would meaningfully erode the margin.
- **`PROMPT`-tier default for `audio.microphone` instead of `DENY`:**
  considered, rejected — `PROMPT` currently resolves to `DENY` anyway
  (ADR-0004), so this would be a distinction without a runtime
  difference today, while implying a "will ask nicely" semantic that
  doesn't yet exist. Revisit once Phase 4's interactive approval flow is
  real.
