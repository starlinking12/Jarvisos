"""System tools — the first real entries in the ToolRegistry.

Deliberately scoped to zero-risk, genuinely useful operations for Phase 2:
no permission scope needed, no filesystem/network/process access. This is
what "no placeholders" looks like for tools whose higher-risk siblings
(filesystem, automation, shell) are correctly deferred to the phases that
build their SafetyGate-integrated approval flow (see `safety_gate.py`'s
module docstring) — these two are fully real and fully wired end-to-end
today, not stand-ins for something bigger.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..tool_registry import ToolRegistry, ToolSpec


async def _get_current_time(_args: dict[str, object]) -> str:
    return datetime.now(UTC).isoformat()


def register_system_tools(registry: ToolRegistry, *, agent_names: list[str]) -> None:
    registry.register(
        ToolSpec(
            name="system.get_current_time",
            description="Returns the current UTC time in ISO 8601 format.",
            handler=_get_current_time,
        )
    )

    async def _list_agents(_args: dict[str, object]) -> str:
        return ", ".join(agent_names)

    registry.register(
        ToolSpec(
            name="system.list_agents",
            description="Returns the names of all registered domain agents.",
            handler=_list_agents,
        )
    )
