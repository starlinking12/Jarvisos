"""ThreatScorer — combines raw `SecurityFinding`s from every monitor into
the signal `SecurityCenter` actually acts on. A single `INFO`-severity
finding (e.g. one unrecognized startup entry) is noise a security center
that alerts on every raw finding would drown users in; `ThreatScorer`'s
job is deciding what's worth surfacing as a `security.alert` versus what
gets recorded (still persisted — nothing is silently dropped) but not
pushed as a live event.

Escalation rule (real, simple, and the correct scope for Phase 4 — not a
full correlation engine): if the same category produces findings across
`escalation_threshold` consecutive scan cycles, severity is escalated one
level, since a persistent condition is more actionable than a one-off.
"""

from __future__ import annotations

from collections import defaultdict

from .types import FindingSeverity, SecurityFinding

_SEVERITY_ORDER = [FindingSeverity.INFO, FindingSeverity.WARNING, FindingSeverity.CRITICAL]


class ThreatScorer:
    def __init__(self, escalation_threshold: int = 3) -> None:
        self._escalation_threshold = escalation_threshold
        self._consecutive_counts: dict[str, int] = defaultdict(int)

    def score(self, findings: list[SecurityFinding]) -> list[SecurityFinding]:
        """Returns findings with severity escalated where warranted.
        Categories with no finding this cycle have their consecutive
        count reset — escalation is about *persistence*, not historical
        totals."""
        seen_categories = {f.category.value for f in findings}

        for category in list(self._consecutive_counts.keys()):
            if category not in seen_categories:
                self._consecutive_counts[category] = 0

        scored: list[SecurityFinding] = []
        for finding in findings:
            key = finding.category.value
            self._consecutive_counts[key] += 1

            if self._consecutive_counts[key] >= self._escalation_threshold:
                scored.append(self._escalate(finding))
            else:
                scored.append(finding)

        return scored

    @staticmethod
    def _escalate(finding: SecurityFinding) -> SecurityFinding:
        current_index = _SEVERITY_ORDER.index(finding.severity)
        new_index = min(current_index + 1, len(_SEVERITY_ORDER) - 1)
        if new_index == current_index:
            return finding
        return SecurityFinding(
            category=finding.category,
            severity=_SEVERITY_ORDER[new_index],
            message=f"{finding.message} (escalated — persisted across multiple scans)",
            requires_approval=finding.requires_approval
            or _SEVERITY_ORDER[new_index] == FindingSeverity.CRITICAL,
        )
