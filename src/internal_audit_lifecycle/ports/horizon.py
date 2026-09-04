"""HorizonReadPort: read-only access to compliance-advisory's regulatory-horizon change-feed signal.

compliance-advisory is the SINGLE source of regulatory-horizon change; internal-audit-lifecycle
reads a per-entity signal count from it to feed the planning engine's ``horizon_pressure`` driver,
and never recomputes horizon change itself. The ``local`` adapter answers from a deterministic
fixture (compliance-advisory's ledger-diff contract, frozen as a fixture test), ``gcp`` reads
compliance-advisory's change-feed surface (lazy, refuses when unconfigured), and ``onprem`` fails
fast.

The return DTO lives in ``domain/planning.py`` next to the planner that consumes it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.planning import HorizonSignal


@runtime_checkable
class HorizonReadPort(Protocol):
    def signals(self) -> tuple[HorizonSignal, ...]:
        """Return the current per-entity horizon signal counts (possibly empty), read-only.

        A failure to reach compliance-advisory is a raised error (managed) or
        ``NotImplementedError`` (on-prem),
        never a silent empty success that would zero out every entity's horizon pressure.
        """
        ...
