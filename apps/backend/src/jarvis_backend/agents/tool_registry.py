"""ToolRegistry — the Tool Executors tier's catalogue (see ADR-0008).

A `ToolSpec` is a self-contained, callable capability: a name, a
description (used by `Planner` when asking a model to choose tools), an
optional `PermissionScope` it must be granted before running (checked by
`SafetyGate`, not by the tool itself — a tool never decides its own
authorization), and the async handler that performs the work.

Registration is intentionally decoupled from execution (`ToolExecutor`,
in `tool_executor.py`) — the registry only knows what tools exist, never
how or whether one is currently allowed to run. This mirrors
`WidgetRegistry` in the renderer (`apps/renderer/src/layout/WidgetRegistry.ts`):
the same "plugin-ready registry, separate from the execution/authorization
layer" shape, applied on the backend.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from jarvis_contracts import EventSource

ToolHandler = Callable[[dict[str, object]], Awaitable[str]]


@dataclass(slots=True, frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    permission_scope: str | None = None  # matches PermissionScope values, see safety_gate.py
    owner_agent: EventSource | None = None  # None = available to any domain agent


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' is already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def describe_for_planner(self) -> str:
        """Renders the tool catalogue as a compact text block suitable for
        inclusion in a planning prompt — see `SimplePlanner`."""
        lines = [f"- {spec.name}: {spec.description}" for spec in self._tools.values()]
        return "\n".join(lines) if lines else "(no tools registered)"
