"""On-prem FindingFeedPort adapter: fail-fast portability placeholder (P-12).

The client wires its own issue-remediation-capa link behind this seam. Until then it refuses at call
time rather than pretending, so a placeholder never becomes a silent empty answer that would look
like a real result.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.findings import IssueHandover


class OnPremFindingFeedAdapter:
    """Satisfies the port but refuses at call time: the client binds its own issue-remediation-capa
    link.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def emit(self, handover: IssueHandover) -> str:
        raise NotImplementedError(
            "on-prem finding_feed is a portability placeholder: bind the client's own "
            "issue-remediation-capa connection (see docs/onprem-migration.md)"
        )
