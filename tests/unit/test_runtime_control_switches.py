"""Review routing has a switch, default on, and every caller says what happened to a hand-off.

The fleet's runtime-control contract (2026-09-24). Review routing is the one cheap runtime
control this service has: ``AUDIT_REVIEW_ROUTING`` is read in three states; off binds a
disabled router and says so at startup; on under the managed profile refuses to boot without a
console; and the API (triage, plan, finding), the agent tools and the CLI report
``review_routing`` rather than failing an already-assessed result when the console is
unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from internal_audit_lifecycle.adapters.controls import (
    DisabledReviewRouter,
    RecordingReviewRouter,
    ReviewRouting,
)
from internal_audit_lifecycle.agent import tools
from internal_audit_lifecycle.api import app as api_module
from internal_audit_lifecycle.api.app import app
from internal_audit_lifecycle.cli.main import main as cli_main
from internal_audit_lifecycle.config import (
    REVIEW_ROUTING_ENV,
    Container,
    ControlSwitches,
    ProfileChoice,
    Settings,
    build_container,
    warn_switched_off,
)
from internal_audit_lifecycle.domain.models import TriageInput, TriageResult
from internal_audit_lifecycle.domain.triage_service import TriageService
from internal_audit_lifecycle.envread import ConfiguredEmptyError

_LOOPBACK = ("127.0.0.1", 50000)
_ESCALATING = {"subject": "Acme Holdings (FICTIONAL)", "text": "urgent data breach"}
_ROUTINE = {"subject": "Acme Holdings (FICTIONAL)", "text": "routine note"}
_AUDITOR = {"X-Dev-Persona": "auditor"}
_FINDING = {"engagement": "e", "area": "payments", "title": "t", "impact": 5, "likelihood": 5}
_LOCAL_ROUTE = "internal_audit_lifecycle.adapters.local.review_router.LocalReviewRouter.route"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(REVIEW_ROUTING_ENV, raising=False)
    monkeypatch.delenv("HUMAN_REVIEW_URL", raising=False)
    # The API caches its container for the process; each test here states its own posture.
    api_module._container.cache_clear()
    yield
    api_module._container.cache_clear()


def _result(text: str = "urgent data breach") -> TriageResult:
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = TriageService(container.audit, tracer=container.tracer)
    return service.triage(
        TriageInput(subject="Acme Holdings (FICTIONAL)", text=text), actor="auditor@bank.example"
    )


def _gcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "internal_audit_lifecycle.config.resolve_profile",
        lambda environ=None: ProfileChoice("gcp", True),
    )


# --------------------------------------------------------------------------- #
# Three states
# --------------------------------------------------------------------------- #
def test_routing_is_on_when_nothing_is_said() -> None:
    assert Settings.load().controls == ControlSwitches(review_routing=True)


def test_routing_switched_off_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert Settings.load().controls.switched_off() == (REVIEW_ROUTING_ENV,)


def test_an_emptied_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "")
    with pytest.raises(ConfiguredEmptyError, match=REVIEW_ROUTING_ENV):
        Settings.load()


def test_an_unrecognised_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "sometimes")
    with pytest.raises(ValueError, match=REVIEW_ROUTING_ENV):
        Settings.load()


# --------------------------------------------------------------------------- #
# Off binds the disabled router, and says so once
# --------------------------------------------------------------------------- #
def test_off_binds_the_disabled_router() -> None:
    settings = Settings(profile="local", controls=ControlSwitches(review_routing=False))
    assert isinstance(Container(settings).review_router, DisabledReviewRouter)


def test_on_binds_the_profile_router() -> None:
    settings = Settings(profile="local")
    assert not isinstance(Container(settings).review_router, DisabledReviewRouter)


def test_the_off_posture_is_logged_once_however_many_containers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_switched_off.cache_clear()
    settings = Settings(profile="local", controls=ControlSwitches(review_routing=False))
    with caplog.at_level(logging.WARNING, logger="internal_audit_lifecycle.config"):
        for _ in range(3):
            build_container(settings)
    assert caplog.text.count(REVIEW_ROUTING_ENV) == 1


# --------------------------------------------------------------------------- #
# On has to work: checked at boot under the managed profile
# --------------------------------------------------------------------------- #
def test_routing_on_under_gcp_without_a_console_refuses_at_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _gcp(monkeypatch)
    with pytest.raises(ConfiguredEmptyError, match="HUMAN_REVIEW_URL"):
        Settings.load()


def test_routing_stated_off_under_gcp_needs_no_console(monkeypatch: pytest.MonkeyPatch) -> None:
    _gcp(monkeypatch)
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "false")
    assert Settings.load().controls.review_routing is False


def test_routing_on_under_gcp_with_a_console_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _gcp(monkeypatch)
    monkeypatch.setenv("HUMAN_REVIEW_URL", "https://review.example.test")
    assert Settings.load().review_url == "https://review.example.test"


# --------------------------------------------------------------------------- #
# The four routing outcomes
# --------------------------------------------------------------------------- #
class _Accepting:
    def route(self, result: TriageResult, *, maker: str, tenant: str = "") -> str:
        return "review-1"


class _Refusing:
    def route(self, result: TriageResult, *, maker: str, tenant: str = "") -> str:
        raise ConnectionError("console unreachable")


def test_routing_outcomes_take_each_of_their_four_values() -> None:
    result = _result()
    assert result.requires_human_review

    not_required = RecordingReviewRouter(_Accepting())
    assert not_required.route(_result("routine note"), maker="m") == ""
    assert not_required.outcome is ReviewRouting.NOT_REQUIRED

    routed = RecordingReviewRouter(_Accepting())
    assert routed.route(result, maker="m") == "review-1"
    assert routed.outcome is ReviewRouting.ROUTED

    off = RecordingReviewRouter(DisabledReviewRouter(Settings()))
    assert off.route(result, maker="m") == ""
    assert off.outcome is ReviewRouting.OFF


def test_a_failed_hand_off_is_reported_and_logged_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed = RecordingReviewRouter(_Refusing())
    with caplog.at_level(logging.WARNING, logger="internal_audit_lifecycle.adapters.controls"):
        assert failed.route(_result(), maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED
    assert "ConnectionError" in caplog.text


# --------------------------------------------------------------------------- #
# Every caller reports it: the API routes, the agent tools, the CLI
# --------------------------------------------------------------------------- #
def _post(path: str, body: dict[str, object]) -> dict[str, object]:
    response = TestClient(app, client=_LOOPBACK).post(path, json=body, headers=_AUDITOR)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_api_reports_routed_and_not_required_triage() -> None:
    routed = _post("/v1/triage", _ESCALATING)
    assert routed["review_routing"] == "routed"
    assert routed["review_ref"]
    routine = _post("/v1/triage", _ROUTINE)
    assert routine["review_routing"] == "not_required"
    assert routine["review_ref"] == ""


@pytest.mark.parametrize(
    ("path", "body"),
    [("/v1/triage", _ESCALATING), ("/v1/plan", {"as_of": "2026-08-08"}), ("/v1/finding", _FINDING)],
)
def test_every_routing_route_reports_routing_off(
    monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, object]
) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    reply = _post(path, body)
    assert reply["review_routing"] == "off"
    assert reply["review_ref"] == ""


@pytest.mark.parametrize(
    ("path", "body"),
    [("/v1/triage", _ESCALATING), ("/v1/plan", {"as_of": "2026-08-08"}), ("/v1/finding", _FINDING)],
)
def test_every_routing_route_reports_a_failed_hand_off_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, object]
) -> None:
    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    reply = _post(path, body)
    assert reply["review_routing"] == "failed"
    assert reply["review_ref"] == ""


def test_the_agent_tools_report_the_hand_off(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tools.triage_case(**_ESCALATING)["review_routing"] == "routed"
    assert tools.draft_annual_plan()["review_routing"] == "routed"
    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    finding = tools.write_finding("e", "payments", "t", 5, 5)
    assert finding["review_routing"] == "failed"
    assert finding["review_ref"] == ""


def test_the_cli_reports_the_hand_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert cli_main(["finding", "e", "payments", "t"]) == 0
    assert "human review hand-off : off" in capsys.readouterr().out
