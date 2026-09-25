"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

This service binds one model port, ``generation``, and two routes call it: ``/v1/plan`` (the
plan narrative) and ``/v1/workpaper`` (the working-paper draft). Both are prose, so both sample
FREE: the request carries no temperature and the Gemini adapter sends none.
"""

from __future__ import annotations

import dataclasses
import sys
from datetime import date
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from internal_audit_lifecycle import config
from internal_audit_lifecycle.adapters.gcp.generation import CloudGenerationAdapter
from internal_audit_lifecycle.adapters.local.generation import LocalGenerationAdapter
from internal_audit_lifecycle.api import app as app_module
from internal_audit_lifecycle.config import LOCAL_STUB_MODEL, Settings
from internal_audit_lifecycle.domain import fieldwork, narration
from internal_audit_lifecycle.domain.fieldwork import (
    RetrievalQuery,
    RetrievedPassage,
    WorkpaperService,
)
from internal_audit_lifecycle.domain.narration import NarratedPlan, PlanNarrationService
from internal_audit_lifecycle.domain.planning import AnnualPlan, AnnualPlanner, seed_universe
from internal_audit_lifecycle.ports.generation import GenerationRequest, GenerationResponse

from tests import REPO_ROOT

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"
_AUDITOR = {"X-Dev-Persona": "auditor"}


def _post(api_client: TestClient, route: str, payload: dict[str, Any]) -> dict[str, str]:
    response = api_client.post(route, json=payload, headers=_AUDITOR)
    assert response.status_code == 200, response.text
    return dict(response.headers)


def _plan(api_client: TestClient) -> dict[str, str]:
    return _post(api_client, "/v1/plan", {"as_of": "2026-08-08"})


def _workpaper(api_client: TestClient) -> dict[str, str]:
    return _post(api_client, "/v1/workpaper", {"area": "payments", "text": "reconciliation"})


def _scope(api_client: TestClient) -> dict[str, str]:
    payload = {"area": "payments", "seed": 20260808, "sample_size": 3, "as_of": "2026-08-08"}
    return _post(api_client, "/v1/scope", payload)


# --- the headers on the real routes ------------------------------------------------------------


def test_a_narrated_plan_names_the_local_stub_that_answered(api_client: TestClient) -> None:
    """Under ``local`` the pill reads the same before and after an answer: one stub, one name."""
    headers = _plan(api_client)
    assert Settings.load().generator_model == LOCAL_STUB_MODEL
    assert headers[ANSWERED_BY] == LOCAL_STUB_MODEL
    assert SEARCH_USED not in headers


def test_a_drafted_workpaper_names_the_local_stub_that_answered(api_client: TestClient) -> None:
    headers = _workpaper(api_client)
    assert headers[ANSWERED_BY] == LOCAL_STUB_MODEL
    assert SEARCH_USED not in headers


def test_a_route_that_calls_no_model_names_none(api_client: TestClient) -> None:
    """Scoping is deterministic end to end: nothing noted, nothing sent, never a guess."""
    headers = _scope(api_client)
    assert ANSWERED_BY not in headers
    assert SEARCH_USED not in headers


class _AnsweringNarrator(PlanNarrationService):
    """The real narrator, plus what a model adapter that searched would note while it called."""

    def narrate(self, plan: AnnualPlan) -> NarratedPlan:
        provenance.note_model("fake-answering-model")
        provenance.note_search()
        return super().narrate(plan)


def test_the_route_names_the_model_that_answered_and_that_it_searched(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "PlanNarrationService", _AnsweringNarrator)
    headers = _plan(api_client)
    # The stand-in noted first, then the real local adapter underneath it: both, in call order.
    assert headers[ANSWERED_BY] == f"fake-answering-model, {LOCAL_STUB_MODEL}"
    assert headers[SEARCH_USED] == "true"
    # The next request is a fresh record: an answer never leaks into a later response.
    monkeypatch.setattr(app_module, "PlanNarrationService", PlanNarrationService)
    later = _scope(api_client)
    assert ANSWERED_BY not in later
    assert SEARCH_USED not in later


# --- the latent false banner: no flag moves generator_model ------------------------------------


def test_generator_model_is_the_setting_the_adapter_reads_and_no_flag_swaps_it() -> None:
    """A flag that moved the pill but not the model that answered.

    A resolver once named ``models.hard_reasoning`` when ``models.use_hard_reasoning`` was set,
    while the managed adapter called ``request.model or models.reasoning`` and never read the
    flag. The pill then named a model that never answered. The flag is gone; a stray one in a
    settings object must change nothing.
    """
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    sources = sorted((REPO_ROOT / "src").rglob("*.py"))
    assert sources, "no source files found: this check would pass over nothing"
    for source in sources:
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source


def test_under_gcp_generator_model_is_the_model_the_gemini_adapter_calls() -> None:
    managed = dataclasses.replace(Settings.load(), profile="gcp")
    assert managed.generator_model == CloudGenerationAdapter._MODEL


# --- the Gemini adapter: notes what it called, samples per request -----------------------------


class _FakeGenAI:
    """Just enough of ``google.genai`` to record what the adapter sends. No SDK is installed."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        recorder = self

        class _Models:
            def generate_content(self, **kwargs: Any) -> Any:
                recorder.calls.append(kwargs)
                return SimpleNamespace(text='{"narrative": "ok"}')

        class _Client:
            def __init__(self) -> None:
                self.models = _Models()

        self.types = ModuleType("google.genai.types")
        # The config is captured as the kwargs it was built from, so an absent key is visible.
        self.types.GenerateContentConfig = lambda **kwargs: dict(kwargs)  # type: ignore[attr-defined]
        self.genai = ModuleType("google.genai")
        self.genai.Client = _Client  # type: ignore[attr-defined]
        self.genai.types = self.types  # type: ignore[attr-defined]
        self.google = ModuleType("google")
        self.google.__path__ = []
        self.google.genai = self.genai  # type: ignore[attr-defined]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "google", self.google)
        monkeypatch.setitem(sys.modules, "google.genai", self.genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", self.types)


@pytest.fixture()
def fake_genai(monkeypatch: pytest.MonkeyPatch) -> _FakeGenAI:
    fake = _FakeGenAI()
    fake.install(monkeypatch)
    return fake


def _gemini() -> CloudGenerationAdapter:
    return CloudGenerationAdapter(dataclasses.replace(Settings.load(), profile="gcp"))


def test_the_gemini_adapter_notes_the_model_it_called(fake_genai: _FakeGenAI) -> None:
    with provenance.scope() as record:
        response = _gemini().generate(GenerationRequest(system="s", prompt="p"))
    assert fake_genai.calls[0]["model"] == CloudGenerationAdapter._MODEL
    assert record.models == [CloudGenerationAdapter._MODEL]
    assert record.search_used is False, "no search tool is attached, so none may be noted"
    assert response.model == CloudGenerationAdapter._MODEL


def test_a_drafting_request_sends_no_temperature_and_a_pinned_one_sends_zero(
    fake_genai: _FakeGenAI,
) -> None:
    passages = (RetrievedPassage(source_id="wp-1", title="t", snippet="s"),)
    drafting = fieldwork.build_request(RetrievalQuery(area="payments", text="x"), passages)
    _gemini().generate(drafting)
    _gemini().generate(GenerationRequest(system="s", prompt="p", temperature=0.0))
    free, pinned = (call["config"] for call in fake_genai.calls)
    assert "temperature" not in free, "a free request must omit temperature, never send 1.0"
    assert pinned["temperature"] == 0.0


def test_the_local_stub_notes_its_own_name() -> None:
    with provenance.scope() as record:
        response = LocalGenerationAdapter(Settings.load()).generate(
            GenerationRequest(system="s", prompt="p")
        )
    assert record.models == [LOCAL_STUB_MODEL]
    assert response.model == LOCAL_STUB_MODEL


# --- sampling per call site --------------------------------------------------------------------


class _Recording:
    """A GenerationPort that records every request and answers through the local stub."""

    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []
        self._stub = LocalGenerationAdapter(Settings.load())

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return self._stub.generate(request)


def test_every_call_site_is_free_because_every_one_writes_prose() -> None:
    """The plan narrative and the working-paper draft are both prose: neither pins sampling.

    Neither output is extracted, classified or scored: the engine owns every number and rank,
    and each draft is checked against the facts or the retrieved sources whatever the model
    samples, then discarded (never re-rolled) if it fails. So no call site pins ``0.0``.
    """
    port = _Recording()
    plan = AnnualPlanner().rank(seed_universe(), as_of=date(2026, 8, 8), scope="annual")
    PlanNarrationService(port).narrate(plan)
    WorkpaperService(port).draft(
        RetrievalQuery(area="payments", text="x"),
        (RetrievedPassage(source_id="wp-1", title="t", snippet="s"),),
    )
    assert [r.response_keys for r in port.requests] == [("narrative",), ("workpaper",)]
    assert [r.temperature for r in port.requests] == [None, None]
    # And the pure builders the eval scores agree with what the services send.
    assert narration.build_request(plan).temperature is None
