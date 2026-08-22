"""Local GenerationPort: a deterministic, SDK-free narrator for the offline profile.

It stands in for a managed model in the gate, the tests and the demo. It never decides anything:
it restates the engine-owned facts it is handed as a short JSON payload keyed by the request's
first response key, so its output is grounded BY CONSTRUCTION and the whole offline pipeline
(including the narration and working-paper paths) runs with no network and no cloud SDK.

Two grounding shapes, chosen by the requested response key, because the two consuming services
enforce different grounding:

* a working paper (``response_keys == ("workpaper",)``) must cite ONLY retrieved source ids, so
  the draft cites each fact KEY (the passage source id) in square brackets;
* a narrative or note restates only engine NUMBERS, so it emits the fact VALUES and never the
  keys (a key like ``rank_1_score`` carries a stray digit that would read as an ungrounded figure).

A silent empty return would let a producer ship the narration seam unwired, so this always
produces a real, inspectable payload.
"""

from __future__ import annotations

import json

from ...config import Settings
from ...ports.generation import GenerationRequest, GenerationResponse


class LocalGenerationAdapter:
    """Restate the request's engine facts as a deterministic JSON payload (no model, no network)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        key = request.response_keys[0] if request.response_keys else "note"
        if key == "workpaper":
            # Cite each retrieved source id (the fact key) in brackets: grounded by construction.
            cited = "; ".join(f"[{source_id}] evidence restated" for source_id, _ in request.facts)
            text = f"Working paper: {cited}." if cited else "Working paper: no evidence."
        else:
            # Restate the engine figures (the fact values), never the keys.
            values = ", ".join(value for _key, value in request.facts)
            text = f"Restated figures: {values}." if values else "Restated figures: none."
        return GenerationResponse(text=json.dumps({key: text}), model="local-deterministic")
