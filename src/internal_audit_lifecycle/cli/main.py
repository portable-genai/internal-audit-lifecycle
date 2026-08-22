"""Minimal stdlib CLI: triage a case, or verify the audit chain (argparse, no extra deps)."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.findings import FindingInput, FindingService
from ..domain.models import TriageInput, TriageResult
from ..domain.planning import AnnualPlanner, enrich_universe, seed_universe
from ..domain.triage_service import TriageService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="internal_audit_lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)

    triage_cmd = sub.add_parser("triage", help="Triage a single case.")
    triage_cmd.add_argument("subject")
    triage_cmd.add_argument("text")
    triage_cmd.add_argument("--actor", default="cli-user@bank.example")
    triage_cmd.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    plan_cmd = sub.add_parser("plan", help="Rank the audit universe into a risk-based annual plan.")
    plan_cmd.add_argument("--actor", default="cli-user@bank.example")
    plan_cmd.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    finding_cmd = sub.add_parser("finding", help="Write up a finding and route it for sign-off.")
    finding_cmd.add_argument("engagement")
    finding_cmd.add_argument("area")
    finding_cmd.add_argument("title")
    finding_cmd.add_argument("--impact", type=int, default=4)
    finding_cmd.add_argument("--likelihood", type=int, default=4)
    finding_cmd.add_argument("--actor", default="cli-user@bank.example")
    finding_cmd.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="internal-audit-lifecycle")

    if args.command == "triage":
        service = TriageService(container.audit, tracer=container.tracer)
        result = service.triage(TriageInput(subject=args.subject, text=args.text), actor=args.actor)
        print(f"{result.subject}: {result.severity.value} ({result.decision.value})")
        print(f"  requires_human_review: {result.requires_human_review}")
        if result.requires_human_review:
            # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
            # only printed the flag would be a second place for an escalation to stop.
            ref = container.review_router.route(result, maker=args.actor, tenant=args.tenant)
            print(f"  routed to human review: {ref}")
        return 0

    if args.command == "plan":
        universe = enrich_universe(seed_universe(), tuple(container.horizon.signals()))
        plan = AnnualPlanner().rank(universe, as_of=date.today(), scope="annual audit plan")
        for entry in plan.entries:
            print(f"  #{entry.rank} {entry.entity_id}: {entry.score} ({entry.band.value})")
        # Rule R8: approving an annual plan is consequential, so route it, never merely print it.
        ref = container.review_router.route(_envelope(plan), maker=args.actor, tenant=args.tenant)
        print(f"  routed to human review: {ref}")
        return 0

    if args.command == "finding":
        finding = FindingService().assess(
            FindingInput(
                engagement=args.engagement,
                title=args.title,
                area=args.area,
                impact=args.impact,
                likelihood=args.likelihood,
                evidence=(),
            )
        )
        print(f"{finding.id}: {finding.severity.value} (score {finding.score})")
        ref = container.review_router.route(
            _envelope(finding), maker=args.actor, tenant=args.tenant
        )
        print(f"  routed to human review: {ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


def _envelope(result: object) -> TriageResult:
    """Project a consequential audit result onto the shared R8 review envelope."""
    return TriageResult(
        subject=result.subject,  # type: ignore[attr-defined]
        severity=result.severity,  # type: ignore[attr-defined]
        decision=result.decision,  # type: ignore[attr-defined]
        summary=result.summary,  # type: ignore[attr-defined]
        requires_human_review=True,
        citations=tuple(getattr(result, "citations", ())),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
