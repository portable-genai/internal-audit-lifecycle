"""KnowledgeBaseReadPort: the governed workpaper / prior-audit retrieval store (rule R3).

Fieldwork grounds its working-paper drafts against retrieved evidence, and internal-audit-lifecycle
does NOT build a retrieval backend of its own: the workpaper and prior-audit corpus is ingested into
the shared governed store and retrieved from it (governed RAG). The ``local`` adapter answers from a
deterministic fixture corpus, the ``gcp`` adapter reads Gemini API File Search over the corpus
(lazy, refuses when unconfigured), and ``onprem`` fails fast. Empty retrieval is a legitimate answer
the fieldwork engine turns into "no draft"; a failure to REACH the store is a raised error.

The query and passage DTOs live in ``domain/fieldwork.py`` next to the engine that consumes them.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.fieldwork import RetrievalQuery, RetrievedPassage


@runtime_checkable
class KnowledgeBaseReadPort(Protocol):
    def search(self, query: RetrievalQuery) -> tuple[RetrievedPassage, ...]:
        """Retrieve ranked grounding passages for ``query`` (possibly empty).

        An empty tuple means the corpus had nothing to ground against (the fieldwork engine then
        declines to draft). A failure to reach the store is a raised error (managed) or
        ``NotImplementedError`` (on-prem), never a silent empty success that would look like an
        empty corpus.
        """
        ...
