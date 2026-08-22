"""On-prem KnowledgeBasePort adapter: fail-fast portability placeholder (P-12).

The client wires its own retrieval-store link behind this seam. Until then it refuses at
rather than pretending, so a placeholder never becomes a silent empty answer that would look
like a real result.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.fieldwork import RetrievalQuery, RetrievedPassage


class OnPremKnowledgeBaseAdapter:
    """Satisfies the port but refuses at call time: the client binds its own retrieval link."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, query: RetrievalQuery) -> tuple[RetrievedPassage, ...]:
        raise NotImplementedError(
            "on-prem knowledge_base is a portability placeholder: bind the client's own "
            "the knowledge base connection (see docs/onprem-migration.md)"
        )
