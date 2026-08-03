# ADR-0001: Electron Shell + Python AI Backend, Contract-First & Event-Driven

**Status:** Accepted
**Date:** 2026-07-18
**Phase:** 0 — Foundational Architecture

## Context

JARVIS OS is a Windows-first AI operating environment, not a conventional desktop
app. It requires a transparent always-on-top HUD, a click-through desktop overlay,
multiple coordinated windows, deep native desktop automation, Three.js/React Three
Fiber rendering, CesiumJS 3D Earth, and a large Python-based AI backend (agents,
memory, vision, voice, planning). Two runtime shells were evaluated: Tauri (Rust
core) and Electron (Node/Chromium core).

## Decision

We build on **Electron**, not Tauri, with a strict separation of responsibilities:

- **Electron (Node.js + Chromium)** owns everything about being a desktop
  application: window lifecycle, the overlay window, tray icon, global shortcuts,
  the Python backend supervisor process, the secure IPC bridge, and the OS
  permission model.
- **Python (FastAPI + asyncio)** owns everything about being intelligent: agent
  orchestration, memory, vision, voice, automation/tool execution, and planning.
- **React + TypeScript + Vite** renders the UI inside Electron's renderer
  processes, using Three.js / React Three Fiber for the Arc Reactor core and
  holographic panels, Framer Motion for transitions, and Zustand for UI state.

The two runtimes never talk to each other directly. All communication crosses a
**contract-first, event-driven boundary**: TypeScript and Python each hold a
generated/mirrored copy of the same event and IPC schemas, defined once in
`packages/contracts`. Electron's main process supervises the Python backend as a
child process and bridges renderer IPC to backend events over a local WebSocket
(with a stdio fallback for boot-time health checks before the HTTP/WS server is
up).

## Rationale

- **Ecosystem maturity for exactly the features required.** Transparent
  click-through overlays, multi-window HUD composition, tray integration, global
  shortcuts, and mature native module support (screen capture, window
  enumeration, UI Automation bindings on Windows) are all well-trodden ground in
  Electron. Tauri's Rust core is lighter weight, but desktop automation and
  overlay behavior on Windows would require more custom native work with a
  smaller ecosystem to draw on.
- **Team velocity.** The stack is Node/TypeScript end-to-end on the shell side
  and Python end-to-end on the AI side — no third language (Rust) in the critical
  path, which matters for a fast-moving, rapidly-iterating Phase 0–3 roadmap.
- **Python is non-negotiable for the AI backend.** Ollama tooling, embeddings,
  vision models, and the broader local-AI ecosystem are Python-first. Electron's
  main process is a natural supervisor for a long-running Python sidecar
  regardless of shell choice, so this part of the decision is orthogonal to
  Tauri vs. Electron.

## Trade-offs Accepted

- **Memory/footprint:** Electron's Chromium + Node overhead is materially larger
  than Tauri's WebView2-based footprint. Mitigated by lazy-loading heavy
  renderer bundles (Three.js/Cesium scenes) per-window and by keeping the
  overlay window's renderer minimal.
- **Two runtimes to supervise (Node + Python) instead of one (Rust) plus a
  sidecar.** This is accepted because it was already required for the AI
  backend under either shell choice — Tauri would also need a Python sidecar.
- **Security surface:** Electron requires disciplined `contextIsolation`,
  disabled `nodeIntegration` in renderers, and a narrow `preload` bridge. This is
  enforced as a hard rule (see `apps/shell/src/main/ipc`), not an afterthought.

## Consequences

- All cross-process communication must go through `packages/contracts`. No
  renderer, main process module, or Python module may hand-roll an ad-hoc
  message shape.
- The Python backend must be independently runnable and testable without
  Electron (it exposes a normal FastAPI app + WebSocket event stream).
- Every new IPC channel or backend event requires a contract entry before
  implementation — this is enforced by code review, and later by a schema-drift
  CI check (Phase 2+).

## Alternatives Considered

- **Tauri + Rust core:** rejected for this phase per explicit product direction
  and the overlay/automation ecosystem gap noted above. Revisit only if
  Electron's footprint becomes a measured, user-facing problem.
- **Single Python process with a lightweight webview (e.g. pywebview):**
  rejected — insufficient control over multi-window HUD composition, overlay
  click-through behavior, and native tray/shortcut integration on Windows.
