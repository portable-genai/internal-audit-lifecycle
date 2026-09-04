"""ObligationsReadPort: read-only access to obligations-control-mapping's obligation register
(system of record).

internal-audit-lifecycle pulls the obligations for an audited area from obligations-control-mapping,
the SINGLE SYSTEM OF RECORD for the obligation graph, and never keeps a parallel register. This port
is READ-ONLY by construction: it returns obligations, it cannot write them. The ``local`` adapter
answers from a deterministic fixture (obligations-control-mapping's contract, frozen as a fixture
test), the ``gcp`` adapter reads obligations-control-mapping's REST / A2A read surface (lazy,
refuses when unconfigured), and the ``onprem`` adapter fails fast.

The domain stays pure: this is a Protocol, and its return DTO lives in ``domain/scoping.py`` next
to the engine that consumes it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.scoping import ObligationRef


@runtime_checkable
class ObligationsReadPort(Protocol):
    def obligations_for(self, area: str) -> tuple[ObligationRef, ...]:
        """Return the obligations obligations-control-mapping holds for ``area`` (possibly empty),
        read-only.

        A failure to reach obligations-control-mapping is a raised error (the managed family) or a
        raised
        ``NotImplementedError`` (the on-premises placeholder), never a silent empty success a
        caller could mistake for "this area has no obligations".
        """
        ...
