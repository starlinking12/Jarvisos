"""File integrity monitor — cross-platform (pure `hashlib` + filesystem
access, no native dependency). Hashes each watched file, compares against
the stored baseline (`SecurityRepository`'s `file_integrity_baseline`
table), and reports a finding when a hash changes — the baseline is then
updated to the new hash, so the *next* scan compares against the latest
known-good state rather than re-flagging the same change forever.

First run for any given path has no baseline to compare against; it
establishes one silently (no finding) rather than flagging every
watched file as "changed" on first launch.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

import structlog

from .types import FindingSeverity, SecurityCategory, SecurityFinding

logger = structlog.get_logger("jarvis_backend.security.file_integrity_monitor")


class BaselineStoreProtocol(Protocol):
    async def get_file_baseline(self, path: str) -> str | None: ...
    async def set_file_baseline(self, path: str, file_hash: str) -> None: ...


class FileIntegrityMonitor:
    name = "file_integrity"

    def __init__(
        self, watched_paths: tuple[Path, ...], baseline_store: BaselineStoreProtocol
    ) -> None:
        self._watched_paths = watched_paths
        self._baseline_store = baseline_store

    async def scan(self) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        for path in self._watched_paths:
            if not path.is_file():
                continue

            current_hash = self._hash_file(path)
            baseline_hash = await self._baseline_store.get_file_baseline(str(path))

            if baseline_hash is None:
                await self._baseline_store.set_file_baseline(str(path), current_hash)
                continue

            if current_hash != baseline_hash:
                findings.append(
                    SecurityFinding(
                        category=SecurityCategory.FILE_INTEGRITY,
                        severity=FindingSeverity.WARNING,
                        message=f"Watched file changed: {path}",
                    )
                )
                await self._baseline_store.set_file_baseline(str(path), current_hash)

        return findings

    @staticmethod
    def _hash_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
