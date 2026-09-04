"""On-prem HorizonPort adapter: fail-fast portability placeholder (P-12).

The client wires its own compliance-advisory link behind this seam. Until then it refuses at call
time rather than pretending, so a placeholder never becomes a silent empty answer that would look
like a real result.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.planning import HorizonSignal


class OnPremHorizonAdapter:
    """Satisfies the port but refuses at call time: the client binds its own compliance-advisory
    link.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def signals(self) -> tuple[HorizonSignal, ...]:
        raise NotImplementedError(
            "on-prem horizon is a portability placeholder: bind the client's own "
            "compliance-advisory connection (see docs/onprem-migration.md)"
        )
