"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from internal_audit_lifecycle.domain.fieldwork import RetrievalQuery
from internal_audit_lifecycle.domain.findings import IssueHandover
from internal_audit_lifecycle.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from internal_audit_lifecycle.domain.models import (
    TriageResult,
)
from internal_audit_lifecycle.ports.generation import GenerationRequest

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="triage",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="Acme Holdings (FICTIONAL): triaged high",
    citations=(Citation(source_id="case:acme", title="Case description", snippet="urgent"),),
)

#: The escalated result every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = TriageResult(
    subject=sample_cases.ESCALATING_CASE.subject,
    severity=Severity.HIGH,
    decision=Decision.ESCALATED,
    summary=f"{sample_cases.ESCALATING_CASE.subject}: triaged high",
    requires_human_review=True,
    citations=(Citation(source_id="case:acme", title="Case description", snippet="urgent"),),
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})

#: The narration request every generation implementation is handed (facts the model may restate).
CANONICAL_GEN_REQUEST = GenerationRequest(
    system="restate the facts",
    prompt="facts:\nentities=4",
    facts=(("entities", "4"),),
    response_keys=("narrative",),
)

#: The read area every read-port implementation is queried for (the seed fixtures answer for it).
CANONICAL_AREA = "payments"

#: The retrieval query the knowledge-base implementation is handed.
CANONICAL_KB_QUERY = RetrievalQuery(area=CANONICAL_AREA, text="reconciliation breaks")

#: The approved-finding handover every finding-feed implementation is handed (rule: approval_ref
#: is present, because a finding is emitted to Aud3 only after a human approved it).
CANONICAL_HANDOVER = IssueHandover(
    finding_id="find-canonical-payments",
    engagement="canonical",
    area=CANONICAL_AREA,
    title="Reconciliation breaks not escalated",
    severity="high",
    source_system="Aud1",
    approval_ref="rev-canonical-1",
    citations=(("wp-2025-pay-01", "Prior-year payments workpaper"),),
)


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _generation_invoke(adapter: Any) -> Any:
    return adapter.generate(CANONICAL_GEN_REQUEST)


def _generation_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "text", ""))


def _obligations_invoke(adapter: Any) -> Any:
    return adapter.obligations_for(CANONICAL_AREA)


def _control_results_invoke(adapter: Any) -> Any:
    return adapter.results_for(CANONICAL_AREA)


def _horizon_invoke(adapter: Any) -> Any:
    return adapter.signals()


def _knowledge_base_invoke(adapter: Any) -> Any:
    return adapter.search(CANONICAL_KB_QUERY)


def _nonempty(_adapter: Any, result: Any) -> bool:
    return bool(result)


def _finding_feed_invoke(adapter: Any) -> Any:
    return adapter.emit(CANONICAL_HANDOVER)


def _finding_feed_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.pending()) == 1


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated result to human review",
    ),
    "generation": PortCase(
        invoke=_generation_invoke,
        answered=_generation_answered,
        # The lazy `google.genai` import is the first thing the managed narrator does.
        managed_refusal=(ImportError,),
        detail="narrate the engine facts as text",
    ),
    "obligations": PortCase(
        invoke=_obligations_invoke,
        answered=_nonempty,
        # No Rgc7 endpoint configured offline, so the managed adapter refuses before reaching out.
        managed_refusal=(RuntimeError,),
        detail="read the obligations Rgc7 holds for an area",
    ),
    "control_results": PortCase(
        invoke=_control_results_invoke,
        answered=_nonempty,
        # No Aud2 endpoint configured offline, so the managed adapter refuses.
        managed_refusal=(RuntimeError,),
        detail="read Aud2's control-effectiveness results for an area",
    ),
    "horizon": PortCase(
        invoke=_horizon_invoke,
        answered=_nonempty,
        # No Rsk1 endpoint configured offline, so the managed adapter refuses.
        managed_refusal=(RuntimeError,),
        detail="read Rsk1's horizon signal counts",
    ),
    "knowledge_base": PortCase(
        invoke=_knowledge_base_invoke,
        answered=_nonempty,
        # No retrieval endpoint configured offline, so the managed adapter refuses.
        managed_refusal=(RuntimeError,),
        detail="retrieve grounding passages for a working paper",
    ),
    "finding_feed": PortCase(
        invoke=_finding_feed_invoke,
        answered=_finding_feed_answered,
        # No Aud3 endpoint configured offline, so the managed adapter refuses.
        managed_refusal=(RuntimeError,),
        detail="emit one approved finding to Aud3",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches Hrz4 over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
