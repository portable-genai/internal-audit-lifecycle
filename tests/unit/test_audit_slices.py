"""Unit tests for the four audit-lifecycle engines: determinism, oracles and the boundaries.

These are the substance of internal-audit-lifecycle: the consequential numbers come from pure code,
are replayable, and match an independent hand-computed expectation. The model narrates only, and the
fieldwork engine refuses to draft when retrieval is empty.
"""

from __future__ import annotations

from datetime import date

from internal_audit_lifecycle.domain.fieldwork import (
    RetrievalQuery,
    RetrievedPassage,
    WorkpaperService,
    draft_is_grounded,
)
from internal_audit_lifecycle.domain.findings import (
    FindingConfig,
    FindingInput,
    FindingService,
    handover_envelope,
)
from internal_audit_lifecycle.domain.kernel import Citation, Severity
from internal_audit_lifecycle.domain.planning import (
    AnnualPlanner,
    HorizonSignal,
    enrich_universe,
    seed_universe,
)
from internal_audit_lifecycle.domain.scoping import (
    ControlResult,
    ObligationRef,
    SampleUnit,
    ScopingService,
    stratified_sample,
)


# --------------------------------------------------------------------------- #
# Slice 1: planning
# --------------------------------------------------------------------------- #
def test_planning_is_replayable_and_matches_the_hand_computed_oracle() -> None:
    universe = enrich_universe(seed_universe(), ())
    a = AnnualPlanner().rank(universe, as_of=date(2026, 8, 8), scope="fy")
    b = AnnualPlanner().rank(universe, as_of=date(2026, 8, 8), scope="fy")
    assert a == b, "the same universe must always yield the same ranked plan"

    by_id = {e.entity_id: (e.score, e.band, e.rank) for e in a.entries}
    assert by_id["ent-payments"] == (100, Severity.CRITICAL, 1)
    assert by_id["ent-treasury"] == (67, Severity.HIGH, 2)
    assert by_id["ent-onboarding"] == (50, Severity.MEDIUM, 3)
    assert by_id["ent-facilities"] == (5, Severity.LOW, 4)


def test_planning_is_always_escalated_and_cited() -> None:
    plan = AnnualPlanner().rank(
        enrich_universe(seed_universe(), ()), as_of=date(2026, 8, 8), scope="s"
    )
    assert plan.requires_human_review is True
    assert plan.severity is Severity.CRITICAL
    assert plan.citations, "a ranked plan must cite the universe rows behind it"


def test_horizon_enrichment_overlays_the_read_signal() -> None:
    universe = seed_universe()
    bumped = enrich_universe(
        universe,
        (HorizonSignal(entity_id="ent-facilities", signals=9, citation=Citation("rsk1", "x")),),
    )
    facilities = next(e for e in bumped if e.id == "ent-facilities")
    assert facilities.horizon_signals == 9, "the freshly read signal must overlay the stored value"


# --------------------------------------------------------------------------- #
# Slice 2: scoping and sampling
# --------------------------------------------------------------------------- #
def _obl(oid: str, area: str) -> ObligationRef:
    return ObligationRef(id=oid, title=oid, area=area, owner="o", citation=Citation(oid, oid))


def _ctrl(cid: str, area: str, eff: str) -> ControlResult:
    return ControlResult(
        control_id=cid,
        area=area,
        effectiveness=eff,
        as_of="2026-07-31",
        citation=Citation(cid, cid),
    )


def test_scoping_filters_to_area_and_flags_failing_controls() -> None:
    scope = ScopingService().build_scope(
        "payments",
        (_obl("o1", "payments"), _obl("o2", "onboarding")),
        (_ctrl("c1", "payments", "fail"), _ctrl("c2", "payments", "pass")),
    )
    assert [o.id for o in scope.obligations] == ["o1"]
    assert scope.failing_controls == ("c1",), "only a non-pass control is flagged for sampling"


