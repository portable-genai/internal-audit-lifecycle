"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** An escalated result is ROUTED from inside the tool, in
  the same call that produced it. An agent surface that only returned the flag would be a third
  place an escalation can quietly stop, after the API and the CLI.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with
  no ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.findings import FindingInput, FindingService
from ..domain.models import TriageInput, TriageResult
from ..domain.narration import PlanNarrationService
from ..domain.pii import PII_PATTERNS
from ..domain.planning import AnnualPlanner, enrich_universe, seed_universe
from ..domain.triage_service import TriageService

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "internal-audit-lifecycle-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result is not an API response. The API returns to the authenticated caller the text
    that caller just submitted; a TOOL result goes into a model's context, and P-04 says
    minimise the data that reaches a model. The evidence snippet a caller may legitimately read
    back is therefore masked here, on the way to the agent, using the same pattern pack the
    audit write masks with. Walking the whole structure rather than three named fields means a
    future field cannot arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def triage_case(
    subject: str,
    text: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Triage one case and route it for human review when it escalates.

    Scores the case into a deterministic severity band, writes an already-redacted audit event,
    and, when the band escalates, submits the result to the human-review console (rule R8).

    Args:
      subject: The party or case the description is about.
      text: The free-text case description.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on an outbound review.

    Returns:
      A JSON-safe result dict with every string masked for personal data (P-04: a tool result
      goes into a model's context), plus ``review_ref``: where the escalation WENT. It is empty
      only when the result did not escalate, so a caller can tell a routed escalation from a
      flag nobody read.
    """
    container = _container(settings)
    case = TriageInput(subject=subject, text=text)
    result = TriageService(container.audit, tracer=container.tracer).triage(case, actor=actor)
    review_ref = ""
    if result.requires_human_review:
        review_ref = container.review_router.route(result, maker=actor, tenant=tenant)
    payload = _redacted(to_jsonable(result))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a triage result must serialise to a JSON object")
    # Attached after the redaction pass: it is a routing reference, not narrative text, and
    # masking an identifier would break the caller's ability to look the review up.
    payload["review_ref"] = review_ref
    return payload


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well. Without an anchor a truncation cannot be detected, and the detail
      says so rather than implying a stronger guarantee than the store provides.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


def _route_envelope(
    container: Container,
    *,
    subject: str,
    severity: Any,
    decision: Any,
    summary: str,
    citations: Any,
    maker: str,
    tenant: str,
) -> str:
    """Project a consequential audit result onto the R8 envelope and ROUTE it (rule R8)."""
    envelope = TriageResult(
        subject=subject,
        severity=severity,
        decision=decision,
        summary=summary,
        requires_human_review=True,
        citations=tuple(citations),
    )
    return container.review_router.route(envelope, maker=maker, tenant=tenant)


def draft_annual_plan(
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Rank the audit universe into a risk-based annual plan and route it for sign-off.

    The scores, bands and ranks are the deterministic engine's, over the universe enriched with
    compliance-advisory horizon signals read through the ``horizon`` port; the model only narrates
    the ranked
    plan, and the narrative is discarded unless every figure in it is one the engine produced.
    Approving a plan is consequential, so the result is ROUTED to human review here (rule R8).

    Args:
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on the outbound review.

    Returns:
      A JSON-safe dict with the ranked entries, the grounded narrative and ``review_ref``: where
      the plan escalation WENT.
    """
    from datetime import date

    container = _container(settings)
    universe = enrich_universe(seed_universe(), tuple(container.horizon.signals()))
    plan = AnnualPlanner().rank(universe, as_of=date.today(), scope="annual audit plan")
    note = PlanNarrationService(container.generation).narrate(plan)
    review_ref = _route_envelope(
        container,
        subject=plan.subject,
        severity=plan.severity,
        decision=plan.decision,
        summary=plan.summary,
        citations=plan.citations,
        maker=actor,
        tenant=tenant,
    )
    payload = _redacted(
        {
            "scope": plan.scope,
            "severity": plan.severity.value,
            "entries": [
                {"entity_id": e.entity_id, "score": e.score, "band": e.band.value, "rank": e.rank}
                for e in plan.entries
            ],
            "narrative": note.text,
        }
    )
    if not isinstance(payload, dict):  # pragma: no cover - dict in, dict out
        raise TypeError("a plan payload must be a JSON object")
    payload["review_ref"] = review_ref
    return payload


def write_finding(
    engagement: str,
    area: str,
    title: str,
    impact: int,
    likelihood: int,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Write up a finding with a deterministic severity and route it for lead-auditor sign-off.

    Severity is pure code (impact x likelihood banded by config), never the model's opinion. The
    finding is ROUTED to human review here (rule R8); internal-audit-lifecycle holds no remediation
    state, and the
    finding reaches issue-remediation-capa only after this review is approved.

    Args:
      engagement: The engagement the finding belongs to.
      area: The audited area.
      title: The finding title.
      impact: Impact rating (1-5); clamped into range.
      likelihood: Likelihood rating (1-5); clamped into range.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on the outbound review.

    Returns:
      A JSON-safe dict with the finding, its computed severity and ``review_ref``.
    """
    container = _container(settings)
    finding = FindingService().assess(
        FindingInput(
            engagement=engagement,
            title=title,
            area=area,
            impact=impact,
            likelihood=likelihood,
            evidence=(),
        )
    )
    review_ref = _route_envelope(
        container,
        subject=finding.subject,
        severity=finding.severity,
        decision=finding.decision,
        summary=finding.summary,
        citations=finding.citations,
        maker=actor,
        tenant=tenant,
    )
    payload = _redacted(
        {
            "id": finding.id,
            "engagement": finding.engagement,
            "area": finding.area,
            "title": finding.title,
            "score": finding.score,
            "severity": finding.severity.value,
        }
    )
    if not isinstance(payload, dict):  # pragma: no cover - dict in, dict out
        raise TypeError("a finding payload must be a JSON object")
    payload["review_ref"] = review_ref
    return payload


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (triage_case, verify_audit_trail, draft_annual_plan, write_finding)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path).

    The import is deliberately here rather than at module scope: without it this module, the
    card and every tool would need an agent runtime installed to be imported at all, and the
    offline gate installs none.
    """
    # No ignore comment: the missing-import error for this module is already reported (and
    # ignored) at the TYPE_CHECKING import above, and a second one would be flagged as unused.
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
