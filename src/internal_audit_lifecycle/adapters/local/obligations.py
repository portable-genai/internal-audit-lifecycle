"""Local ObligationsReadPort: a deterministic fixture of Rgc7's obligation register.

Rgc7 is not reachable in the offline gate, so this stands in for its read surface with a fixed,
obviously-fictional obligation set per audited area. It freezes the contract Aud1 depends on (a
fixture test pins the shape), so the offline pipeline exercises the real scoping path with no
network and no cloud SDK. A silent empty return for a KNOWN area would let a producer ship the
scoping seam unwired, so every seeded area returns real, inspectable obligations.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.scoping import ObligationRef

_SEED: dict[str, tuple[ObligationRef, ...]] = {
    "payments": (
        ObligationRef(
            id="obl-pay-settlement",
            title="Same-day settlement reconciliation",
            area="payments",
            owner="payments-operations",
            citation=Citation(
                source_id="rgc7://obl-pay-settlement",
                title="Same-day settlement reconciliation",
                snippet="MAS TRM s5.2 (FICTIONAL)",
            ),
        ),
        ObligationRef(
            id="obl-pay-sanctions",
            title="Sanctions screening of outbound payments",
            area="payments",
            owner="financial-crime",
            citation=Citation(
                source_id="rgc7://obl-pay-sanctions",
                title="Sanctions screening of outbound payments",
                snippet="MAS 626 s7 (FICTIONAL)",
            ),
        ),
    ),
    "onboarding": (
        ObligationRef(
            id="obl-kyc-cdd",
            title="Customer due diligence at onboarding",
            area="onboarding",
            owner="compliance",
            citation=Citation(
                source_id="rgc7://obl-kyc-cdd",
                title="Customer due diligence at onboarding",
                snippet="MAS 626 s6 (FICTIONAL)",
            ),
        ),
    ),
}


class LocalObligationsAdapter:
    """Answer obligation reads from a deterministic fixture register (no Rgc7, no network)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def obligations_for(self, area: str) -> tuple[ObligationRef, ...]:
        return _SEED.get(area, ())
