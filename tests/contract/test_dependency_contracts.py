"""Frozen contracts for the systems Aud1 consumes, and the control-triad boundary it must hold.

Aud2 is not built yet, so the shape Aud1 expects from it is frozen HERE, against the deterministic
fixture adapter, so a future Aud2 that changes the contract breaks this test rather than Aud1 in
production. The same freezing covers Rgc7 (obligations), Rsk1 (horizon) and Aud3 (the handover
feed). The boundary tests prove Aud1 keeps NO control catalog and NO remediation state of its own.
"""

from __future__ import annotations

from internal_audit_lifecycle.config import build_container
from internal_audit_lifecycle.domain.findings import IssueHandover
from internal_audit_lifecycle.domain.planning import HorizonSignal
from internal_audit_lifecycle.domain.scoping import ControlResult, ObligationRef
from internal_audit_lifecycle.ports import PORT_PROTOCOLS

from tests.conftest import local_settings


def _container():  # type: ignore[no-untyped-def]
    return build_container(local_settings())


# --------------------------------------------------------------------------- #
# Frozen dependency contracts (fixture adapters stand in for the live systems)
# --------------------------------------------------------------------------- #
def test_rgc7_obligation_read_contract() -> None:
    obligations = _container().obligations.obligations_for("payments")
    assert obligations, "the Rgc7 fixture must answer for a seeded area"
    for o in obligations:
        assert isinstance(o, ObligationRef)
        assert o.area == "payments" and o.id and o.citation.source_id.startswith("rgc7://")


def test_aud2_control_result_contract_is_frozen() -> None:
    results = _container().control_results.results_for("payments")
    assert results, "the Aud2 fixture must answer for a seeded area (Aud2 is not built yet)"
    for r in results:
        assert isinstance(r, ControlResult)
        assert r.effectiveness in {"pass", "partial", "fail"}
        assert r.as_of and r.citation.source_id.startswith("aud2://")


def test_rsk1_horizon_signal_contract_is_frozen() -> None:
    signals = _container().horizon.signals()
    assert signals, "the Rsk1 fixture must answer with per-entity horizon signals"
    for s in signals:
        assert isinstance(s, HorizonSignal)
        assert s.signals >= 0 and s.citation.source_id.startswith("rsk1://")


def test_aud3_feed_records_only_approved_handovers() -> None:
    feed = _container().finding_feed
    handover = IssueHandover(
        finding_id="find-x",
        engagement="e",
        area="payments",
        title="t",
        severity="high",
        source_system="Aud1",
        approval_ref="rev-1",
        citations=(),
    )
    ref = feed.emit(handover)
    assert ref and feed.pending() == (handover,)


def test_aud3_feed_refuses_an_unapproved_handover() -> None:
    feed = _container().finding_feed
    handover = IssueHandover(
        finding_id="find-x",
        engagement="e",
        area="payments",
        title="t",
        severity="high",
        source_system="Aud1",
        approval_ref="",  # no approval: emission must be refused
        citations=(),
    )
    try:
        feed.emit(handover)
    except ValueError:
        return
    raise AssertionError("the Aud3 feed must refuse a handover with no approval reference")


# --------------------------------------------------------------------------- #
# The control-triad boundary: no parallel catalog, no remediation state
# --------------------------------------------------------------------------- #
def test_no_control_catalog_store_port_is_registered() -> None:
    """Aud1 READS Rgc7's inventory; it must never register a control-catalog store of its own."""
    forbidden = {"control_catalog", "control_inventory", "controls_store", "control_store"}
    assert not (set(PORT_PROTOCOLS) & forbidden), (
        "Aud1 must not own a control catalog: it reads Rgc7's inventory through the "
        "read-only 'obligations' / 'control_results' ports (the control-triad boundary)."
    )


def test_no_remediation_store_port_is_registered() -> None:
    """Aud1 RAISES findings; the post-finding remediation lifecycle is Aud3's, not Aud1's."""
    forbidden = {"remediation", "capa", "issue_store", "remediation_store", "closure"}
    assert not (set(PORT_PROTOCOLS) & forbidden), (
        "Aud1 must hold no remediation/CAPA state: findings leave via the one-way 'finding_feed' "
        "emit to Aud3 (the control-triad boundary)."
    )
