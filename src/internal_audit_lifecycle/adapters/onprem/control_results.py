"""On-prem ControlResultsPort adapter: fail-fast portability placeholder (P-12).

The client wires its own Aud2 link behind this seam. Until then it refuses at call time
rather than pretending, so a placeholder never becomes a silent empty answer that would look
like a real result.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.scoping import ControlResult


class OnPremControlResultsAdapter:
    """Satisfies the port but refuses at call time: the client binds its own Aud2 link."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def results_for(self, area: str) -> tuple[ControlResult, ...]:
        raise NotImplementedError(
            "on-prem control_results is a portability placeholder: bind the client's own "
            "Aud2 connection (see docs/onprem-migration.md)"
        )
