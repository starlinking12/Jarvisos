"""Security Center shared types (see ADR-0013).

Every monitor (`ProcessMonitor`, `StartupMonitor`, `RegistryMonitor`,
`ScheduledTaskMonitor`, `FileIntegrityMonitor`, `NetworkMonitor`)
satisfies `SecurityMonitor` structurally — the same `Protocol`-based
provider pattern as every other swappable subsystem in this project
(`ModelProvider`, `VadProvider`, etc.) — and returns `SecurityFinding`s,
which `ThreatScorer` combines into `security.alert` events.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class SecurityCategory(str, Enum):
    """Mirrors `SecurityAlertCategory` in `jarvis_contracts` exactly —
    kept as a distinct type for the same reason `PermissionScope` is
    duplicated rather than imported (see `safety_gate.py`'s module
    docstring): this enum is a monitor-internal classification that
    happens to share vocabulary with the wire contract, not a dependency
    on it."""

    PROCESS = "process"
    STARTUP = "startup"
    REGISTRY = "registry"
    SCHEDULED_TASK = "scheduled_task"
    FILE_INTEGRITY = "file_integrity"
    NETWORK = "network"


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(slots=True, frozen=True)
class SecurityFinding:
    category: SecurityCategory
    severity: FindingSeverity
    message: str
    requires_approval: bool = False


class SecurityMonitor(Protocol):
    """Every monitor implements exactly one method: run one scan pass and
    report what it found. `SecurityCenter` owns scheduling (how often each
    monitor runs) and aggregation — monitors are pure "observe and
    report," never "decide and act," keeping them trivially testable and
    consistent with `SafetyGate` being the sole authorization authority
    (a monitor that found something suspicious never itself blocks
    anything)."""

    async def scan(self) -> list[SecurityFinding]: ...

    @property
    def name(self) -> str: ...
