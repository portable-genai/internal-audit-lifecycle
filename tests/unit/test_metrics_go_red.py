"""Every engine metric must be able to go RED, or it is not a metric (the independent-oracle rule).

Each deterministic engine is scored against a dataset's OWN expected outcome, never the engine's
own verdict. This suite proves that when the expected outcome DISAGREES with the engine (the
degraded/mutant case), the metric falls below its threshold. A metric that stays green on the
mutant is falsely green and catches nothing.
"""

from __future__ import annotations

from datetime import date

from agent_eval_kit import assert_can_go_red

from internal_audit_lifecycle.domain.findings import FindingInput, FindingService
from internal_audit_lifecycle.domain.narration import narrative_is_grounded
from internal_audit_lifecycle.domain.planning import (
    AnnualPlanner,
    enrich_universe,
    seed_universe,
)
from internal_audit_lifecycle.domain.scoping import SampleUnit, stratified_sample

_FACTS = (("entities", "4"), ("rank_1_score", "100"))


def _plan_score_for(expected_score: int) -> float:
    """1.0 iff the engine's ent-payments score equals the oracle figure it is handed."""
    plan = AnnualPlanner().rank(
        enrich_universe(seed_universe(), ()), as_of=date(2026, 8, 8), scope="e"
    )
    entry = next(e for e in plan.entries if e.entity_id == "ent-payments")
    return 1.0 if entry.score == expected_score else 0.0


def test_plan_ranking_accuracy_can_go_red() -> None:
    assert_can_go_red(
        _plan_score_for,
        green=100,  # the hand-computed oracle score for ent-payments
        red=999,  # a wrong oracle: a falsely-green metric would still score this 1.0
        threshold=0.99,
        metric="plan_ranking_accuracy",
    )


def _severity_for(expected: str) -> float:
    """1.0 iff the engine's severity for a (5, 5) finding equals the oracle severity handed in."""
    result = FindingService().assess(
        FindingInput(engagement="e", title="t", area="a", impact=5, likelihood=5, evidence=())
    )
    return 1.0 if result.severity.value == expected else 0.0


def test_severity_accuracy_can_go_red() -> None:
    assert_can_go_red(
        _severity_for,
        green="critical",  # 5 x 5 = 25 -> critical
        red="low",  # the wrong expectation must drive the metric red
        threshold=0.99,
        metric="severity_accuracy",
    )


def _stratification_for(expected: tuple[tuple[str, int], ...]) -> float:
    """1.0 iff the engine's allocation matches the oracle allocation handed in."""
    units = (
        SampleUnit(id="ctrl-a", stratum="control"),
        SampleUnit(id="ctrl-b", stratum="control"),
        SampleUnit(id="obl-a", stratum="obligation"),
        SampleUnit(id="obl-b", stratum="obligation"),
    )
    sample = stratified_sample(units, seed=1, as_of="2026-08-08", size=3)
    return 1.0 if dict(sample.strata) == dict(expected) else 0.0


def test_sample_stratification_can_go_red() -> None:
    assert_can_go_red(
        _stratification_for,
        green=(("control", 2), ("obligation", 1)),
        red=(("control", 3),),
        threshold=0.99,
        metric="sample_stratification",
    )


def _groundedness_for(text: str) -> float:
    """1.0 iff every integer in ``text`` is one the engine facts contain."""
    return 1.0 if narrative_is_grounded(text, _FACTS) else 0.0


def test_narration_groundedness_can_go_red() -> None:
    assert_can_go_red(
        _groundedness_for,
        green="The plan ranks 4 entities; the top scores 100.",  # 4 and 100 are engine figures
        red="The plan ranks 4 entities; the top scores 999.",  # 999 is invented -> ungrounded
        threshold=0.99,
        metric="plan_narration_groundedness",
    )
