#!/usr/bin/env python3
"""Evaluation gate for Internal Audit Lifecycle Copilot (internal-audit-lifecycle).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change. It drives the REAL
  deterministic engines (planning, sampling, finding severity) against INDEPENDENT hand-computed
  oracles, and the RAW local narrator through the same grounding contract the service enforces, with
  SDK-free local adapters. * **gate** - the promotion verdict from the shared model-quality-gate
  authority (requires the ``gcp`` profile), via ``agent_eval_kit.PromotionGateClient``.

Every engine metric scores the engine against the dataset's OWN expected outcome, never the
engine's own verdict, so each can go red (see ``tests/unit/test_not_falsely_green.py``). Exit is
``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from internal_audit_lifecycle.adapters.local.audit import (
    LocalAuditAdapter,
)
from internal_audit_lifecycle.adapters.local.generation import (
    LocalGenerationAdapter,
)
from internal_audit_lifecycle.adapters.local.tracer import (
    LocalNoopTracerAdapter,
)
from internal_audit_lifecycle.config import (
    Settings,
)
from internal_audit_lifecycle.domain import (
    fieldwork,
    narration,
)
from internal_audit_lifecycle.domain.fieldwork import (
    RetrievalQuery,
    RetrievedPassage,
)
from internal_audit_lifecycle.domain.findings import (
    FindingInput,
    FindingService,
)
from internal_audit_lifecycle.domain.models import (
    TriageInput,
)
from internal_audit_lifecycle.domain.pii import (
    PII_PATTERNS,
)
from internal_audit_lifecycle.domain.planning import (
    AnnualPlanner,
    enrich_universe,
    seed_universe,
)
from internal_audit_lifecycle.domain.scoping import (
    SampleUnit,
    stratified_sample,
)
from internal_audit_lifecycle.domain.triage_service import (
    TriageService,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"
PLAN_ORACLE = _REPO_ROOT / "eval" / "datasets" / "plan_oracle.jsonl"
FINDING_ORACLE = _REPO_ROOT / "eval" / "datasets" / "finding_oracle.jsonl"

THRESHOLDS: dict[str, float] = {
    "decision_accuracy": 0.80,
    "pii_safety": 0.99,
    "plan_ranking_accuracy": 0.99,
    "severity_accuracy": 0.99,
    "sample_stratification": 0.99,
    "sample_determinism": 0.99,
    "plan_narration_groundedness": 0.99,
    "workpaper_grounding": 0.99,
}
#: The registered model-quality-gate metric bundle for this vertical (model-quality-gate owns the
#: metrics + thresholds).
_BUNDLE = "internal-audit-lifecycle"

#: The hand-computed stratification oracle for the payments engagement (slice 2): the failing
#: controls (2) and obligations (2) sampled to size 3 allocate control:2, obligation:1.
_SAMPLE_ORACLE_STRATA = {"control": 2, "obligation": 1}
_SAMPLE_ORACLE_TOTAL = 3


def _load(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"{path}: oracle dataset is empty")
    return rows


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def audit_texts(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of every audit row, which is what a leak scan has to read.

    Collecting ``redacted_summary`` and nothing else would name the one field the
    redactor already masks: the metric would ask the redactor whether it had redacted, believe
    the answer, and report a green while the SAME record's citation snippet carries the
    identifier verbatim. Citations travel inside the record, and they carry raw source text in
    ``snippet`` and, routinely, in ``source_id`` (a locator built from the case subject).

    ``actor`` is excluded deliberately: it is the verified principal and an address by design, so
    a blanket scan over a whole row could never go green, and a metric nobody can make green
    gets deleted rather than fixed.
    """
    texts: list[str] = []
    for row in rows:
        texts.append(str(row.get("redacted_summary", "")))
        texts.append(json.dumps(row.get("citations", []), sort_keys=True))
    return texts


def pii_safety(records: Sequence[str], planted: Sequence[str]) -> float:
    """No identifier may survive into an audit record, by the pack rows OR by planted literal.

    Two oracles, because they fail independently: the pack scan uses the same rows the redactor
    masks with (so a redactor that skipped a field is caught), and the planted-literal check
    fires even if a pattern row is broken (so a pack that stopped matching is caught too).
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def score_plan_ranking(rows: list[dict[str, object]]) -> float:
    """Compare the engine's score/band/rank per entity to the independent oracle."""
    universe = enrich_universe(seed_universe(), ())
    plan = AnnualPlanner().rank(universe, as_of=date(2026, 8, 8), scope="eval")
    by_id = {e.entity_id: e for e in plan.entries}
    scores: list[float] = []
    for row in rows:
        entry = by_id.get(str(row["entity_id"]))
        ok = (
            entry is not None
            and entry.score == int(str(row["expected_score"]))
            and entry.band.value == str(row["expected_band"])
            and entry.rank == int(str(row["expected_rank"]))
        )
        scores.append(1.0 if ok else 0.0)
    return _mean(scores)


