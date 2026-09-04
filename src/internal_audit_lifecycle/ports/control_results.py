"""ControlResultsReadPort: read-only access to continuous-controls-monitoring's
control-effectiveness results.

continuous-controls-monitoring (Continuous Controls Monitoring) is not built yet, so the ``local``
adapter answers from a deterministic fixture that freezes the contract internal-audit-lifecycle
expects (a fixture test pins it), and the ``gcp`` adapter reads continuous-controls-monitoring's
REST / A2A surface once it exists (lazy, refuses when unconfigured); ``onprem`` fails fast.
internal-audit-lifecycle READS these verdicts and holds no control catalog of its own: the
control-triad boundary means every control id in an internal-audit-lifecycle output originated from
a read.

The return DTO lives in ``domain/scoping.py`` next to the scoping engine that consumes it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.scoping import ControlResult


@runtime_checkable
class ControlResultsReadPort(Protocol):
    def results_for(self, area: str) -> tuple[ControlResult, ...]:
        """Return continuous-controls-monitoring's latest control-effectiveness results for ``area``
        (possibly empty).

        A failure to reach continuous-controls-monitoring is a raised error (managed) or
        ``NotImplementedError`` (on-prem),
        never a silent empty success.
        """
        ...
