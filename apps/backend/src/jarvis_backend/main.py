"""JARVIS backend entrypoint and composition root."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jarvis_backend.agents.automation_agent import AutomationAgent
from jarvis_backend.agents.desktop_agent import DesktopAgent
from jarvis_backend.agents.domain_agent import DomainAgent, build_default_agent_specs
from jarvis_backend.agents.orchestrator import Orchestrator
from jarvis_backend.agents.permission_broker import PermissionBroker
from jarvis_backend.agents.planner import SimplePlanner
from jarvis_backend.agents.safety_gate import (
    PermissionDecisionKind,
    PermissionScope,
    SafetyGate,
    SafetyPolicy,
)
from jarvis_backend.agents.task_ledger import TaskLedger
from jarvis_backend.agents.tool_executor import ToolExecutor
from jarvis_backend.agents.tool_registry import ToolRegistry
from jarvis_backend.agents.tools.automation_tools import register_automation_tools
from jarvis_backend.agents.tools.desktop_tools import register_desktop_tools
from jarvis_backend.agents.tools.system_tools import register_system_tools
from jarvis_backend.ai import (
    MockProvider,
    ModelProvider,
    ModelRouter,
    OllamaProvider,
    WarmModelManager,
)
from jarvis_backend.api import api_router
from jarvis_backend.config import ProviderConfig, Settings, get_settings
from jarvis_backend.desktop import (
    AutomationDependencyUnavailable,
    DesktopDependencyUnavailable,
    PyAutoGUIInputController,
    PyGetWindowManager,
    WindowManager,
)
from jarvis_backend.event_bus import event_bus
from jarvis_backend.memory import (
    NullLongTermMemory,
    RetrievalPipeline,
    SqliteLongTermMemory,
    WorkingMemory,
)
from jarvis_backend.persistence import DEFAULT_DB_PATH, Database
from jarvis_backend.persistence.repositories import (
    AuditRepository,
    MemoryRepository,
    SecurityRepository,
    SettingsRepository,
    TaskRepository,
)
from jarvis_backend.security import (
    FileIntegrityMonitor,
    NetworkMonitor,
    ProcessMonitor,
    RegistryMonitor,
    ScheduledTaskMonitor,
    SecurityCenter,
    SecuritySettings,
    StartupMonitor,
    get_security_settings,
)
from jarvis_backend.voice import (
    VoiceEngine,
    VoiceSettings,
    get_voice_settings,
    register_voice_tools,
)
from jarvis_backend.voice.audio import AudioStreamingPipeline, MicrophoneManager, SpeakerManager
from jarvis_backend.voice.barge_in import BargeInController, RawSpeechDetector
from jarvis_backend.voice.stt.whisper_cpp_provider import WhisperCppProvider
from jarvis_backend.voice.tts.piper_provider import PiperProvider
from jarvis_backend.voice.types import VoiceProfile
from jarvis_backend.voice.vad.webrtc_vad_provider import WebRtcVadProvider
from jarvis_backend.voice.wake_word.openwakeword_provider import OpenWakeWordProvider
from jarvis_contracts import EventSource

logger = structlog.get_logger("jarvis_backend")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


def build_provider(config: ProviderConfig) -> ModelProvider:
    if config.kind == "ollama":
        if not config.host:
            raise ValueError(f"Provider '{config.name}' of kind 'ollama' requires a host")
        return OllamaProvider(config.host, request_timeout_s=config.request_timeout_s)
    if config.kind == "mock":
        return MockProvider()
    raise ValueError(f"Unknown provider kind '{config.kind}' for provider '{config.name}'")


@dataclass(slots=True)
class OrchestratorBundle:
    orchestrator: Orchestrator
    providers: dict[str, ModelProvider]
    tool_registry: ToolRegistry
    safety_gate: SafetyGate
    permission_broker: PermissionBroker


def _build_desktop_adapters(
    settings: Settings,
) -> tuple[WindowManager | None, object | None]:
    """Construct optional native desktop adapters without breaking the backend.

    Desktop observation is useful whenever the OS adapter is available. Input
    automation is separately controlled by ``automation_enabled`` so merely
    installing pyautogui never activates high-impact input capabilities.
    """
    try:
        window_manager: WindowManager | None = PyGetWindowManager()
    except DesktopDependencyUnavailable as error:
        logger.warning("desktop_window_manager_unavailable", error=str(error))
        return None, None

    input_controller = None
    if settings.automation_enabled:
        try:
            input_controller = PyAutoGUIInputController()
        except AutomationDependencyUnavailable as error:
            logger.warning("desktop_input_controller_unavailable", error=str(error))

    return window_manager, input_controller


def build_orchestrator(settings: Settings, database: Database | None = None) -> OrchestratorBundle:
    providers = {config.name: build_provider(config) for config in settings.providers()}

    model_router = ModelRouter(
        providers=providers,
        routing=settings.routing(),
        retry_policy=settings.retry_policy(),
        resource_limits=settings.resource_limits(),
        event_bus=event_bus,
        warm_pool=WarmModelManager(),
    )

    tool_registry = ToolRegistry()
    agent_specs = build_default_agent_specs()
    register_system_tools(
        tool_registry, agent_names=[spec.identity.value for spec in agent_specs.values()]
    )

    window_manager, input_controller = _build_desktop_adapters(settings)
    if window_manager is not None:
        register_desktop_tools(tool_registry, window_manager)
        logger.info("desktop_observation_tools_registered")

    if settings.automation_enabled and window_manager is not None and input_controller is not None:
        register_automation_tools(
            tool_registry,
            window_manager=window_manager,
            input_controller=input_controller,
        )
        logger.info("desktop_automation_tools_registered")
    elif settings.automation_enabled:
        logger.warning("desktop_automation_not_available")

    permission_broker = PermissionBroker(event_bus)
    audit_repository = AuditRepository(database) if database is not None else None
    permission_policy = SafetyPolicy.production_default()
    if settings.automation_enabled:
        # Automation is opt-in and remains interactive by default. The user
        # must approve each high-impact automation scope through the existing
        # Phase 4 permission broker; we never silently change automation to ALLOW.
        permission_policy.overrides[PermissionScope.AUTOMATION_INPUT] = PermissionDecisionKind.PROMPT
    safety_gate = SafetyGate(
        permission_policy,
        broker=permission_broker,
        audit_repository=audit_repository,
    )

    task_repository = TaskRepository(database) if database is not None else None
    task_ledger = TaskLedger(repository=task_repository)

    tool_executor = ToolExecutor(
        registry=tool_registry,
        safety_gate=safety_gate,
        task_ledger=task_ledger,
        event_bus=event_bus,
    )

    agents: dict[EventSource, DomainAgent] = {}
    for identity, spec in agent_specs.items():
        if identity == EventSource.AGENT_DESKTOP and window_manager is not None:
            agents[identity] = DesktopAgent(
                spec,
                model_router=model_router,
                tool_executor=tool_executor,
                window_manager=window_manager,
            )
        elif identity == EventSource.AGENT_AUTOMATION:
            agents[identity] = AutomationAgent(
                spec,
                model_router=model_router,
                tool_executor=tool_executor,
            )
        else:
            agents[identity] = DomainAgent(
                spec,
                model_router=model_router,
                tool_executor=tool_executor,
            )

    working_memory = WorkingMemory()
    if database is not None:
        memory_repository = MemoryRepository(database)
        long_term_memory = SqliteLongTermMemory(memory_repository, model_router)
    else:
        long_term_memory = NullLongTermMemory()

    retrieval = RetrievalPipeline(
        working_memory=working_memory,
        long_term_memory=long_term_memory,
        model_router=model_router,
    )

    planner = SimplePlanner(model_router, tool_registry)
    orchestrator = Orchestrator(
        model_router=model_router,
        planner=planner,
        task_ledger=task_ledger,
        memory=retrieval,
        event_bus=event_bus,
        agents=agents,
    )

    return OrchestratorBundle(
        orchestrator=orchestrator,
        providers=providers,
        tool_registry=tool_registry,
        safety_gate=safety_gate,
        permission_broker=permission_broker,
    )


def build_voice_engine(
    voice_settings: VoiceSettings, bundle: OrchestratorBundle
) -> VoiceEngine | None:
    if not voice_settings.enabled:
        logger.info("voice_engine_disabled_by_config")
        return None

    try:
        audio_config = voice_settings.audio_config()
        microphone = MicrophoneManager(
            audio_config, device_index=voice_settings.devices.input_device_index
        )
        speaker = SpeakerManager(
            audio_config, device_index=voice_settings.devices.output_device_index
        )
        vad = WebRtcVadProvider(
            sample_rate=audio_config.sample_rate,
            frame_duration_ms=audio_config.frame_duration_ms,
            aggressiveness=voice_settings.vad.aggressiveness,
            hangover_frames=voice_settings.vad.hangover_frames,
        )
        pipeline = AudioStreamingPipeline(microphone, vad)
        wake_word = OpenWakeWordProvider(voice_settings.wake_word_config())
        stt = WhisperCppProvider(
            binary_path=voice_settings.whisper.binary_path,
            model_path=voice_settings.whisper.model_path,
            language=voice_settings.whisper.language,
        )
        tts = PiperProvider(
            voice_settings.piper_voice_mappings(), binary_path=voice_settings.piper.binary_path
        )
        default_voice = VoiceProfile(
            voice_id=voice_settings.piper.default_voice_id,
            display_name=voice_settings.piper.default_voice_id,
            language_code="en-US",
        )
        barge_in_controller = BargeInController(speaker, RawSpeechDetector(vad.raw_engine))

        voice_engine = VoiceEngine(
            audio_config=audio_config,
            microphone=microphone,
            speaker=speaker,
            pipeline=pipeline,
            wake_word=wake_word,
            stt=stt,
            tts=tts,
            default_voice=default_voice,
            orchestrator=bundle.orchestrator,
            safety_gate=bundle.safety_gate,
            event_bus=event_bus,
            barge_in_controller=barge_in_controller,
            barge_in_enabled=voice_settings.barge_in_enabled,
        )
        register_voice_tools(bundle.tool_registry, voice_engine)
        logger.info("voice_engine_constructed")
        return voice_engine
    except Exception as error:  # noqa: BLE001
        logger.warning("voice_engine_construction_failed", error=str(error))
        return None


def build_security_center(
    security_settings: SecuritySettings, database: Database
) -> SecurityCenter | None:
    if not security_settings.enabled:
        logger.info("security_center_disabled_by_config")
        return None

    security_repository = SecurityRepository(database)
    monitors = []
    try:
        monitors.append(ProcessMonitor(denylist_names=frozenset(security_settings.process_denylist)))
        monitors.append(
            NetworkMonitor(
                allowed_listen_ports=frozenset(security_settings.network_allowed_listen_ports)
            )
        )
    except Exception as error:  # noqa: BLE001
        logger.warning("psutil_backed_monitors_unavailable", error=str(error))

    monitors.append(StartupMonitor(known_entries=frozenset(security_settings.startup_known_entries)))
    monitors.append(RegistryMonitor())
    monitors.append(
        ScheduledTaskMonitor(
            known_task_names=frozenset(security_settings.scheduled_task_known_names)
        )
    )
    if security_settings.watched_file_paths:
        monitors.append(
            FileIntegrityMonitor(
                watched_paths=tuple(Path(p) for p in security_settings.watched_file_paths),
                baseline_store=security_repository,
            )
        )

    return SecurityCenter(
        monitors,
        event_bus=event_bus,
        repository=security_repository,
        scan_interval_s=security_settings.scan_interval_s,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    database = Database(Path(settings.db_path) if settings.db_path else DEFAULT_DB_PATH)
    await database.connect()
    app.state.database = database
    app.state.settings_repository = SettingsRepository(database)

    bundle = build_orchestrator(settings, database)
    app.state.orchestrator = bundle.orchestrator
    app.state.providers = bundle.providers
    app.state.permission_broker = bundle.permission_broker

    for name, provider in bundle.providers.items():
        health = await provider.health_check()
        if health.healthy:
            logger.info("provider_healthy", provider=name, models=health.available_models)
        else:
            logger.warning("provider_unhealthy", provider=name, detail=health.detail)

    voice_settings = get_voice_settings(settings.voice_settings_json)
    voice_engine = build_voice_engine(voice_settings, bundle)
    app.state.voice_engine = voice_engine
    if voice_engine is not None:
        await voice_engine.start()

    security_settings = get_security_settings(settings.security_settings_json)
    security_center = build_security_center(security_settings, database)
    app.state.security_center = security_center
    if security_center is not None:
        await security_center.start()

    yield

    if security_center is not None:
        await security_center.stop()
    if voice_engine is not None:
        await voice_engine.stop()

    for provider in bundle.providers.values():
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            await aclose()
    await database.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="JARVIS Backend",
        version="0.0.0",
        description="Local-first AI backend for JARVIS OS.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the JARVIS backend server.")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()

    settings = get_settings()
    port = args.port or settings.backend_port
    configure_logging(settings.log_level)
    uvicorn.run(
        "jarvis_backend.main:app",
        host="127.0.0.1",
        port=port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