def score_severity(rows: list[dict[str, object]]) -> float:
    """Compare the finding engine's severity to the independent (impact, likelihood) oracle."""
    service = FindingService()
    scores: list[float] = []
    for row in rows:
        result = service.assess(
            FindingInput(
                engagement="eval",
                title="eval finding",
                area="eval",
                impact=int(str(row["impact"])),
                likelihood=int(str(row["likelihood"])),
                evidence=(),
            )
        )
        scores.append(1.0 if result.severity.value == str(row["expected_severity"]) else 0.0)
    return _mean(scores)


def _payments_units() -> tuple[SampleUnit, ...]:
    return (
        SampleUnit(id="ctrl-pay-recon", stratum="control"),
        SampleUnit(id="ctrl-pay-screening", stratum="control"),
        SampleUnit(id="obl-pay-settlement", stratum="obligation"),
        SampleUnit(id="obl-pay-sanctions", stratum="obligation"),
    )


def score_stratification() -> float:
    """The engine's per-stratum allocation must match the hand-computed oracle allocation."""
    sample = stratified_sample(_payments_units(), seed=20260808, as_of="2026-08-08", size=3)
    alloc = dict(sample.strata)
    return 1.0 if (alloc == _SAMPLE_ORACLE_STRATA and sample.size == _SAMPLE_ORACLE_TOTAL) else 0.0


def score_determinism() -> float:
    """Two runs with the same seed and as_of must produce a byte-identical selection."""
    a = stratified_sample(_payments_units(), seed=20260808, as_of="2026-08-08", size=3)
    b = stratified_sample(_payments_units(), seed=20260808, as_of="2026-08-08", size=3)
    return 1.0 if a == b else 0.0


def score_plan_narration_groundedness() -> float:
    """Score the RAW local narrator: every integer it emits must be an engine-produced figure."""
    universe = enrich_universe(seed_universe(), ())
    plan = AnnualPlanner().rank(universe, as_of=date(2026, 8, 8), scope="eval")
    request = narration.build_request(plan)
    raw = LocalGenerationAdapter(Settings(profile="local")).generate(request)
    parsed = narration.parse_narrative(raw.text)
    grounded = parsed is not None and narration.narrative_is_grounded(parsed, request.facts)
    return 1.0 if grounded else 0.0


def score_workpaper_grounding() -> float:
    """Score the RAW local drafter: every cited source must be a retrieved passage."""
    passages = (
        RetrievedPassage(source_id="wp-1", title="Prior workpaper", snippet="breaks not escalated"),
    )
    query = RetrievalQuery(area="payments", text="reconciliation")
    request = fieldwork.build_request(query, passages)
    raw = LocalGenerationAdapter(Settings(profile="local")).generate(request)
    parsed = fieldwork.parse_draft(raw.text)
    grounded = parsed is not None and fieldwork.draft_is_grounded(parsed, passages)
    return 1.0 if grounded else 0.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    settings = Settings(profile="local", audit_path=":memory:")
    audit = LocalAuditAdapter(settings)
    service = TriageService(audit, tracer=LocalNoopTracerAdapter(settings))

    decision_scores: list[float] = []
    for case in cases:
        result = service.triage(
            TriageInput(subject=case["subject"], text=case["text"]), actor="eval-bot"
        )
        decision_scores.append(1.0 if result.severity.value == case["expected_severity"] else 0.0)

    # pii_safety: no raw identifier may survive into any audit record. `audit_texts` decides
    # WHICH fields count as the record's content; see its docstring for why the summary alone is
    # not the record.
    records = audit_texts(audit.log.read_all())
    planted = [case["planted"] for case in cases if case.get("planted")]

    plan_rows = _load_rows(PLAN_ORACLE)
    finding_rows = _load_rows(FINDING_ORACLE)

    results = (
        EvalMetricResult.scored(
            "decision_accuracy", _mean(decision_scores), THRESHOLDS["decision_accuracy"]
        ),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(records, planted), THRESHOLDS["pii_safety"]
        ),
        EvalMetricResult.scored(
            "plan_ranking_accuracy",
            score_plan_ranking(plan_rows),
            THRESHOLDS["plan_ranking_accuracy"],
        ),
        EvalMetricResult.scored(
            "severity_accuracy", score_severity(finding_rows), THRESHOLDS["severity_accuracy"]
        ),
        EvalMetricResult.scored(
            "sample_stratification", score_stratification(), THRESHOLDS["sample_stratification"]
        ),
        EvalMetricResult.scored(
            "sample_determinism", score_determinism(), THRESHOLDS["sample_determinism"]
        ),
        EvalMetricResult.scored(
            "plan_narration_groundedness",
            score_plan_narration_groundedness(),
            THRESHOLDS["plan_narration_groundedness"],
        ),
        EvalMetricResult.scored(
            "workpaper_grounding",
            score_workpaper_grounding(),
            THRESHOLDS["workpaper_grounding"],
        ),
    )
    n = len(cases) + len(plan_rows) + len(finding_rows)
    return EvalReport(dataset=str(dataset), results=results, n_examples=n)


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"AUDIT_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("AUDIT_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / model-quality-gate for internal-audit-lifecycle.",
        )
    )
