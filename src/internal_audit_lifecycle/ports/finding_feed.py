"""FindingFeedPort: the one-way emit of an APPROVED finding to issue-remediation-capa (the
control-triad boundary).

internal-audit-lifecycle RAISES findings; issue-remediation-capa OWNS the post-finding remediation
lifecycle to closure. This port is the whole seam between them: a finding, once a human has approved
it through human-review-console, is emitted as a normalized
:class:`~..domain.findings.IssueHandover` on the issue-remediation-capa feed and nothing more. There
is deliberately NO remediation/CAPA store port in this repo, and the no-remediation-store contract
test fails the build if one appears. The ``local`` adapter records the handover in an inspectable
outbox, ``gcp`` posts to issue-remediation-capa's intake surface (lazy, refuses when unconfigured),
``onprem`` fails fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.findings import IssueHandover


@runtime_checkable
class FindingFeedPort(Protocol):
    def emit(self, handover: IssueHandover) -> str:
        """Emit one approved finding to issue-remediation-capa and return the feed reference.

        A finding with an empty ``approval_ref`` is a programming error: emission happens only
        after a human approved the finding through human-review-console. A failure to reach
        issue-remediation-capa is a raised
        error (managed) or ``NotImplementedError`` (on-prem), never a silent success.
        """
        ...
