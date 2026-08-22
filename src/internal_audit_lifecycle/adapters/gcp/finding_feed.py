"""GCP FindingFeedPort adapter: reach Aud3 over HTTPS, refusing when unconfigured.

The endpoint is per-deployment config (AUDIT_AUD3_FEED_URL), read three-state: UNSET and
SET-AND-EMPTY both arrive as ``""``, and this adapter REFUSES every call rather than reaching a
default host. That refusal is the managed-family behaviour the parity suite asserts offline.
When set, the ``google.*`` auth import stays INSIDE the method so ``local`` / ``onprem`` import
this module with no cloud SDK (the portability proof).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.findings import IssueHandover


class CloudFindingFeedAdapter:
    """Reach Aud3 over its authenticated HTTPS surface, or refuse when unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def emit(self, handover: IssueHandover) -> str:
        url = self._settings.aud3_feed_url
        if not url:
            raise RuntimeError(
                "Aud3 endpoint is unconfigured: set AUDIT_AUD3_FEED_URL to the deployment "
                "URL. There is no default host to fall back to."
            )
        return self._reach(url, handover)

    def _reach(
        self, url: str, handover: IssueHandover
    ) -> str:  # pragma: no cover - needs live Aud3
        # Lazy import: absent offline and in CI, so a managed run without the SDK raises here.
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.post(url, json={"finding_id": handover.finding_id}, timeout=10.0)
        response.raise_for_status()
        return self._parse(response.json())

    @staticmethod
    def _parse(payload: object) -> str:  # pragma: no cover - needs live Aud3
        raise NotImplementedError("wire Aud3 payload parsing when its live surface is available")
