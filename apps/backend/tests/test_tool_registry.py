from __future__ import annotations

import pytest

from jarvis_backend.agents.tool_registry import ToolRegistry, ToolSpec


async def _dummy_handler(args: dict[str, object]) -> str:
    return "ok"


def test_register_and_get_tool() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(name="test.tool", description="A test tool.", handler=_dummy_handler)

    registry.register(spec)

    assert registry.get("test.tool") is spec
    assert registry.get("nonexistent") is None


def test_register_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="dup", description="first", handler=_dummy_handler))

    with pytest.raises(ValueError):
        registry.register(ToolSpec(name="dup", description="second", handler=_dummy_handler))


def test_list_returns_all_registered_tools() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="a", description="a", handler=_dummy_handler))
    registry.register(ToolSpec(name="b", description="b", handler=_dummy_handler))

    names = {spec.name for spec in registry.list()}
    assert names == {"a", "b"}


def test_describe_for_planner_renders_all_tools() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="a.tool", description="does A", handler=_dummy_handler))

    description = registry.describe_for_planner()
    assert "a.tool" in description
    assert "does A" in description


def test_describe_for_planner_handles_empty_registry() -> None:
    registry = ToolRegistry()
    assert "no tools" in registry.describe_for_planner().lower()
