"""GCP ObligationsPort adapter: reach obligations-control-mapping over HTTPS, refusing when
unconfigured.

The endpoint is per-deployment config (AUDIT_OBLIGATIONS_URL), read three-state: UNSET and
SET-AND-EMPTY both arrive as ``""``, and this adapter REFUSES every call rather than reaching a
default host. That refusal is the managed-family behaviour the parity suite asserts offline.
When set, the ``google.*`` auth import stays INSIDE the method so ``local`` / ``onprem`` import
this module with no cloud SDK (the portability proof).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.scoping import ObligationRef


class CloudObligationsAdapter:
    """Reach obligations-control-mapping over its authenticated HTTPS surface, or refuse when
    unconfigured.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def obligations_for(self, area: str) -> tuple[ObligationRef, ...]:
        url = self._settings.obligations_url
        if not url:
            raise RuntimeError(
                "obligations-control-mapping endpoint is unconfigured: set AUDIT_OBLIGATIONS_URL "
                "to the deployment "
                "URL. There is no default host to fall back to."
            )
        return self._reach(url, area)

    def _reach(
        self, url: str, area: str
    ) -> tuple[ObligationRef, ...]:  # pragma: no cover - needs live obligations-control-mapping
        # Lazy import: absent offline and in CI, so a managed run without the SDK raises here.
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.get(url, params={"area": area}, timeout=10.0)
        response.raise_for_status()
        return self._parse(response.json())

    @staticmethod
    def _parse(
        payload: object,
    ) -> tuple[ObligationRef, ...]:  # pragma: no cover - needs live obligations-control-mapping
        raise NotImplementedError(
            "wire obligations-control-mapping payload parsing when its live surface is available"
        )
