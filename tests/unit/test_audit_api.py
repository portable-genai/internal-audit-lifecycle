"""API tests for the four audit-lifecycle endpoints: R8 routing, grounding and the tenant boundary.

Identity is the verified persona resolved server-side (the ``X-Dev-Persona`` header under the
deliberate local profile); the ``auditor`` persona owns the ``demo-bank`` estate and the
``other-tenant`` persona is refused with 403, never 404.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _auditor() -> dict[str, str]:
    return {"X-Dev-Persona": "auditor"}


def test_plan_ranks_routes_and_grounds(api_client: TestClient) -> None:
    resp = api_client.post("/v1/plan", json={"as_of": "2026-08-08"}, headers=_auditor())
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_human_review"] is True
    assert body["review_ref"], "rule R8: the plan must be routed, not merely flagged"
    ranks = {e["entity_id"]: e for e in body["entries"]}
    assert ranks["ent-payments"]["score"] == 100 and ranks["ent-payments"]["rank"] == 1
    assert body["severity"] == "critical"
    # The narrative restates only engine figures; the local narrator is grounded by construction.
    assert body["narrative"]


def test_scope_reads_dependencies_and_samples_deterministically(api_client: TestClient) -> None:
    payload = {"area": "payments", "seed": 20260808, "sample_size": 3, "as_of": "2026-08-08"}
    a = api_client.post("/v1/scope", json=payload, headers=_auditor()).json()
    b = api_client.post("/v1/scope", json=payload, headers=_auditor()).json()
    assert a == b, "the same seed and as_of must produce an identical sample"
    assert a["failing_controls"] == ["ctrl-pay-recon", "ctrl-pay-screening"]
    assert a["sample_size"] == 3
    assert {o["id"] for o in a["obligations"]} == {"obl-pay-settlement", "obl-pay-sanctions"}


def test_workpaper_drafts_when_grounded_and_declines_when_empty(api_client: TestClient) -> None:
    drafted = api_client.post(
        "/v1/workpaper", json={"area": "payments", "text": "reconciliation"}, headers=_auditor()
    ).json()
    assert drafted["drafted"] is True and drafted["grounded"] is True
    assert drafted["citations"], "a drafted working paper cites its retrieved evidence"

    empty = api_client.post(
        "/v1/workpaper", json={"area": "no-such-area", "text": "x"}, headers=_auditor()
    ).json()
    assert empty["drafted"] is False and empty["text"] == ""


def test_finding_severity_is_deterministic_and_routed(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/finding",
        json={"engagement": "e", "area": "payments", "title": "t", "impact": 5, "likelihood": 5},
        headers=_auditor(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "critical" and body["score"] == 25
    assert body["review_ref"], "rule R8: a finding must be routed for sign-off"


def test_finding_handover_requires_approval_and_emits(api_client: TestClient) -> None:
    base = {"engagement": "e", "area": "payments", "title": "t", "impact": 4, "likelihood": 4}
    missing = api_client.post(
        "/v1/finding/handover", json={**base, "approval_ref": ""}, headers=_auditor()
    )
    assert missing.status_code == 400, "a handover with no approval reference must be refused"

    ok = api_client.post(
        "/v1/finding/handover", json={**base, "approval_ref": "rev-42"}, headers=_auditor()
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["approval_ref"] == "rev-42" and body["source_system"] == "internal-audit-lifecycle"
    assert body["feed_ref"]


def test_cross_tenant_access_is_403_not_404(api_client: TestClient) -> None:
    resp = api_client.post("/v1/plan", json={}, headers={"X-Dev-Persona": "other-tenant"})
    assert resp.status_code == 403, (
        "a verified principal from another tenant is refused, not hidden"
    )
