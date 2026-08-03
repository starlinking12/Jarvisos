/**
 * Backend Event Contracts — the ONLY allowed shape for Electron-main <->
 * Python-backend communication over the WebSocket event stream.
 *
 * This file MUST stay in lockstep with
 * `packages/contracts/python/jarvis_contracts/events.py`. Phase 1 adds an
 * automated drift check to CI; until then, any change here requires a
 * matching change there in the same commit.
 *
 * Envelope: every message on the wire is a `JarvisEvent`. `type` acts as the
 * discriminant; `payload` shape is determined by the corresponding schema
 * below.
 */

import { z } from "zod";

export const EventSource = z.enum([
  "shell", // Electron main process
  "backend", // Python FastAPI process
  "orchestrator",
  "agent.desktop",
  "agent.vision",
  "agent.research",
  "agent.security",
  "agent.memory",
  "agent.earth",
  "agent.automation",
  "agent.developer",
]);
export type EventSource = z.infer<typeof EventSource>;

// ---------------------------------------------------------------------------
// backend.health — periodic heartbeat from the Python process
// ---------------------------------------------------------------------------
export const BackendHealthPayload = z.object({
  status: z.enum(["ok", "degraded"]),
  uptimeMs: z.number().int().nonnegative(),
  loadedModels: z.array(z.string()).default([]),
});
export type BackendHealthPayload = z.infer<typeof BackendHealthPayload>;

// ---------------------------------------------------------------------------
// orchestrator.message — a user-visible message from the Orchestrator
// (the only agent permitted to address the user directly, per system rules)
// ---------------------------------------------------------------------------
export const MessageRole = z.enum(["assistant", "system"]);
export type MessageRole = z.infer<typeof MessageRole>;

export const OrchestratorMessagePayload = z.object({
  conversationId: z.string().uuid(),
  role: MessageRole,
  contentDelta: z.string(), // streaming chunk; empty string + done=true = end
  done: z.boolean().default(false),
});
export type OrchestratorMessagePayload = z.infer<
  typeof OrchestratorMessagePayload
>;

// ---------------------------------------------------------------------------
// agent.taskUpdate — internal agent progress, surfaced to UI as HUD state,
// never shown as raw chat
// ---------------------------------------------------------------------------
export const TaskStatus = z.enum([
  "queued",
  "running",
  "waiting_for_permission",
  "completed",
  "failed",
]);
export type TaskStatus = z.infer<typeof TaskStatus>;

export const AgentTaskUpdatePayload = z.object({
  taskId: z.string().uuid(),
  agent: EventSource,
  status: TaskStatus,
  summary: z.string(),
  progress: z.number().min(0).max(1).nullable(),
});
export type AgentTaskUpdatePayload = z.infer<typeof AgentTaskUpdatePayload>;

// ---------------------------------------------------------------------------
// security.alert — reserved now, populated by the Security Agent in Phase 3
// ---------------------------------------------------------------------------
export const SecurityAlertSeverity = z.enum([
  "info",
  "warning",
  "critical",
]);
export type SecurityAlertSeverity = z.infer<typeof SecurityAlertSeverity>;

export const SecurityAlertPayload = z.object({
  severity: SecurityAlertSeverity,
  category: z.enum([
    "process",
    "startup",
    "registry",
    "scheduled_task",
    "file_integrity",
    "network",
  ]),
  message: z.string(),
  requiresApproval: z.boolean().default(false),
});
export type SecurityAlertPayload = z.infer<typeof SecurityAlertPayload>;

// ---------------------------------------------------------------------------
// ai.request / ai.token / ai.response — ModelRouter call lifecycle (Phase 2)
// ---------------------------------------------------------------------------
export const AiTaskType = z.enum([
  "chat",
  "reasoning",
  "toolcall",
  "summarize",
  "embed",
]);
export type AiTaskType = z.infer<typeof AiTaskType>;

