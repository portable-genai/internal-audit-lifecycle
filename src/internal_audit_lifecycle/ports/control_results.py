"""ControlResultsReadPort: read-only access to Aud2's control-effectiveness results.

Aud2 (Continuous Controls Monitoring) is not built yet, so the ``local`` adapter answers from a
deterministic fixture that freezes the contract Aud1 expects (a fixture test pins it), and the
``gcp`` adapter reads Aud2's REST / A2A surface once it exists (lazy, refuses when unconfigured);
``onprem`` fails fast. Aud1 READS these verdicts and holds no control catalog of its own: the
control-triad boundary means every control id in an Aud1 output originated from a read.

The return DTO lives in ``domain/scoping.py`` next to the scoping engine that consumes it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.scoping import ControlResult


@runtime_checkable
class ControlResultsReadPort(Protocol):
    def results_for(self, area: str) -> tuple[ControlResult, ...]:
        """Return Aud2's latest control-effectiveness results for ``area`` (possibly empty).

        A failure to reach Aud2 is a raised error (managed) or ``NotImplementedError`` (on-prem),
        never a silent empty success.
        """
        ...
