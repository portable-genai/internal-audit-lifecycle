"""GCP KnowledgeBasePort adapter: reach the knowledge base over HTTPS, refusing when unconfigured.

The endpoint is per-deployment config (AUDIT_KNOWLEDGE_BASE_URL), read three-state: UNSET and
SET-AND-EMPTY both arrive as ``""``, and this adapter REFUSES every call rather than reaching a
default host. That refusal is the managed-family behaviour the parity suite asserts offline.
When set, the ``google.*`` auth import stays INSIDE the method so ``local`` / ``onprem`` import
this module with no cloud SDK (the portability proof).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.fieldwork import RetrievalQuery, RetrievedPassage


class CloudKnowledgeBaseAdapter:
    """Reach the retrieval store over HTTPS, or refuse when the endpoint is unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, query: RetrievalQuery) -> tuple[RetrievedPassage, ...]:
        url = self._settings.knowledge_base_url
        if not url:
            raise RuntimeError(
                "knowledge-base endpoint is unconfigured: set AUDIT_KNOWLEDGE_BASE_URL "
                "to the deployment URL. There is no default host to fall back to."
            )
        return self._reach(url, query)

    def _reach(
        self, url: str, query: RetrievalQuery
    ) -> tuple[RetrievedPassage, ...]:  # pragma: no cover - needs live the knowledge base
        # Lazy import: absent offline and in CI, so a managed run without the SDK raises here.
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.get(url, params={"area": query.area, "q": query.text}, timeout=10.0)
        response.raise_for_status()
        return self._parse(response.json())

    @staticmethod
    def _parse(
        payload: object,
    ) -> tuple[RetrievedPassage, ...]:  # pragma: no cover - needs live the knowledge base
        raise NotImplementedError(
            "wire the knowledge base payload parsing when its live surface is available"
        )
