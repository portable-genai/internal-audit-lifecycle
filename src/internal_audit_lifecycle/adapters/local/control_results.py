"""Local ControlResultsReadPort: a deterministic fixture of continuous-controls-monitoring's
effectiveness results.

continuous-controls-monitoring is not built yet, so this freezes the contract
internal-audit-lifecycle expects from it (a fixture test pins the shape) with fixed,
obviously-fictional control verdicts per area. When continuous-controls-monitoring ships, the
``gcp`` adapter reads its live surface and this fixture stays as the offline stand-in.
internal-audit-lifecycle READS these verdicts and never keeps a control catalog of its own.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.scoping import ControlResult

_AS_OF = "2026-07-31"

_SEED: dict[str, tuple[ControlResult, ...]] = {
    "payments": (
        ControlResult(
            control_id="ctrl-pay-recon",
            area="payments",
            effectiveness="fail",
            as_of=_AS_OF,
            citation=Citation(
                source_id="aud2://ctrl-pay-recon",
                title="Settlement reconciliation control",
                snippet="operating effectiveness FAIL (FICTIONAL)",
            ),
        ),
        ControlResult(
            control_id="ctrl-pay-screening",
            area="payments",
            effectiveness="partial",
            as_of=_AS_OF,
            citation=Citation(
                source_id="aud2://ctrl-pay-screening",
                title="Sanctions screening control",
                snippet="operating effectiveness PARTIAL (FICTIONAL)",
            ),
        ),
    ),
    "onboarding": (
        ControlResult(
            control_id="ctrl-kyc-idv",
            area="onboarding",
            effectiveness="pass",
            as_of=_AS_OF,
            citation=Citation(
                source_id="aud2://ctrl-kyc-idv",
                title="Identity verification control",
                snippet="operating effectiveness PASS (FICTIONAL)",
            ),
        ),
    ),
}


class LocalControlResultsAdapter:
    """Answer control-result reads from a deterministic fixture (no continuous-controls-monitoring,
    no network).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def results_for(self, area: str) -> tuple[ControlResult, ...]:
        return _SEED.get(area, ())
