# ADR-0014: Desktop Intelligence & Safety-Gated Automation

**Status:** Accepted
**Date:** 2026-08-08
**Phase:** 5 — Desktop Intelligence + Automation + Packaging

## Context

Phase 5 is the first JARVIS OS phase that gives an agent real control over
the user's desktop. The project already has the architectural boundaries
needed for this: `Orchestrator` is the sole user-facing tier, `DomainAgent`
contains agent behavior, `ToolExecutor` is the sole tool-handler invocation
choke point, and `SafetyGate` is the authorization authority for
side-effecting tools (ADR-0008 and ADR-0004).

The backend must remain independently testable without a desktop, while the
product is Windows-first and needs genuine window inspection, native UI
inspection, and mouse/keyboard synthesis. Phase 5 therefore needs concrete
OS providers behind small structural protocols rather than embedding OS
library calls in agent or tool code.

## Decision

### 1. Python owns desktop intelligence and automation

Per ADR-0001, Python owns agent orchestration, automation/tool execution,
and planning. Electron remains responsible for the application shell and
interactive permission UI. Desktop automation therefore executes through
backend tools and is authorized by `SafetyGate`; it does not create a second
renderer-side automation path.

### 2. Three provider protocols

Phase 5 introduces three small structural interfaces:

- `WindowManagerProtocol` — enumerate, inspect, focus, move, and resize top-level windows.
- `UIInspectorProtocol` — inspect native Windows UI Automation trees read-only.
- `InputControllerProtocol` — synthesize mouse and keyboard input.

Concrete implementations are optional and platform-aware:

- `pygetwindow` for top-level window state.
- `pywinauto` (`uia` backend) for native UI Automation inspection.
- `pyautogui` for mouse/keyboard synthesis.

Missing dependencies or unsupported platforms produce explicit unavailability
rather than fake success.

### 3. Desktop Agent vs Automation Agent

The Desktop Agent graduates to a bespoke `DesktopAgent` because it now has
real behavior: reasoning-only steps receive the currently active window as
verified context. It still delegates tools through `ToolExecutor`.

The Automation Agent remains the generic `DomainAgent` implementation for
now. Its new capability is expressed through its tool allowlist. A bespoke
subclass is deferred until automation needs behavior that cannot be expressed
as shared tool delegation.

### 4. Read-only vs mutating tools

Read-only desktop inspection tools are owned by `agent.desktop` and do not
require a permission scope:

- `desktop.list_windows`
- `desktop.active_window`
- `desktop.inspect_ui`

Mutating desktop tools are owned by `agent.automation` and require the
existing `automation.input` scope:

- `automation.focus_window`
- `automation.move_window`
- `automation.resize_window`
- `automation.click`
- `automation.type_text`
- `automation.press_key`
- `automation.hotkey`
- `automation.scroll`

No new permission scope is introduced because `automation.input` already
exists in both the TypeScript contract and Python `PermissionScope` mirror.
Phase 4's `PermissionBroker` therefore provides the interactive `PROMPT`
path without a new transport or dialog mechanism.

### 5. Tool ownership is enforced at the choke point

`ToolSpec.owner_agent` existed before Phase 5 but was metadata only. Phase 5
makes `ToolExecutor` enforce it immediately before the permission check and
handler invocation. `DomainAgent.allowed_tools` remains the capability
allowlist; `owner_agent` becomes centralized defense-in-depth.

### 6. No new event family

Existing `agent.step` and `agent.observe` events already provide task
progress and tool-result observability. Desktop actions therefore do not
introduce a parallel `desktop.*` event family in this slice.

### 7. Optional automation dependencies

The backend keeps its core dependency set unchanged. Windows automation
libraries are provided through the optional `[automation]` extra. This
preserves standalone backend tests and non-Windows development environments.

## Security invariants

1. No desktop mutation occurs outside a `ToolSpec.handler` invocation.
2. No automation handler runs before `SafetyGate.check()` grants
   `PermissionScope.AUTOMATION_INPUT`.
3. The Automation Agent cannot invoke Desktop-owned read-only tools and the
   Desktop Agent cannot invoke Automation-owned mutating tools.
4. Tool handlers never decide their own authorization.
5. Unsupported platforms and missing dependencies fail closed.
6. The Orchestrator remains the only user-facing component.

## Alternatives rejected

- **Electron-side automation API:** rejected because it would create a
  second automation execution path outside the backend's ToolExecutor and
  SafetyGate architecture.
- **One monolithic DesktopAutomationService:** rejected because it would mix
  window state, UI inspection, and input synthesis, making testing and future
  platform providers harder.
- **Copying AJ's UIAutomator wholesale:** rejected. The reference project is
  useful for identifying practical libraries, but its element discovery is a
  stub and its input calls are not integrated with JARVIS OS's SafetyGate.
- **New permission scopes for every mouse/keyboard action:** rejected;
  `automation.input` already expresses the security boundary at the right
  granularity for Phase 5.
- **New desktop events:** rejected until a concrete consumer needs telemetry
  beyond existing agent lifecycle events.

## Consequences

- CI can test the entire tool and agent layer with fakes and without Windows.
- Real Windows integration tests can be added under a dedicated
  `live_desktop` marker.
- Phase 5 packaging can install the `[automation]` dependencies into the
  bundled backend environment without changing the agent architecture.
- Future Vision work can consume screen/UI observations without owning input
  synthesis, preserving a clean separation between perception and action.
