"""The plan-narrative narration service: the model narrates the engine's numbers, never makes them.

Given an :class:`~.planning.AnnualPlan` (already ranked by the deterministic engine), this asks
the generation port for a short planning narrative, then holds it to two hard rules before it is
allowed out:

* **Schema validation, discard on failure.** The model must return JSON with the requested keys;
  malformed output is discarded, not repaired.
* **Groundedness, discard on failure.** Every integer in the narrative must be one the engine
  produced (the ranked scores and the entity count). A narrative that invents a figure is
  discarded and a deterministic, grounded-by-construction narrative is used instead.

The request-building, parsing and grounding checks are module-level pure functions so the eval
scores the RAW model output through the same contract the service enforces. Pure stdlib: the
model is reached only through the injected port.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..ports.generation import GenerationPort, GenerationRequest
from .planning import AnnualPlan

__all__ = [
    "NarratedPlan",
    "PlanNarrationService",
    "build_request",
    "fallback_text",
    "grounded_integers",
    "narrative_is_grounded",
    "parse_narrative",
]

_INT = re.compile(r"-?\d+")

_SYSTEM = (
    "You are an internal-audit planning assistant. You restate the ranked audit plan you are "
    "given as a short narrative. You never invent a number: use only the figures in the facts "
    "block."
)


@dataclass(frozen=True, slots=True)
class NarratedPlan:
    """A planning narrative plus how it was produced."""

    text: str
    model_authored: bool
    grounded: bool


def _facts(plan: AnnualPlan) -> tuple[tuple[str, str], ...]:
    """The engine-owned figures the narrative may cite, and nothing else grounds it."""
    facts: list[tuple[str, str]] = [("entities", str(len(plan.entries)))]
    for entry in plan.entries[:3]:
        facts.append((f"rank_{entry.rank}_score", str(entry.score)))
    return tuple(facts)


def grounded_integers(facts: tuple[tuple[str, str], ...]) -> set[str]:
    """Every integer token that appears in the engine-owned facts (the grounded number set)."""
    allowed: set[str] = set()
    for _key, value in facts:
        allowed.update(_INT.findall(value))
    return allowed


def narrative_is_grounded(text: str, facts: tuple[tuple[str, str], ...]) -> bool:
    """True when every integer in ``text`` is one the engine facts contain."""
    allowed = grounded_integers(facts)
    return all(token in allowed for token in _INT.findall(text))


def build_request(plan: AnnualPlan) -> GenerationRequest:
    """The exact narration request the service sends, exposed so the eval scores the same path."""
    facts = _facts(plan)
    block = "\n".join(f"{key}={value}" for key, value in facts)
    prompt = (
        f"Scope: {plan.scope}\n"
        f"Facts (use ONLY these numbers):\n{block}\n"
        'Return JSON of the form {"narrative": "<one sentence>"}.'
    )
    return GenerationRequest(
        system=_SYSTEM, prompt=prompt, facts=facts, response_keys=("narrative",)
    )


def parse_narrative(text: str) -> str | None:
    """Parse the model's raw text into the ``narrative`` string, or ``None`` if invalid."""
    try:
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    narrative = parsed.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        return None
    return narrative.strip()


def fallback_text(facts: tuple[tuple[str, str], ...]) -> str:
    """A deterministic, grounded-by-construction narrative built purely from the engine facts."""
    values = dict(facts)
    top = values.get("rank_1_score", "0")
    return (
        f"The risk-based plan ranks {values.get('entities', '0')} entities; the highest-priority "
        f"entity scores {top}. The lead auditor reviews and signs off the plan."
    )


class PlanNarrationService:
    """Draft a grounded planning narrative for a ranked annual plan."""

    def __init__(self, generation: GenerationPort) -> None:
        self._generation = generation

    def narrate(self, plan: AnnualPlan) -> NarratedPlan:
        request = build_request(plan)
        try:
            response = self._generation.generate(request)
        except Exception:  # noqa: BLE001 - a narration failure degrades, never crashes a decision
            return NarratedPlan(
                text=fallback_text(request.facts), model_authored=False, grounded=True
            )

        narrative = parse_narrative(response.text)
        if narrative is None or not narrative_is_grounded(narrative, request.facts):
            return NarratedPlan(
                text=fallback_text(request.facts), model_authored=False, grounded=True
            )
        return NarratedPlan(text=narrative, model_authored=True, grounded=True)
