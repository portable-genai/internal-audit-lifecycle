"""Object-level authorisation: a verified principal's tenant against the audited estate's owner.

The audit universe, its plans, scopes, working papers and findings all belong to ONE owning
tenant offline (the seeded ``demo-bank``). Authorisation is made against the VERIFIED principal's
tenant, never a client-asserted one, and a caller from another tenant is refused with 403 (the
estate EXISTS and the caller is simply not authorised for it), never 404. There is deliberately no
permissive default: the caller passes the tenant it resolved from the verified principal.
"""

from __future__ import annotations

__all__ = ["ESTATE_TENANT", "CrossTenantError", "authorize_estate_access"]

#: The tenant that OWNS the offline seed estate. In a deployment each row carries its owning
#: tenant; offline the seed IS the demo bank's estate, so any other verified tenant is refused.
ESTATE_TENANT = "demo-bank"


class CrossTenantError(Exception):
    """A verified principal asked for an estate owned by another tenant (surface maps to 403)."""

    def __init__(self, principal_tenant: str, estate_tenant: str) -> None:
        super().__init__(
            f"tenant {principal_tenant!r} is not authorised for the audit estate owned by "
            f"{estate_tenant!r}"
        )
        self.principal_tenant = principal_tenant
        self.estate_tenant = estate_tenant


def authorize_estate_access(principal_tenant: str, *, estate_tenant: str = ESTATE_TENANT) -> None:
    """Authorise a VERIFIED principal's tenant against the estate's owning tenant, or raise."""
    if principal_tenant != estate_tenant:
        raise CrossTenantError(principal_tenant, estate_tenant)
