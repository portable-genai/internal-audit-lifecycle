"""Slice 3: fieldwork and working-paper drafting (grounded retrieval, model narrates only).

The pipeline order cribs ``credit-memo-drafting``'s memo service: redact the input, retrieve
grounding passages from the workpaper / prior-audit corpus (the ``knowledge_base`` port), let the
model draft a working paper that cites ONLY the retrieved passages, and validate that citation
grounding, discarding the draft on failure. The hard rule is the same one that service enforces:
**empty retrieval means no draft.** A working paper with nothing to ground against is not
produced; the auditor is told the corpus had nothing, never handed an ungrounded narrative.

The request-building, parsing and grounding checks are module-level pure functions so the eval
can score the RAW model output through the same contract the service enforces (a grounding metric
that watched only the already-filtered service output could never go red). Pure stdlib: the model
and the corpus are reached only through injected ports.

Rule R1: the drafting prompt (the audit area and every retrieved passage, as sent) is screened
INPUT before the call and the raw response OUTPUT after it, before either is parsed or trusted
(:mod:`.screening`). A refusal in either direction, or a guardrail that cannot decide, is audited
``Decision.BLOCKED`` and the draft is the deterministic fallback below: never text the guardrail
refused, and never a partial model draft.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..ports.audit import AuditSinkPort
from ..ports.generation import GenerationPort, GenerationRequest
from ..ports.guardrail import GuardrailPort
from .kernel import Citation
from .screening import ScreenedGeneration

__all__ = [
    "RetrievalQuery",
    "RetrievedPassage",
    "Workpaper",
    "WorkpaperService",
    "build_request",
    "cited_sources",
    "draft_is_grounded",
    "fallback_text",
    "parse_draft",
]

_SYSTEM = (
    "You are an internal-audit assistant. You draft a concise working-paper note that restates "
    "ONLY the retrieved evidence you are given. You never introduce a fact or a source that is "
    "not in the evidence block, and you cite every claim by its source id."
)

_SOURCE_TOKEN = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    """A grounding query against the workpaper / prior-audit corpus (knowledge-base port)."""

    area: str
    text: str
    limit: int = 5


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """One ranked passage retrieved for grounding (the ``knowledge_base`` port return)."""

    source_id: str
    title: str
    snippet: str


@dataclass(frozen=True, slots=True)
class Workpaper:
    """A drafted working paper, or an explicit "not drafted" when the corpus had nothing.

    ``drafted`` is False exactly when retrieval was empty: the auditor sees that the corpus
    returned no evidence rather than an ungrounded narrative. ``model_authored`` records whether
    the text came from the model (grounded and kept) or the deterministic fallback.
    """

    area: str
    drafted: bool
    text: str
    model_authored: bool
    grounded: bool
    citations: tuple[Citation, ...]


def cited_sources(text: str) -> set[str]:
    """Every ``[source-id]`` token a draft cites."""
    return set(_SOURCE_TOKEN.findall(text))


def draft_is_grounded(text: str, passages: tuple[RetrievedPassage, ...]) -> bool:
    """True when the draft cites at least one source and every citation is a retrieved one."""
    retrieved = {p.source_id for p in passages}
    cited = cited_sources(text)
    return bool(cited) and cited.issubset(retrieved)


def build_request(
    query: RetrievalQuery, passages: tuple[RetrievedPassage, ...]
) -> GenerationRequest:
    """The exact drafting request, exposed so the eval scores the same contract the service does."""
    block = "\n".join(f"[{p.source_id}] {p.title}: {p.snippet}" for p in passages)
    facts = tuple((p.source_id, p.snippet) for p in passages)
    prompt = (
        f"Audit area: {query.area}\n"
        f"Retrieved evidence (cite ONLY these source ids, in square brackets):\n{block}\n"
        'Return JSON of the form {"workpaper": "<two sentences with [source-id] citations>"}.'
    )
    # Sampling stays FREE (no temperature sent): this drafts prose. The citation check below
    # holds whatever the model samples, and a draft that fails it is discarded, not re-rolled.
    return GenerationRequest(
        system=_SYSTEM, prompt=prompt, facts=facts, response_keys=("workpaper",), temperature=None
    )


def parse_draft(text: str) -> str | None:
    """Parse the model's raw text into the ``workpaper`` string, or ``None`` if invalid."""
    try:
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    draft = parsed.get("workpaper")
    if not isinstance(draft, str) or not draft.strip():
        return None
    return draft.strip()


def fallback_text(passages: tuple[RetrievedPassage, ...]) -> str:
    """A deterministic, grounded-by-construction draft built purely from retrieved passages."""
    lines = [f"{p.title} [{p.source_id}]: {p.snippet}" for p in passages]
    return "Evidence reviewed: " + "; ".join(lines) + "."


def _citations(passages: tuple[RetrievedPassage, ...]) -> tuple[Citation, ...]:
    return tuple(
        Citation(source_id=p.source_id, title=p.title, snippet=p.snippet) for p in passages
    )


class WorkpaperService:
    """Draft a grounded working paper, or refuse to draft when retrieval is empty."""

    #: The audit action a guardrail refusal of this call is recorded under.
    ACTION = "workpaper_draft"

    def __init__(
        self, generation: GenerationPort, guardrail: GuardrailPort, audit: AuditSinkPort
    ) -> None:
        self._model = ScreenedGeneration(generation, guardrail, audit, action=self.ACTION)

    def draft(
        self, query: RetrievalQuery, passages: tuple[RetrievedPassage, ...], *, actor: str
    ) -> Workpaper:
        if not passages:
            # Empty retrieval means NO draft. Never an ungrounded narrative.
            return Workpaper(
                area=query.area,
                drafted=False,
                text="",
                model_authored=False,
                grounded=False,
                citations=(),
            )

        request = build_request(query, passages)
        citations = _citations(passages)
        fallback = Workpaper(
            area=query.area,
            drafted=True,
            text=fallback_text(passages),
            model_authored=False,
            grounded=True,
            citations=citations,
        )
        # Rule R1: screened both ways, a refusal audited BLOCKED; None means use the fallback.
        # Nothing here was scored, so a BLOCKED record states no severity.
        raw = self._model.generate(request, actor=actor)
        if raw is None:
            return fallback
        draft = parse_draft(raw)
        if draft is None or not draft_is_grounded(draft, passages):
            # Schema-invalid or ungrounded: discard the model output, never repair it.
            return fallback
        return Workpaper(
            area=query.area,
            drafted=True,
            text=draft,
            model_authored=True,
            grounded=True,
            citations=citations,
        )
