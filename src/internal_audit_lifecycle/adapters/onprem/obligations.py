"""On-prem ObligationsPort adapter: fail-fast portability placeholder (P-12).

The client wires its own Rgc7 link behind this seam. Until then it refuses at call time
rather than pretending, so a placeholder never becomes a silent empty answer that would look
like a real result.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.scoping import ObligationRef


class OnPremObligationsAdapter:
    """Satisfies the port but refuses at call time: the client binds its own Rgc7 link."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def obligations_for(self, area: str) -> tuple[ObligationRef, ...]:
        raise NotImplementedError(
            "on-prem obligations is a portability placeholder: bind the client's own "
            "Rgc7 connection (see docs/onprem-migration.md)"
        )
