"""Slice 4: finding write-up, deterministic severity, and the issue-remediation-capa handover (the
boundary).

A finding's severity is PURE CODE from config-owned criteria (an impact x likelihood matrix banded
by thresholds), never the model's opinion. Every finding sets ``requires_human_review``: the lead
auditor signs off through human-review-console, and only on approval is the finding emitted on the
issue-remediation-capa feed as a normalized :class:`IssueHandover`. The control-triad boundary is
enforced, not documented: internal-audit-lifecycle RAISES findings and holds NO remediation state.
The ``finding_feed`` port is a one-way emit to issue-remediation-capa; there is deliberately no
remediation/CAPA store port in this repo, and the no-remediation-store contract test fails the build
if one ever appears.

``IssueHandover`` is the read-port DTO the ``finding_feed`` port emits, defined here next to the
engine that produces it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kernel import Citation, Decision, Severity

__all__ = [
    "FindingConfig",
    "FindingInput",
    "Finding",
    "FindingService",
    "IssueHandover",
    "handover_envelope",
]

#: Reference severity bands over the impact x likelihood product (1..25). Config-owned (B4).
_DEFAULT_SEVERITY_FLOORS: dict[str, int] = {
    Severity.CRITICAL.value: 20,
    Severity.HIGH.value: 12,
    Severity.MEDIUM.value: 6,
    Severity.LOW.value: 0,
}

_BAND_ORDER: tuple[Severity, ...] = (
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


@dataclass(frozen=True, slots=True)
class FindingConfig:
    """Bank-owned finding-severity policy (B4). Defaults equal the reference policy."""

    min_scale: int = 1
    max_scale: int = 5
    severity_floors: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.severity_floors is None:
            object.__setattr__(self, "severity_floors", dict(_DEFAULT_SEVERITY_FLOORS))


@dataclass(frozen=True, slots=True)
class FindingInput:
    """One raw finding an auditor raises within an engagement (before the severity is computed)."""

    engagement: str
    title: str
    area: str
    impact: int
    likelihood: int
    evidence: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class Finding:
    """A written-up finding: deterministic severity, always escalated for lead-auditor sign-off.

    The field set overlaps the R8 review envelope (``subject`` / ``severity`` / ``decision`` /
    ``summary`` / ``requires_human_review`` / ``citations``) so a surface routes it to
    human-review-console
    without the pure domain importing a surface type.
    """

    id: str
    engagement: str
    area: str
    title: str
    score: int
    severity: Severity
    subject: str
    decision: Decision
    summary: str
    requires_human_review: bool
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class IssueHandover:
    """The normalized envelope emitted to issue-remediation-capa on approval (issue-remediation-capa
    owns everything after this).

    It carries WHAT was found and its severity, plus the approval reference that authorised the
    handover, and deliberately NO remediation, RCA or closure state: that lifecycle is
    issue-remediation-capa's.
    """

    finding_id: str
    engagement: str
    area: str
    title: str
    severity: str
    source_system: str
    approval_ref: str
    citations: tuple[tuple[str, str], ...]


class FindingService:
    """Write up a finding with a deterministic severity; hold no remediation state."""

    _SOURCE_SYSTEM = "internal-audit-lifecycle"

    def __init__(self, config: FindingConfig | None = None) -> None:
        self.config = config or FindingConfig()

    def _band(self, score: int) -> Severity:
        floors = self.config.severity_floors
        for band in reversed(_BAND_ORDER):
            floor = floors.get(band.value)
            if floor is not None and score >= int(floor):
                return band
        return Severity.LOW

    def assess(self, raw: FindingInput) -> Finding:
        """Compute a finding's severity from impact x likelihood; always escalate for sign-off."""
        lo, hi = self.config.min_scale, self.config.max_scale
        impact = max(lo, min(hi, raw.impact))
        likelihood = max(lo, min(hi, raw.likelihood))
        score = impact * likelihood
        severity = self._band(score)
        finding_id = f"find-{raw.engagement}-{raw.area}".lower().replace(" ", "-")
        summary = (
            f"{raw.title} in {raw.area}: impact {impact} x likelihood {likelihood} = {score} "
            f"-> {severity.value}"
        )
        return Finding(
            id=finding_id,
            engagement=raw.engagement,
            area=raw.area,
            title=raw.title,
            score=score,
            severity=severity,
            subject=raw.title,
            decision=Decision.ESCALATED,
            summary=summary,
            requires_human_review=True,
            citations=raw.evidence,
        )


def handover_envelope(finding: Finding, *, approval_ref: str) -> IssueHandover:
    """Build the issue-remediation-capa handover envelope for an APPROVED finding.

    ``approval_ref`` is the human-review-console review reference that authorised the handover: an
    empty one is a
    programming error, because a finding is only emitted to issue-remediation-capa after a human
    approved it. The
    caller (the surface) enforces that; this function records the reference it was given.
    """
    return IssueHandover(
        finding_id=finding.id,
        engagement=finding.engagement,
        area=finding.area,
        title=finding.title,
        severity=finding.severity.value,
        source_system=FindingService._SOURCE_SYSTEM,
        approval_ref=approval_ref,
        citations=tuple((c.source_id, c.title) for c in finding.citations),
    )
