"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.fieldwork import Workpaper
from ..domain.findings import Finding
from ..domain.models import TriageResult
from ..domain.planning import AnnualPlan
from ..domain.scoping import EngagementScope, SampleResult


class TriageRequest(BaseModel):
    subject: str
    text: str


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class TriageResponse(BaseModel):
    subject: str
    severity: str
    decision: str
    summary: str
    requires_human_review: bool
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the result did not escalate. A caller can tell a routed escalation from
    #: a flag that stopped here, which is the whole point of the rule.
    review_ref: str = ""
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, result: TriageResult, *, review_ref: str = "") -> TriageResponse:
        return cls(
            subject=result.subject,
            severity=result.severity.value,
            decision=result.decision.value,
            summary=result.summary,
            requires_human_review=result.requires_human_review,
            review_ref=review_ref,
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: Provenance the UI banner states on every page: where the runtime sits and which model
    #: answers. Both are read off the service because the browser cannot know either.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"


def _citations(items: object) -> list[CitationModel]:
    out: list[CitationModel] = []
    for c in items:  # type: ignore[attr-defined]
        out.append(CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet))
    return out


# --------------------------------------------------------------------------- #
# Slice 1: risk-based annual planning
# --------------------------------------------------------------------------- #
class PlanRequest(BaseModel):
    scope: str = "FY2027 annual audit plan"
    as_of: str = "2026-08-08"  # ISO date the ranking is computed as of


class PlanEntryModel(BaseModel):
    entity_id: str
    name: str
    score: int
    band: str
    rank: int
    drivers: list[dict[str, object]]


class PlanResponse(BaseModel):
    scope: str
    as_of: str
    severity: str
    requires_human_review: bool
    review_ref: str = ""
    narrative: str
    narrative_model_authored: bool
    entries: list[PlanEntryModel]
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(
        cls,
        plan: AnnualPlan,
        *,
        narrative: str,
        narrative_model_authored: bool,
        review_ref: str,
    ) -> PlanResponse:
        return cls(
            scope=plan.scope,
            as_of=plan.as_of,
            severity=plan.severity.value,
            requires_human_review=plan.requires_human_review,
            review_ref=review_ref,
            narrative=narrative,
            narrative_model_authored=narrative_model_authored,
            entries=[
                PlanEntryModel(
                    entity_id=e.entity_id,
                    name=e.name,
                    score=e.score,
                    band=e.band.value,
                    rank=e.rank,
                    drivers=[
                        {"name": d.name, "points": d.points, "detail": d.detail} for d in e.drivers
                    ],
                )
                for e in plan.entries
            ],
            citations=_citations(plan.citations),
        )


# --------------------------------------------------------------------------- #
# Slice 2: scoping and sampling
# --------------------------------------------------------------------------- #
class ScopeRequest(BaseModel):
    area: str = "payments"
    seed: int = 20260808
    sample_size: int = 3
    as_of: str = "2026-08-08"


class ScopeResponse(BaseModel):
    area: str
    obligations: list[dict[str, str]]
    control_results: list[dict[str, str]]
    failing_controls: list[str]
    sample_seed: int
    sample_size: int
    sample_strata: list[dict[str, int]]
    sample_selected: list[str]
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, scope: EngagementScope, sample: SampleResult) -> ScopeResponse:
        return cls(
            area=scope.area,
            obligations=[
                {"id": o.id, "title": o.title, "owner": o.owner} for o in scope.obligations
            ],
            control_results=[
                {"control_id": c.control_id, "effectiveness": c.effectiveness, "as_of": c.as_of}
                for c in scope.control_results
            ],
            failing_controls=list(scope.failing_controls),
            sample_seed=sample.seed,
            sample_size=sample.size,
            sample_strata=[{stratum: count} for stratum, count in sample.strata],
            sample_selected=list(sample.selected),
            citations=_citations(scope.citations),
        )


# --------------------------------------------------------------------------- #
# Slice 3: fieldwork / working-paper drafting
# --------------------------------------------------------------------------- #
class WorkpaperRequest(BaseModel):
    area: str = "payments"
    text: str = "Assess whether reconciliation breaks were escalated on time."


class WorkpaperResponse(BaseModel):
    area: str
    drafted: bool
    text: str
    model_authored: bool
    grounded: bool
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, wp: Workpaper) -> WorkpaperResponse:
        return cls(
            area=wp.area,
            drafted=wp.drafted,
            text=wp.text,
            model_authored=wp.model_authored,
            grounded=wp.grounded,
            citations=_citations(wp.citations),
        )


# --------------------------------------------------------------------------- #
# Slice 4: finding write-up and the Aud3 handover
# --------------------------------------------------------------------------- #
class FindingRequest(BaseModel):
    engagement: str = "payments-fy2027"
    area: str = "payments"
    title: str = "Reconciliation breaks not escalated"
    impact: int = 4
    likelihood: int = 4


class FindingResponse(BaseModel):
    id: str
    engagement: str
    area: str
    title: str
    score: int
    severity: str
    requires_human_review: bool
    review_ref: str = ""
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, finding: Finding, *, review_ref: str) -> FindingResponse:
        return cls(
            id=finding.id,
            engagement=finding.engagement,
            area=finding.area,
            title=finding.title,
            score=finding.score,
            severity=finding.severity.value,
            requires_human_review=finding.requires_human_review,
            review_ref=review_ref,
            citations=_citations(finding.citations),
        )


class HandoverRequest(FindingRequest):
    #: The Hrz7 review reference proving a human approved the finding before it is emitted to Aud3.
    approval_ref: str


class HandoverResponse(BaseModel):
    finding_id: str
    severity: str
    source_system: str
    approval_ref: str
    feed_ref: str
