"""
Backend Event Contracts — Python mirror of
`packages/contracts/src/events.ts`.

This module MUST stay in lockstep with the TypeScript source of truth.
Any change here requires a matching change there in the same commit
(Phase 1 adds an automated drift check to CI).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field


class EventSource(str, Enum):
    SHELL = "shell"
    BACKEND = "backend"
    ORCHESTRATOR = "orchestrator"
    AGENT_DESKTOP = "agent.desktop"
    AGENT_VISION = "agent.vision"
    AGENT_RESEARCH = "agent.research"
    AGENT_SECURITY = "agent.security"
    AGENT_MEMORY = "agent.memory"
    AGENT_EARTH = "agent.earth"
    AGENT_AUTOMATION = "agent.automation"
    AGENT_DEVELOPER = "agent.developer"


# ---------------------------------------------------------------------------
# backend.health
# ---------------------------------------------------------------------------
class BackendHealthPayload(BaseModel):
    status: Literal["ok", "degraded"]
    uptime_ms: int = Field(ge=0, alias="uptimeMs")
    loaded_models: list[str] = Field(default_factory=list, alias="loadedModels")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# orchestrator.message
# ---------------------------------------------------------------------------
class MessageRole(str, Enum):
    ASSISTANT = "assistant"
    SYSTEM = "system"


class OrchestratorMessagePayload(BaseModel):
    conversation_id: UUID = Field(alias="conversationId")
    role: MessageRole
    content_delta: str = Field(alias="contentDelta")
    done: bool = False

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# agent.taskUpdate (coarse HUD-facing progress — see ADR-0008 for how this
# differs from the fine-grained agent.plan/step/observe events below)
# ---------------------------------------------------------------------------
class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTaskUpdatePayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    agent: EventSource
    status: TaskStatus
    summary: str
    progress: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# security.alert (reserved — populated by Security Agent in Phase 3)
# ---------------------------------------------------------------------------
class SecurityAlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SecurityAlertCategory(str, Enum):
    PROCESS = "process"
    STARTUP = "startup"
    REGISTRY = "registry"
    SCHEDULED_TASK = "scheduled_task"
    FILE_INTEGRITY = "file_integrity"
    NETWORK = "network"


class SecurityAlertPayload(BaseModel):
    severity: SecurityAlertSeverity
    category: SecurityAlertCategory
    message: str
    requires_approval: bool = Field(default=False, alias="requiresApproval")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# ai.request / ai.token / ai.response — ModelRouter call lifecycle (Phase 2)
# ---------------------------------------------------------------------------
class AiTaskType(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    TOOLCALL = "toolcall"
    SUMMARIZE = "summarize"
    EMBED = "embed"


class AiRequestPayload(BaseModel):
    request_id: UUID = Field(alias="requestId")
    task_id: UUID | None = Field(default=None, alias="taskId")
    task_type: AiTaskType = Field(alias="taskType")
    provider: str
    model: str

    model_config = {"populate_by_name": True}


class AiTokenPayload(BaseModel):
    request_id: UUID = Field(alias="requestId")
    token: str
    index: int = Field(ge=0)

    model_config = {"populate_by_name": True}


class AiFinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    ERROR = "error"


class AiResponsePayload(BaseModel):
    request_id: UUID = Field(alias="requestId")
    task_id: UUID | None = Field(default=None, alias="taskId")
    finish_reason: AiFinishReason = Field(alias="finishReason")
    total_tokens: int | None = Field(default=None, ge=0, alias="totalTokens")
    latency_ms: float = Field(ge=0, alias="latencyMs")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# agent.task.created / agent.plan / agent.step / agent.observe /
# agent.complete / agent.error — Orchestrator/Agent lifecycle (Phase 2)
# ---------------------------------------------------------------------------
class AgentTaskCreatedPayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    goal: str
    requested_by: EventSource = Field(alias="requestedBy")

    model_config = {"populate_by_name": True}


class PlanStepSchema(BaseModel):
    step_id: UUID = Field(alias="stepId")
    description: str
    agent: EventSource
    tool: str | None = None

    model_config = {"populate_by_name": True}


class AgentPlanPayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    steps: list[PlanStepSchema]

    model_config = {"populate_by_name": True}


class AgentStepPayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    step_id: UUID = Field(alias="stepId")
    agent: EventSource
    status: TaskStatus
    description: str

    model_config = {"populate_by_name": True}


class AgentObservePayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    step_id: UUID = Field(alias="stepId")
    observation: str
    success: bool

    model_config = {"populate_by_name": True}


class AgentCompletePayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    summary: str
    success: bool

    model_config = {"populate_by_name": True}


class AgentErrorPayload(BaseModel):
    task_id: UUID = Field(alias="taskId")
    step_id: UUID | None = Field(default=None, alias="stepId")
    message: str
    recoverable: bool

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# voice.* — Voice Engine lifecycle (Phase 3, see ADR-0010/ADR-0011)
# ---------------------------------------------------------------------------
class VoiceWakePayload(BaseModel):
    wake_word: str = Field(alias="wakeWord")
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class VoiceListeningPayload(BaseModel):
    listening: bool


class VoicePartialPayload(BaseModel):
    transcript: str


class VoiceFinalPayload(BaseModel):
    transcript: str
    conversation_id: UUID = Field(alias="conversationId")
    language_code: str | None = Field(default=None, alias="languageCode")
    duration_ms: float = Field(ge=0, alias="durationMs")

    model_config = {"populate_by_name": True}


class VoiceThinkingPayload(BaseModel):
    conversation_id: UUID = Field(alias="conversationId")
    task_id: UUID | None = Field(default=None, alias="taskId")

    model_config = {"populate_by_name": True}


class VoiceSpeakingPayload(BaseModel):
    text: str
    voice_id: str = Field(alias="voiceId")

    model_config = {"populate_by_name": True}


class VoiceFinishedPayload(BaseModel):
    voice_id: str = Field(alias="voiceId")

    model_config = {"populate_by_name": True}


class VoiceInterruptedReason(str, Enum):
    BARGE_IN = "barge_in"
    MANUAL_STOP = "manual_stop"
    ERROR = "error"


class VoiceInterruptedPayload(BaseModel):
    reason: VoiceInterruptedReason
    latency_ms: float | None = Field(default=None, ge=0, alias="latencyMs")

    model_config = {"populate_by_name": True}


class VoiceErrorPayload(BaseModel):
    message: str
    recoverable: bool


# ---------------------------------------------------------------------------
# permission.request — backend-originated approval request (Phase 4,
# ADR-0012). Mirrors packages/contracts/src/events.ts's PermissionRequestScope
# exactly (kept string-value-identical to agents/safety_gate.py's
# PermissionScope, per that module's own documented rationale for the
# duplication).
# ---------------------------------------------------------------------------
class PermissionRequestScope(str, Enum):
    FILESYSTEM_WRITE = "filesystem.write"
    PROCESS_CONTROL = "process.control"
    NETWORK_EGRESS = "network.egress"
    AUTOMATION_INPUT = "automation.input"
    SHELL_EXECUTE = "shell.execute"
    AUDIO_MICROPHONE = "audio.microphone"


class PermissionRequestEventPayload(BaseModel):
    request_id: UUID = Field(alias="requestId")
    scope: PermissionRequestScope
    reason: str
    requested_by: str = Field(alias="requestedBy")
    timeout_ms: int = Field(gt=0, alias="timeoutMs")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Envelope + discriminated union — mirrors the zod discriminatedUnion
# ---------------------------------------------------------------------------
class _EnvelopeBase(BaseModel):
    id: UUID
    source: EventSource
    timestamp: datetime

    model_config = {"populate_by_name": True}


class BackendHealthEvent(_EnvelopeBase):
    type: Literal["backend.health"] = "backend.health"
    payload: BackendHealthPayload


class OrchestratorMessageEvent(_EnvelopeBase):
    type: Literal["orchestrator.message"] = "orchestrator.message"
    payload: OrchestratorMessagePayload


class AgentTaskUpdateEvent(_EnvelopeBase):
    type: Literal["agent.taskUpdate"] = "agent.taskUpdate"
    payload: AgentTaskUpdatePayload


class SecurityAlertEvent(_EnvelopeBase):
    type: Literal["security.alert"] = "security.alert"
    payload: SecurityAlertPayload


class AiRequestEvent(_EnvelopeBase):
    type: Literal["ai.request"] = "ai.request"
    payload: AiRequestPayload


class AiTokenEvent(_EnvelopeBase):
    type: Literal["ai.token"] = "ai.token"
    payload: AiTokenPayload


class AiResponseEvent(_EnvelopeBase):
    type: Literal["ai.response"] = "ai.response"
    payload: AiResponsePayload


class AgentTaskCreatedEvent(_EnvelopeBase):
    type: Literal["agent.task.created"] = "agent.task.created"
    payload: AgentTaskCreatedPayload


class AgentPlanEvent(_EnvelopeBase):
    type: Literal["agent.plan"] = "agent.plan"
    payload: AgentPlanPayload


class AgentStepEvent(_EnvelopeBase):
    type: Literal["agent.step"] = "agent.step"
    payload: AgentStepPayload


class AgentObserveEvent(_EnvelopeBase):
    type: Literal["agent.observe"] = "agent.observe"
    payload: AgentObservePayload


class AgentCompleteEvent(_EnvelopeBase):
    type: Literal["agent.complete"] = "agent.complete"
    payload: AgentCompletePayload


class AgentErrorEvent(_EnvelopeBase):
    type: Literal["agent.error"] = "agent.error"
    payload: AgentErrorPayload


class VoiceWakeEvent(_EnvelopeBase):
    type: Literal["voice.wake"] = "voice.wake"
    payload: VoiceWakePayload


class VoiceListeningEvent(_EnvelopeBase):
    type: Literal["voice.listening"] = "voice.listening"
    payload: VoiceListeningPayload


class VoicePartialEvent(_EnvelopeBase):
    type: Literal["voice.partial"] = "voice.partial"
    payload: VoicePartialPayload


class VoiceFinalEvent(_EnvelopeBase):
    type: Literal["voice.final"] = "voice.final"
    payload: VoiceFinalPayload


class VoiceThinkingEvent(_EnvelopeBase):
    type: Literal["voice.thinking"] = "voice.thinking"
    payload: VoiceThinkingPayload


class VoiceSpeakingEvent(_EnvelopeBase):
    type: Literal["voice.speaking"] = "voice.speaking"
    payload: VoiceSpeakingPayload


class VoiceFinishedEvent(_EnvelopeBase):
    type: Literal["voice.finished"] = "voice.finished"
    payload: VoiceFinishedPayload


class VoiceInterruptedEvent(_EnvelopeBase):
    type: Literal["voice.interrupted"] = "voice.interrupted"
    payload: VoiceInterruptedPayload


class VoiceErrorEvent(_EnvelopeBase):
    type: Literal["voice.error"] = "voice.error"
    payload: VoiceErrorPayload


class PermissionRequestEvent(_EnvelopeBase):
    type: Literal["permission.request"] = "permission.request"
    payload: PermissionRequestEventPayload


JarvisEvent = Annotated[
    Union[
        BackendHealthEvent,
        OrchestratorMessageEvent,
        AgentTaskUpdateEvent,
        SecurityAlertEvent,
        AiRequestEvent,
        AiTokenEvent,
        AiResponseEvent,
        AgentTaskCreatedEvent,
        AgentPlanEvent,
        AgentStepEvent,
        AgentObserveEvent,
        AgentCompleteEvent,
        AgentErrorEvent,
        VoiceWakeEvent,
        VoiceListeningEvent,
        VoicePartialEvent,
        VoiceFinalEvent,
        VoiceThinkingEvent,
        VoiceSpeakingEvent,
        VoiceFinishedEvent,
        VoiceInterruptedEvent,
        VoiceErrorEvent,
        PermissionRequestEvent,
    ],
    Field(discriminator="type"),
]