def test_sampling_is_byte_identical_on_replay() -> None:
    units = tuple(
        SampleUnit(id=f"u{i}", stratum="control" if i % 2 else "obligation") for i in range(10)
    )
    a = stratified_sample(units, seed=42, as_of="2026-08-08", size=4)
    b = stratified_sample(units, seed=42, as_of="2026-08-08", size=4)
    assert a == b
    assert a.size == 4
    assert sum(count for _s, count in a.strata) == 4


def test_sampling_allocates_proportionally_across_strata() -> None:
    units = (
        SampleUnit(id="c1", stratum="control"),
        SampleUnit(id="c2", stratum="control"),
        SampleUnit(id="o1", stratum="obligation"),
        SampleUnit(id="o2", stratum="obligation"),
    )
    sample = stratified_sample(units, seed=20260808, as_of="2026-08-08", size=3)
    assert dict(sample.strata) == {"control": 2, "obligation": 1}


# --------------------------------------------------------------------------- #
# Slice 3: fieldwork
# --------------------------------------------------------------------------- #
class _GroundedGen:
    def generate(self, request: object) -> object:
        import json

        from internal_audit_lifecycle.ports.generation import GenerationResponse

        cited = "; ".join(f"[{src}] ok" for src, _ in request.facts)  # type: ignore[attr-defined]
        return GenerationResponse(text=json.dumps({"workpaper": cited}))


class _HallucinatingGen:
    def generate(self, request: object) -> object:
        import json

        from internal_audit_lifecycle.ports.generation import GenerationResponse

        return GenerationResponse(text=json.dumps({"workpaper": "cites [not-a-source]"}))


def test_fieldwork_declines_to_draft_on_empty_retrieval() -> None:
    wp = WorkpaperService(_GroundedGen()).draft(RetrievalQuery(area="x", text="q"), ())
    assert wp.drafted is False
    assert wp.text == "" and not wp.citations


def test_fieldwork_keeps_a_grounded_model_draft() -> None:
    passages = (RetrievedPassage(source_id="wp-1", title="t", snippet="s"),)
    wp = WorkpaperService(_GroundedGen()).draft(RetrievalQuery(area="x", text="q"), passages)
    assert wp.drafted and wp.model_authored and wp.grounded
    assert draft_is_grounded(wp.text, passages)


def test_fieldwork_discards_an_ungrounded_model_draft() -> None:
    passages = (RetrievedPassage(source_id="wp-1", title="t", snippet="s"),)
    wp = WorkpaperService(_HallucinatingGen()).draft(RetrievalQuery(area="x", text="q"), passages)
    assert wp.drafted and wp.grounded
    assert wp.model_authored is False, "a draft citing an unretrieved source must be discarded"


# --------------------------------------------------------------------------- #
# Slice 4: findings
# --------------------------------------------------------------------------- #
def test_finding_severity_is_deterministic_impact_times_likelihood() -> None:
    service = FindingService()
    assert service.assess(_finding(5, 5)).severity is Severity.CRITICAL
    assert service.assess(_finding(4, 4)).severity is Severity.HIGH
    assert service.assess(_finding(3, 3)).severity is Severity.MEDIUM
    assert service.assess(_finding(2, 2)).severity is Severity.LOW


def test_finding_always_requires_review_and_clamps_out_of_range_scales() -> None:
    result = FindingService(FindingConfig()).assess(_finding(99, -3))
    assert result.requires_human_review is True
    assert result.score == 5 * 1, "impact clamps to 5 and likelihood clamps to 1"


def test_handover_carries_the_approval_ref_and_no_remediation_state() -> None:
    result = FindingService().assess(_finding(5, 5))
    envelope = handover_envelope(result, approval_ref="rev-9")
    assert envelope.approval_ref == "rev-9"
    assert envelope.source_system == "internal-audit-lifecycle"
    # The envelope carries WHAT was found, never any remediation/RCA/closure field.
    fields = set(vars(envelope)) if hasattr(envelope, "__dict__") else set(envelope.__slots__)
    assert not (fields & {"remediation", "rca", "closure", "capa", "status"})


def _finding(impact: int, likelihood: int) -> FindingInput:
    return FindingInput(
        engagement="e",
        title="t",
        area="payments",
        impact=impact,
        likelihood=likelihood,
        evidence=(),
    )
