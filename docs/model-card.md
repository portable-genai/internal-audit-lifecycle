# Model card: Internal Audit Lifecycle Copilot (`internal-audit-lifecycle`)

This is a STARTER model card. It records the model boundary as built and the controls that must be
completed before a managed deployment. The deterministic engines are the system of record; the
model is a bounded, replaceable component that writes two pieces of prose and nothing else.

## What the model does, and does not do

- **Does**: write the **plan narrative**, one sentence restating an `AnnualPlan` the engine has
  ALREADY ranked (`domain/narration.py:build_request`), and the **working-paper draft**, two
  sentences restating passages the `knowledge_base` port has ALREADY retrieved
  (`domain/fieldwork.py:build_request`). Both are asked for as JSON.
- **Does NOT**: produce any plan score, band or rank, any sample selection, any finding severity,
  or any escalation decision. Scores and bands come from `AnnualPlanner` in `domain/planning.py`,
  the sample from `stratified_sample` in `domain/scoping.py`, the severity from `FindingService`
  in `domain/findings.py`, and the `issue-remediation-capa` handover gate from an `human-review-console` approval reference the surface
  checks. With the local stub generation adapter bound, every consequential field is identical, so
  a model change cannot move a figure.

## Boundary and validation

- The model is reachable through exactly one port, `ports/generation.py`. There is no second model
  seam in the repo, and no embeddings or retrieval model of its own: retrieval is a read through
  `KnowledgeBaseReadPort`.
- Each reply is held to two hard rules before it is allowed out. **Schema validation**, so output
  that is not JSON carrying the requested key is discarded rather than repaired
  (`parse_narrative`, `parse_draft`). **Grounding**, enforced per path because the two paths ground
  against different things: every integer in a plan narrative must be one the engine produced
  (`grounded_integers`, `narrative_is_grounded`), and every `[source-id]` in a working paper must
  be a retrieved passage, with at least one cited (`cited_sources`, `draft_is_grounded`).
- When a reply is discarded, `fallback_text` builds a deterministic text purely from the engine
  facts or the retrieved passages, so a surface always has a grounded sentence and never a
  hallucinated one. A model call that RAISES lands in the same fallback: a narration failure
  degrades, it never crashes a decision. Every result reports `model_authored`, so the eval and
  the demo can tell the two paths apart.
- **Empty retrieval means no draft.** `WorkpaperService.draft` returns `drafted=False` with empty
  text when the corpus returns nothing, rather than asking the model to write something. This is
  the one case where the answer is a refusal instead of a fallback.
- The parsing and grounding checks are module-level pure functions rather than private methods,
  deliberately: the `plan_narration_groundedness` and `workpaper_grounding` eval metrics measure
  the RAW model output through the very same contract the service enforces. A metric that watched
  only the already-filtered service output could never go red.
- Personal data is masked before the audit write, before an outbound review payload and before a
  tool result can enter a model's context (`domain/pii.py`, `adapters/_review_payload.py`,
  `agent/tools.py`).
- Every consequential result sets `requires_human_review` and is routed to `human-review-console` (rule R8) in the
  same call; nothing auto-executes, and no model output can satisfy the `issue-remediation-capa` handover's approval
  reference.

## Adapters and profiles

| Profile | Generation adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/generation.py` | Deterministic stub: restates the request's engine facts as JSON, keyed by the requested response key. It emits fact VALUES for a narrative and bracketed fact KEYS for a working paper, because the two consuming services enforce different grounding. Grounded by construction, SDK-free, no network. A silent empty return would let a producer ship the narration seam unwired, so it emits a real, inspectable payload. |
| `gcp` | `adapters/gcp/generation.py` | Gemini via `google.generativeai`, imported lazily inside the method. Model id pinned in the adapter as `_MODEL`, currently `gemini-3.5-flash`, with `response_mime_type=application/json`, `temperature=0.2` and a caller-supplied `max_output_tokens` (the `GenerationRequest` default is 512). |
| `onprem` | `adapters/onprem/generation.py` | Fail-fast placeholder: refuses at call time rather than pretending to narrate, so a placeholder never becomes a silent no-op on the one path where an empty answer would look like a working narrator. |

## Remaining controls (TODO, repo owner)

- **Model id, version and region** (P-07): `gemini-3.5-flash` is a pinned default in the adapter,
  not a confirmed deployment decision. Gemini model ids are regional and an unavailable one fails
  at call time rather than at boot, so confirm the id is served in your region, pin the exact
  version, and record it here. Note that the id appears in a SECOND place, the
  `PromotionGateClient(..., model=...)` argument in `eval/run_eval.py`, and the two are not held
  equal by a test; change both together.
- **Budget, rate limit and a kill switch** (P-10, P-11): `max_output_tokens` is per request and
  there is no per-tenant token budget, no request rate limit, and no switch that forces
  deterministic-only operation. The fallback path already exists, since a discarded or failed reply
  yields the deterministic text, but nothing yet lets an operator disable the model deliberately.
- **Evaluation of the live model**: the offline eval scores the deterministic pipeline with the
  stub adapter against the golden set and the two oracles. Add a managed-profile run, registered
  with the `model-quality-gate` promotion gate (P-08, rule R5), that scores `plan_narration_groundedness` and
  `workpaper_grounding` with the real model bound.
- **Prompt-injection screening** (rule R1): the `agent-guardrail-gateway` is not bound, and this repo
  needs it more than a purely numeric one does. The plan narrative's facts block carries engine
  integers, but the working-paper path puts RETRIEVED PASSAGE TEXT into the prompt, and that text
  comes from a corpus this service does not own. Screen it before it reaches `build_request`, and
  fail closed to deterministic-only when the screen is unavailable.
- **Reasoning trace**: the audit record carries the engine result and its citations, not the
  prompt and reply pair. `COMPLIANCE.md` P-07 records that as owed.

Until these are complete the system is safe to run offline (deterministic engines plus the stub
adapter) and the managed model path is not production-cleared. Note separately that the managed
profile as a whole is blocked by `managed_readiness.py` until the five read adapters' `_parse`
response mappings are implemented, so today the model path cannot be reached in a `gcp` process at
all.
