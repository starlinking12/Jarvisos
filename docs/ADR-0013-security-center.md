# ADR-0013: Security Center — Monitors, Threat Scoring, Platform Scope

**Status:** Accepted
**Date:** 2026-07-25
**Phase:** 4 — Memory Persistence + Security Center

## Context

The project mandate specifies a defensive Security Center covering
process, startup, registry, scheduled-task, file-integrity, and network
monitoring, with threat scoring and an audit log — and the `security.alert`
event schema has existed, unpublished, since Phase 0. Two real constraints
shape this phase: the project is Windows-first, but several of its own
monitoring categories (startup persistence, registry keys, scheduled
tasks) are Windows-specific concepts with no meaningful cross-platform
equivalent; and a security monitor that floods the user with every raw
signal it observes is worse than no monitor, so raw findings need a
scoring layer between detection and alerting.

## Decision

**`SecurityMonitor` protocol**, one implementation per category:
`ProcessMonitor`, `NetworkMonitor` (both cross-platform via `psutil`,
`[security]` extras), `StartupMonitor`, `RegistryMonitor`,
`ScheduledTaskMonitor` (all Windows-only, `sys.platform` guarded),
`FileIntegrityMonitor` (fully cross-platform, pure `hashlib`). Each
`scan()`s independently and returns `SecurityFinding`s; `SecurityCenter`
orchestrates all of them on a configurable interval (default 5 minutes).

**Platform scope, stated plainly rather than faked:** `StartupMonitor`,
`RegistryMonitor`, and `ScheduledTaskMonitor` return an empty finding
list with a logged notice on non-Windows platforms — there is no
Linux/macOS equivalent to a Windows Run key or Scheduled Task worth
inventing a substitute for. This is the same graceful-degradation pattern
already established for optional native audio dependencies
(`NullNoiseSuppressor`/`NullEchoCanceller`, `voice/vad/audio_processing.py`)
and for genuinely-unavailable native packages
(`AudioBackendUnavailableError` and siblings) — honest "not applicable
here," never a fabricated result standing in for missing coverage.

**`ThreatScorer`** sits between raw findings and what actually gets
alerted/persisted. Its one real rule for Phase 4: a finding's severity
escalates one level if its category has produced findings across
`escalation_threshold` (default 3) consecutive scan cycles — a
persistent condition is more actionable than a one-off, and this alone
meaningfully reduces alert fatigue from transient/expected findings
without needing a full correlation/ML-based scoring engine, which is
explicitly out of scope for what a local desktop assistant's built-in
monitor should be.

**One monitor's failure never blocks the others.**
`SecurityCenter.run_scan_cycle()` wraps each monitor's `scan()` in its
own try/except — a `psutil` permission error on `NetworkMonitor`, for
instance, never prevents `FileIntegrityMonitor` from running that cycle.

**Every finding is both persisted and published live**, mirroring
`AuditRepository`'s dual-purpose rationale (ADR-0012): `SecurityRepository`
gives a durable, queryable history; the `security.alert` event (finally
given a real publisher, three phases after its schema was defined) gives
real-time observability to any subscriber — a future Security Center HUD
widget needs zero backend changes to consume this.

## Rationale

- **Protocol-per-monitor, orchestrated centrally**, not one monolithic
  "scan everything" function — the same reasoning as every other
  provider boundary in this project: each monitor is independently
  testable, independently replaceable (a future ML-based process
  anomaly detector satisfies the same `SecurityMonitor` shape), and
  independently able to fail without taking down the others.
- **`sys.platform` guards over silently-empty stub monitors on
  non-Windows platforms:** the explicit log line ("not applicable on
  this platform") is what keeps this an honest architectural choice
  rather than a silent gap a user might mistake for "nothing to report."
- **Escalation-based scoring, not raw-finding alerting:** a monitor that
  fires the moment ANY unrecognized startup entry exists would alert on
  the very first scan of a normal, healthy machine (most machines have
  several legitimate startup entries an allowlist hasn't been
  configured for yet) — escalation-by-persistence is a real, simple
  filter for "this is worth a user's attention" that doesn't require a
  maintained threat-intelligence feed this project has no way to keep
  current.

## Consequences

- Any future monitor (e.g. a Phase 5+ USB-device-change monitor) is a new
  class satisfying `SecurityMonitor`, registered in
  `main.py`'s `build_security_center` — no `SecurityCenter` changes.
- `ThreatScorer`'s escalation state is per-`SecurityCenter`-instance and
  resets on backend restart — a category with a genuinely persistent
  issue re-escalates within `escalation_threshold` scan cycles after
  restart, not instantly; acceptable given scan intervals are minutes,
  not the restart cadence.
- The Security Center is opt-in (`SecuritySettings.enabled = False` by
  default), mirroring the Voice Engine's posture (ADR-0010) — a
  standing background monitor with `psutil` process/network visibility
  is itself a meaningful capability that shouldn't silently activate.
- `security.alert`'s `requires_approval` field (defined since Phase 0)
  is now genuinely set by monitors/`ThreatScorer` for `CRITICAL`-severity
  findings — a future Security Center UI can filter on it to distinguish
  "for your awareness" from "needs a decision," though the interactive
  decision flow itself is a later-phase UI concern, not built here.

## Alternatives Considered

- **A single cross-platform "system monitor" abstraction hiding the
  Windows-specific categories behind a generic interface:** rejected —
  would either force a fake cross-platform implementation (violating
  "no placeholders") or leak platform-conditional behavior into a
  supposedly-generic interface, neither of which is cleaner than six
  concrete monitors that are honest about what they cover.
- **Real-time (event-driven) monitoring instead of periodic scanning**
  (e.g. Windows registry change notifications, file system watchers):
  rejected for Phase 4 — meaningfully more complex (OS-specific
  notification APIs per category) for a security posture where a
  5-minute-granularity periodic scan is an acceptable trade-off for a
  local desktop assistant, not a high-security production server.
  Revisit specific categories (file integrity is the most natural
  candidate) if real-time detection latency becomes a measured need.
- **A maintained denylist/threat-signature database bundled with the
  product:** rejected — this project has no mechanism to keep such a
  database current, and shipping a stale one would be actively
  misleading (implying protection the product doesn't actually provide).
  User-configurable denylists (`SecuritySettings.process_denylist`) are
  the honest scope: the user's own knowledge of their environment, not a
  vendored threat feed.
