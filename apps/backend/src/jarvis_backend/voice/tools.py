"""Voice tools — the Voice Engine's integration point with the agent
framework's `ToolRegistry` (ADR-0008), per the Phase 3 mandate: "Every
component must integrate with the existing... ToolRegistry."

`voice.speak` lets a domain agent make the assistant say something
proactively — e.g. the Automation agent (Phase 5) announcing a completed
background task — without that becoming a full conversational turn
through `VoiceEngine`'s wake→listen→respond cycle. Speaking output alone
carries no privacy/security risk comparable to activating the microphone
(which requires the `audio.microphone` `SafetyGate` scope — see
ADR-0011), so this tool is registered with no `permission_scope`, the
same posture as the Phase 2 `system.*` tools.
"""

from __future__ import annotations

from jarvis_backend.agents.tool_registry import ToolRegistry, ToolSpec

from .voice_engine import VoiceEngine


def register_voice_tools(registry: ToolRegistry, voice_engine: VoiceEngine) -> None:
    async def _speak(args: dict[str, object]) -> str:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return "voice.speak requires a non-empty 'text' argument."

        spoken = await voice_engine.speak_now(text)
        if not spoken:
            return (
                "Could not speak: the voice engine is currently mid-conversation "
                f"(state={voice_engine.state.value}). Try again once it returns to "
                "wake-word listening."
            )
        return "Spoken successfully."

    registry.register(
        ToolSpec(
            name="voice.speak",
            description=(
                "Speaks the given text aloud via the Voice Engine's text-to-speech "
                "pipeline, outside the normal conversational turn. Use for proactive "
                "announcements, not for responding to a user's spoken question (that "
                "happens automatically via the Orchestrator)."
            ),
            handler=_speak,
        )
    )
