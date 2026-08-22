"""Local KnowledgeBaseReadPort: a deterministic fixture corpus for fieldwork grounding.

Stands in for the governed workpaper / prior-audit store offline: a fixed, obviously-fictional
passage set per area. It returns real passages for a seeded area (so the fieldwork engine drafts
a grounded working paper) and an EMPTY tuple for an unknown one (so the "empty retrieval means no
draft" path is exercised offline too). A silent failure would look like an empty corpus, so a
genuine reach failure is the managed/on-prem family's job to raise, never this one's.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.fieldwork import RetrievalQuery, RetrievedPassage

_SEED: dict[str, tuple[RetrievedPassage, ...]] = {
    "payments": (
        RetrievedPassage(
            source_id="wp-2025-pay-01",
            title="Prior-year payments workpaper",
            snippet="Reconciliation breaks aged over 30 days were not escalated (FICTIONAL).",
        ),
        RetrievedPassage(
            source_id="wp-2025-pay-02",
            title="Sanctions screening test log",
            snippet="Two of forty payments bypassed screening on a fallback path (FICTIONAL).",
        ),
    ),
    "onboarding": (
        RetrievedPassage(
            source_id="wp-2025-kyc-01",
            title="Prior-year onboarding workpaper",
            snippet="CDD evidence complete for all sampled accounts (FICTIONAL).",
        ),
    ),
}


class LocalKnowledgeBaseAdapter:
    """Answer retrieval from a deterministic fixture corpus (no File Search, no network)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, query: RetrievalQuery) -> tuple[RetrievedPassage, ...]:
        return _SEED.get(query.area, ())[: max(0, query.limit)]
