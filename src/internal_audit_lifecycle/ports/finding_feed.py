"""FindingFeedPort: the one-way emit of an APPROVED finding to Aud3 (the control-triad boundary).

Aud1 RAISES findings; Aud3 OWNS the post-finding remediation lifecycle to closure. This port is
the whole seam between them: a finding, once a human has approved it through Hrz7, is emitted as a
normalized :class:`~..domain.findings.IssueHandover` on the Aud3 feed and nothing more. There is
deliberately NO remediation/CAPA store port in this repo, and the no-remediation-store contract
test fails the build if one appears. The ``local`` adapter records the handover in an inspectable
outbox, ``gcp`` posts to Aud3's intake surface (lazy, refuses when unconfigured), ``onprem`` fails
fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.findings import IssueHandover


@runtime_checkable
class FindingFeedPort(Protocol):
    def emit(self, handover: IssueHandover) -> str:
        """Emit one approved finding to Aud3 and return the feed reference.

        A finding with an empty ``approval_ref`` is a programming error: emission happens only
        after a human approved the finding through Hrz7. A failure to reach Aud3 is a raised
        error (managed) or ``NotImplementedError`` (on-prem), never a silent success.
        """
        ...
