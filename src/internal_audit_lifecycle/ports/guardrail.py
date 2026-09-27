"""GuardrailPort: the boundary that screens a generation call in both directions (rule R1).

Rule R1 is the reason this port exists: this service binds ``agent-guardrail-gateway`` as a
mandatory dependency (``COMPLIANCE.md``), so every prompt built for the narration model is
screened INPUT before it reaches the model, and every raw model response is screened OUTPUT
after it is produced and BEFORE it is parsed, grounded, audited or handed back to a caller.
``domain/narration.py`` (:class:`~..domain.narration.PlanNarrationService`) and
``domain/fieldwork.py`` (:class:`~..domain.fieldwork.WorkpaperService`) call
:meth:`GuardrailPort.screen` around their one generation call in exactly that shape.

The domain stays pure. This port names the screen; the adapters (not this module) depend on the
managed guardrail service (Model Armor) or a local heuristic stand-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.kernel import Direction, GuardrailVerdict


@runtime_checkable
class GuardrailPort(Protocol):
    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        """Screen inbound prompt or outbound response text; may sanitise it.

        Never raises on a policy match: a block is reported as ``GuardrailVerdict(allowed=False,
        ...)`` so the caller can audit the attempt before deciding how to fail. An allowed verdict
        carries ``sanitized_text``, the text the caller uses from then on EXACTLY as given (the
        input unchanged when nothing was redacted, possibly empty when everything was); the
        caller never falls back to the unscreened original.

        Raising is reserved for the adapter being unable to decide at all: its backend errored
        or timed out, no template is configured, or the on-prem placeholder is bound. The domain
        treats every such raise as a refusal (fail closed) and audits it BLOCKED. Narration is
        optional by design in this service, so the refusal degrades to the deterministic,
        grounded-by-construction text rather than failing the decision it narrates.
        """
        ...