export const AiRequestPayload = z.object({
  requestId: z.string().uuid(),
  taskId: z.string().uuid().nullable(), // null for requests not tied to an agent task (e.g. ad-hoc summarize)
  taskType: AiTaskType,
  provider: z.string(),
  model: z.string(),
});
export type AiRequestPayload = z.infer<typeof AiRequestPayload>;

export const AiTokenPayload = z.object({
  requestId: z.string().uuid(),
  token: z.string(),
  index: z.number().int().nonnegative(),
});
export type AiTokenPayload = z.infer<typeof AiTokenPayload>;

export const AiFinishReason = z.enum(["stop", "length", "tool_call", "error"]);
export type AiFinishReason = z.infer<typeof AiFinishReason>;

export const AiResponsePayload = z.object({
  requestId: z.string().uuid(),
  taskId: z.string().uuid().nullable(),
  finishReason: AiFinishReason,
  totalTokens: z.number().int().nonnegative().nullable(),
  latencyMs: z.number().nonnegative(),
});
export type AiResponsePayload = z.infer<typeof AiResponsePayload>;

// ---------------------------------------------------------------------------
// agent.task.created / agent.plan / agent.step / agent.observe /
// agent.complete / agent.error — Orchestrator/Agent lifecycle (Phase 2)
//
// These are fine-grained audit/debug telemetry, distinct from the coarser
// `agent.taskUpdate` event (Phase 0) that HUD widgets display as a single
// progress summary — see ADR-0008 for the rationale for keeping both.
// ---------------------------------------------------------------------------
export const AgentTaskCreatedPayload = z.object({
  taskId: z.string().uuid(),
  goal: z.string(),
  requestedBy: EventSource,
});
export type AgentTaskCreatedPayload = z.infer<typeof AgentTaskCreatedPayload>;

export const PlanStepSchema = z.object({
  stepId: z.string().uuid(),
  description: z.string(),
  agent: EventSource,
  tool: z.string().nullable(),
});
export type PlanStepSchema = z.infer<typeof PlanStepSchema>;

export const AgentPlanPayload = z.object({
  taskId: z.string().uuid(),
  steps: z.array(PlanStepSchema),
});
export type AgentPlanPayload = z.infer<typeof AgentPlanPayload>;

export const AgentStepPayload = z.object({
  taskId: z.string().uuid(),
  stepId: z.string().uuid(),
  agent: EventSource,
  status: TaskStatus,
  description: z.string(),
});
export type AgentStepPayload = z.infer<typeof AgentStepPayload>;

export const AgentObservePayload = z.object({
  taskId: z.string().uuid(),
  stepId: z.string().uuid(),
  observation: z.string(),
  success: z.boolean(),
});
export type AgentObservePayload = z.infer<typeof AgentObservePayload>;

export const AgentCompletePayload = z.object({
  taskId: z.string().uuid(),
  summary: z.string(),
  success: z.boolean(),
});
export type AgentCompletePayload = z.infer<typeof AgentCompletePayload>;

export const AgentErrorPayload = z.object({
  taskId: z.string().uuid(),
  stepId: z.string().uuid().nullable(),
  message: z.string(),
  recoverable: z.boolean(),
});
export type AgentErrorPayload = z.infer<typeof AgentErrorPayload>;

// ---------------------------------------------------------------------------
// voice.* — Voice Engine lifecycle (Phase 3, see ADR-0010/ADR-0011)
// ---------------------------------------------------------------------------
export const VoiceWakePayload = z.object({
  wakeWord: z.string(),
  confidence: z.number().min(0).max(1),
});
export type VoiceWakePayload = z.infer<typeof VoiceWakePayload>;

export const VoiceListeningPayload = z.object({
  listening: z.boolean(),
});
export type VoiceListeningPayload = z.infer<typeof VoiceListeningPayload>;

export const VoicePartialPayload = z.object({
  transcript: z.string(),
});
export type VoicePartialPayload = z.infer<typeof VoicePartialPayload>;

export const VoiceFinalPayload = z.object({
  transcript: z.string(),
  conversationId: z.string().uuid(),
  languageCode: z.string().nullable(),
  durationMs: z.number().nonnegative(),
});
export type VoiceFinalPayload = z.infer<typeof VoiceFinalPayload>;

