"""Nothing redaction removed survives anywhere else in the WORM record (check C3).

The service masked ``redacted_summary`` and then handed the SAME event its citations untouched,
so the identifier the summary no longer carried was persisted verbatim one field away, in a
record that is by design immutable and long-retained. The summary is not the record.

Two rules this suite holds, and they pull in opposite directions, which is why both are written
down:

* every CONTENT field is scanned: the summary, and each citation's locator, title and snippet.
  The locator is built from the case subject and the snippet is cut from the case text, so both
  are raw client text with a structural-looking name.
* the ATTRIBUTION field is not. ``actor`` is the verified principal and is an address by design,
  so a blanket scan over a whole audit row could never go green, and a scan that "fixed" that by
  masking the actor would erase the only column that says who acted.

Scored two ways, as the eval metric is: the shared pack's own rows, plus the planted literals,
which still fire if a pattern row is broken.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from pii_kit import pack_leak

from internal_audit_lifecycle.adapters._review_payload import result_to_review
from internal_audit_lifecycle.adapters.local.audit import LocalAuditAdapter
from internal_audit_lifecycle.domain.models import TriageInput
from internal_audit_lifecycle.domain.pii import PII_PATTERNS
from internal_audit_lifecycle.domain.triage_service import TriageService

from tests.fixtures import sample_cases

_PLANTED = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)


def _content(row: Mapping[str, Any]) -> str:
    """Every content-bearing field of one audit row, as one scannable blob.

    ``actor`` and the structural columns are excluded deliberately: see the module docstring.
    """
    return " ".join(
        (
            str(row.get("redacted_summary", "")),
            json.dumps(row.get("citations", []), sort_keys=True),
        )
    )


@pytest.mark.parametrize(
    "case",
    [sample_cases.PII_CASE, sample_cases.PII_SUBJECT_CASE],
    ids=["identifier-in-text", "identifier-in-subject-and-text"],
)
def test_no_identifier_reaches_the_audit_record(
    triage_service: TriageService, container: Any, case: TriageInput
) -> None:
    triage_service.triage(case, actor=sample_cases.ACTOR)

    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    rows = list(audit.log.read_all())
    assert rows, "the triage path wrote no audit record, so this proves nothing"

    for row in rows:
        blob = _content(row)
        assert not pack_leak(blob, PII_PATTERNS), f"pack row matched in the WORM record: {blob}"
        for token in _PLANTED:
            assert token not in blob, f"planted {token!r} survived into the WORM record: {blob}"


def test_the_actor_is_kept_verbatim_because_it_is_attribution(
    triage_service: TriageService, container: Any
) -> None:
    """The caveat, pinned: the principal is an address and must NOT be masked away."""
    triage_service.triage(sample_cases.PII_CASE, actor=sample_cases.ACTOR)

    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    actors = [str(row.get("actor", "")) for row in audit.log.read_all()]
    assert actors == [sample_cases.ACTOR]


def test_the_whole_review_payload_is_redacted_not_only_its_narrative_fields(
    triage_service: TriageService,
) -> None:
    """Every field that crosses to the console, including the ones with structural names.

    ``subject`` and ``summary`` were masked and ``case_ref`` and ``source_key`` were not, so the
    identifier the payload had just removed from two fields crossed the wire in the two beside
    them. A citation LOCATOR is the same trap one level down. The scan is over the SERIALISED
    payload rather than a chosen list of fields, so a field added later is covered by default.
    """
    result = triage_service.triage(sample_cases.PII_SUBJECT_CASE, actor=sample_cases.ACTOR)
    review = result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)

    blob = json.dumps(
        {
            "subject": review.subject,
            "summary": review.summary,
            "case_ref": review.case_ref,
            "source_key": review.source_key,
            "sod_group": review.sod_group,
            "citations": [
                {"source_id": c.source_id, "title": c.title, "snippet": c.snippet}
                for c in review.citations
            ],
        },
        sort_keys=True,
    )
    assert not pack_leak(blob, PII_PATTERNS), f"pack row matched in the review payload: {blob}"
    for token in _PLANTED:
        assert token not in blob, f"planted {token!r} crossed to the console: {blob}"
