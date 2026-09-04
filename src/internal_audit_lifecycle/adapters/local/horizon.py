"""Local HorizonReadPort: a deterministic fixture of compliance-advisory's horizon change-feed
signal.

compliance-advisory is not reachable in the offline gate, so this stands in for its ledger-diff
output with a fixed per-entity signal count (a fixture test freezes the shape). It matches the seed
audit universe entity ids, so the planner's ``horizon_pressure`` driver has real input offline.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.planning import HorizonSignal


def _sig(entity_id: str, signals: int) -> HorizonSignal:
    return HorizonSignal(
        entity_id=entity_id,
        signals=signals,
        citation=Citation(
            source_id=f"rsk1://horizon/{entity_id}",
            title="compliance-advisory horizon change-feed",
            snippet=f"{signals} open change item(s) (FICTIONAL)",
        ),
    )


_SEED: tuple[HorizonSignal, ...] = (
    _sig("ent-payments", 3),
    _sig("ent-treasury", 2),
    _sig("ent-onboarding", 1),
    _sig("ent-facilities", 0),
)


class LocalHorizonAdapter:
    """Answer horizon-signal reads from a deterministic fixture (no compliance-advisory, no
    network).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def signals(self) -> tuple[HorizonSignal, ...]:
        return _SEED