export const VoiceThinkingPayload = z.object({
  conversationId: z.string().uuid(),
  taskId: z.string().uuid().nullable(),
});
export type VoiceThinkingPayload = z.infer<typeof VoiceThinkingPayload>;

export const VoiceSpeakingPayload = z.object({
  text: z.string(),
  voiceId: z.string(),
});
export type VoiceSpeakingPayload = z.infer<typeof VoiceSpeakingPayload>;

export const VoiceFinishedPayload = z.object({
  voiceId: z.string(),
});
export type VoiceFinishedPayload = z.infer<typeof VoiceFinishedPayload>;

export const VoiceInterruptedPayload = z.object({
  reason: z.enum(["barge_in", "manual_stop", "error"]),
  latencyMs: z.number().nonnegative().nullable(),
});
export type VoiceInterruptedPayload = z.infer<typeof VoiceInterruptedPayload>;

export const VoiceErrorPayload = z.object({
  message: z.string(),
  recoverable: z.boolean(),
});
export type VoiceErrorPayload = z.infer<typeof VoiceErrorPayload>;

// ---------------------------------------------------------------------------
// permission.request — backend-originated approval request (Phase 4, see
// ADR-0012). The shell's PermissionBridge listens for this, shows the
// existing PermissionGate dialog, and POSTs the decision back to the
// backend's /agent/permission-decision endpoint (not modeled as an event,
// since it's a direct request/response the shell initiates, not something
// other subscribers need to observe).
// ---------------------------------------------------------------------------
export const PermissionRequestScope = z.enum([
  "filesystem.write",
  "process.control",
  "network.egress",
  "automation.input",
  "shell.execute",
  "audio.microphone",
]);
export type PermissionRequestScope = z.infer<typeof PermissionRequestScope>;

export const PermissionRequestEventPayload = z.object({
  requestId: z.string().uuid(),
  scope: PermissionRequestScope,
  reason: z.string(),
  requestedBy: z.string(),
  timeoutMs: z.number().int().positive(),
});
export type PermissionRequestEventPayload = z.infer<typeof PermissionRequestEventPayload>;

// ---------------------------------------------------------------------------
// Envelope + discriminated registry
// ---------------------------------------------------------------------------
export const EventEnvelopeBase = z.object({
  id: z.string().uuid(),
  source: EventSource,
  timestamp: z.string().datetime(),
});

export const JarvisEvent = z.discriminatedUnion("type", [
  EventEnvelopeBase.extend({
    type: z.literal("backend.health"),
    payload: BackendHealthPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("orchestrator.message"),
    payload: OrchestratorMessagePayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.taskUpdate"),
    payload: AgentTaskUpdatePayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("security.alert"),
    payload: SecurityAlertPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("ai.request"),
    payload: AiRequestPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("ai.token"),
    payload: AiTokenPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("ai.response"),
    payload: AiResponsePayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.task.created"),
    payload: AgentTaskCreatedPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.plan"),
    payload: AgentPlanPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.step"),
    payload: AgentStepPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.observe"),
    payload: AgentObservePayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.complete"),
    payload: AgentCompletePayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("agent.error"),
    payload: AgentErrorPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.wake"),
    payload: VoiceWakePayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.listening"),
    payload: VoiceListeningPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.partial"),
    payload: VoicePartialPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.final"),
    payload: VoiceFinalPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.thinking"),
    payload: VoiceThinkingPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.speaking"),
    payload: VoiceSpeakingPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.finished"),
    payload: VoiceFinishedPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.interrupted"),
    payload: VoiceInterruptedPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("voice.error"),
    payload: VoiceErrorPayload,
  }),
  EventEnvelopeBase.extend({
    type: z.literal("permission.request"),
    payload: PermissionRequestEventPayload,
  }),
]);
export type JarvisEvent = z.infer<typeof JarvisEvent>;

export type JarvisEventType = JarvisEvent["type"];
