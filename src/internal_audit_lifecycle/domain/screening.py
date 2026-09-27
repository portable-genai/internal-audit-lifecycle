"""Rule R1 around one generation call: screen INPUT before, OUTPUT after, audit every refusal.

This service makes exactly two generation calls, the plan narrative (``narration.py``) and the
working-paper draft (``fieldwork.py``), and both run through :class:`ScreenedGeneration` so the
screening shape lives in one place rather than being remembered twice:

1. The PROMPT the model will read is screened INPUT. It is the exact string the generation
   port sends (``GenerationRequest.prompt``; the system instruction is a fixed module constant
   no caller writes), so every caller-controlled field that reaches the model (the plan scope,
   the audit area, each retrieved passage) is screened as it is sent, joined, where an
   injection split across two fields is seen whole. The screened text is what is sent, exactly
   as the verdict hands it back.
2. The model's RAW response is screened OUTPUT before it is parsed, grounded, audited or
   returned. The screened text is what the caller parses, exactly as given: it never falls
   back to the unscreened original.

A refusal in either direction is audited ``Decision.BLOCKED`` before anything else happens, and
so is a guardrail that could not decide (its backend errored or timed out, or the on-prem
placeholder is bound): fail CLOSED, never on the unscreened text. The record carries the action,
the direction and the guardrail's reason, never the refused text. Narration is optional by
design in this service (the engine owns every number, and each caller already has a
deterministic, grounded-by-construction text for a model that cannot answer), so a refusal then
returns ``None`` and the caller uses that fixed text: never a partial or unscreened model answer.

A generation failure that is NOT a guardrail event (the model unreachable, the on-prem
placeholder) degrades the same way it always has, unaudited, because nothing was refused.
"""

from __future__ import annotations

from dataclasses import replace

from ..ports.audit import AuditSinkPort
from ..ports.generation import GenerationPort, GenerationRequest
from ..ports.guardrail import GuardrailPort
from .kernel import AuditEvent, Decision, Direction, Severity, utcnow

__all__ = ["ScreenedGeneration"]


class ScreenedGeneration:
    """One generation port wrapped in the guardrail, with every refusal audited BLOCKED."""

    def __init__(
        self,
        generation: GenerationPort,
        guardrail: GuardrailPort,
        audit: AuditSinkPort,
        *,
        action: str,
    ) -> None:
        self._generation = generation
        self._guardrail = guardrail
        self._audit = audit
        self._action = action

    def generate(
        self, request: GenerationRequest, *, actor: str, severity: Severity | None = None
    ) -> str | None:
        """The screened raw model text, or ``None`` when the caller must use its fixed text.

        ``severity`` is what a BLOCKED record may state: the band the engine already scored
        for the thing being narrated, or ``None`` where nothing was scored.
        """
        prompt = self._screen(request.prompt, Direction.INPUT, actor=actor, severity=severity)
        if prompt is None:
            return None
        try:
            response = self._generation.generate(replace(request, prompt=prompt))
        except Exception:  # noqa: BLE001 - an unreachable model degrades, never crashes a decision
            return None
        return self._screen(response.text, Direction.OUTPUT, actor=actor, severity=severity)

    def _screen(
        self, text: str, direction: Direction, *, actor: str, severity: Severity | None
    ) -> str | None:
        """Screen one text; the text to use from here on, exactly as given, or ``None``."""
        try:
            verdict = self._guardrail.screen(text, direction)
        except Exception as exc:  # noqa: BLE001 - an undecided screen is a refusal (fail closed)
            self._audit_blocked(
                actor, direction, f"guardrail unavailable ({type(exc).__name__})", severity
            )
            return None
        if not verdict.allowed or verdict.sanitized_text is None:
            reason = verdict.reason or f"{direction.value} blocked by guardrail"
            self._audit_blocked(actor, direction, reason, severity)
            return None
        return verdict.sanitized_text

    def _audit_blocked(
        self, actor: str, direction: Direction, reason: str, severity: Severity | None
    ) -> None:
        """Write the BLOCKED record. An audit sink that refuses it propagates: never swallowed."""
        self._audit.record(
            AuditEvent(
                action=self._action,
                actor=actor,
                decision=Decision.BLOCKED,
                severity=severity,
                redacted_summary=f"{self._action} blocked ({direction.value}): {reason}",
                citations=(),
                timestamp=utcnow(),
            )
        )
