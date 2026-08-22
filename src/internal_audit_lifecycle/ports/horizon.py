"""HorizonReadPort: read-only access to Rsk1's regulatory-horizon change-feed signal.

Rsk1 is the SINGLE source of regulatory-horizon change; Aud1 reads a per-entity signal count from
it to feed the planning engine's ``horizon_pressure`` driver, and never recomputes horizon change
itself. The ``local`` adapter answers from a deterministic fixture (Rsk1's ledger-diff contract,
frozen as a fixture test), ``gcp`` reads Rsk1's change-feed surface (lazy, refuses when
unconfigured), and ``onprem`` fails fast.

The return DTO lives in ``domain/planning.py`` next to the planner that consumes it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.planning import HorizonSignal


@runtime_checkable
class HorizonReadPort(Protocol):
    def signals(self) -> tuple[HorizonSignal, ...]:
        """Return the current per-entity horizon signal counts (possibly empty), read-only.

        A failure to reach Rsk1 is a raised error (managed) or ``NotImplementedError`` (on-prem),
        never a silent empty success that would zero out every entity's horizon pressure.
        """
        ...
