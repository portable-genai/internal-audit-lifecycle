"""Local FindingFeedPort: an inspectable in-memory outbox for the issue-remediation-capa handover.

Stands in for issue-remediation-capa's intake surface offline: it records each emitted handover in
an outbox a test or the demo can read back, and returns a deterministic feed reference. A silent
no-op would let a producer ship the issue-remediation-capa boundary unwired, so this records a real,
inspectable entry.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.findings import IssueHandover


class LocalFindingFeedAdapter:
    """Record approved-finding handovers in an in-memory outbox (no issue-remediation-capa, no
    network).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.outbox: list[IssueHandover] = []

    def emit(self, handover: IssueHandover) -> str:
        if not handover.approval_ref:
            raise ValueError(
                "refusing to emit a finding to issue-remediation-capa with no approval reference: "
                "a handover "
                "happens only after a human approved the finding through human-review-console"
            )
        self.outbox.append(handover)
        return f"aud3-feed:{handover.finding_id}:{len(self.outbox)}"

    def pending(self) -> tuple[IssueHandover, ...]:
        """The handovers recorded so far (the issue-remediation-capa boundary, made inspectable)."""
        return tuple(self.outbox)
