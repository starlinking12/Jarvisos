# ADR-0014 — Desktop Intelligence and Safety-Gated Automation

**Status:** Accepted and implemented for Phase 5

## Context

JARVIS OS needs real desktop awareness and desktop input automation. The
existing backend already provides the required governance boundary:
`DomainAgent -> ToolExecutor -> SafetyGate -> ToolSpec.handler`.

Phase 5 must not create a second execution path for native input.

## Decision

1. Desktop integration is represented by platform-neutral `WindowManager`
   and `InputController` protocols in `jarvis_backend.desktop.types`.
2. Native adapters (`PyGetWindowManager`, `PyAutoGUIInputController`) live
   behind those protocols and are optional runtime dependencies.
3. Read-only desktop observation tools use the existing `ToolRegistry` and
   carry no permission scope.
4. Mutating window/input tools use the existing `automation.input`
   `PermissionScope` and therefore cannot execute without `ToolExecutor` and
   `SafetyGate` approval.
5. `JARVIS_AUTOMATION_ENABLED` is false by default. Enabling it configures
   `automation.input` as `PROMPT`, not `ALLOW`, so the existing Phase 4
   permission broker remains the final approval mechanism.
6. `DesktopAgent` may add verified desktop state to reasoning prompts, but
   it never invokes native adapters as a bypass around the tool executor.
7. `AutomationAgent` remains a thin specialization point; automation policy
   belongs to `SafetyGate`, not the agent class.
8. Native desktop dependencies are exposed through the backend's optional
   `automation` package extra rather than a separate ad-hoc requirements file.

## Consequences

### Positive

- One tool execution choke point remains intact.
- Native automation is opt-in and interactive by default.
- OS-specific implementations can be replaced without changing agents or tools.
- Unit tests can use fakes without native desktop dependencies.
- Production/development installs have one canonical dependency declaration.

### Deferred

- Image-based UI element recognition belongs to the Vision phase.
- OCR and semantic UI targeting are not inferred from window metadata.
- Complex multi-step transactional automation, rollback, and action planning
  are future extensions.
