# Features FAQ

For a product owner, a risk lead or a delivery manager deciding what this system does, what it
refuses to do, and where its responsibility ends.

### What does it actually do?

It runs the internal-audit engagement lifecycle from the annual plan to an approved finding, in
four deterministic engines plus two narrated surfaces:

1. **Risk-based annual planning** (`domain/planning.py`): each auditable entity scores as the sum
   of named additive drivers (inherent risk, the age of the last assurance, the Aud2 control
   effectiveness trend, Rsk1 horizon pressure), clamped to 0..100 and banded by config-owned
   floors, then ranked score DESC then id ASC so ties break the same way every time.
2. **Engagement scoping and sampling** (`domain/scoping.py`): the scope is assembled from Rgc7
   obligations and Aud2 control results for the audited area, the failing controls are flagged,
   and `stratified_sample` selects a proportionally allocated sample from a seed plus an `as_of`
   date, with no global RNG state, so the selection is byte-identical on replay.
3. **Fieldwork and working papers** (`domain/fieldwork.py`): retrieve grounding passages through
   the `knowledge_base` port, ask the model for a draft, and validate that every `[source-id]`
   the draft cites was actually retrieved.
4. **Finding write-up and handover** (`domain/findings.py`): severity is impact x likelihood
   banded by config-owned floors, and an APPROVED finding becomes a normalized `IssueHandover`
   emitted one-way to Aud3.

`domain/narration.py` writes the plan narrative and `domain/fieldwork.py` the working paper; both
restate figures or evidence the engines produced.

### What makes a plan rank or a finding severity defensible?

Four properties, all pure code:

- **The score is built from named drivers, not a black box.** Every `PlanEntry` carries the
  `PlanDriver` list that produced it, each with its points and a sentence explaining the
  arithmetic, so a challenge to a rank is a challenge to a specific driver.
- **The inputs come from the systems that own them.** The control trend is Aud2's verdict and the
  horizon count is Rsk1's; Aud1 recomputes neither.
- **The sample is replayable.** The same population, seed and `as_of` produce the same selection,
  because the per-stratum RNG is seeded from a SHA-256 of those three and never from `hash()`,
  which is salted per process.
- **The severity is computed, not asserted.** `FindingService.assess` clamps impact and likelihood
  to the configured scale, multiplies, and bands the product against config-owned floors.

The model plays no part in any of it.

### What is the model allowed to write?

Two things, both held to a hard rule before they are allowed out:

- **The plan narrative.** Every integer in it must be one the engine produced (the entity count
  and the top three scores). A narrative that invents a figure is discarded and a deterministic
  narrative is used instead.
- **The working paper.** Every `[source-id]` it cites must be a retrieved passage, and it must
  cite at least one. A draft that cites a source that was not retrieved is discarded and a
  deterministic draft built from the passages is used instead.

Both replies must also parse as JSON with the requested key; malformed output is discarded, never
repaired. The response records whether the model or the fallback produced the text, so the eval
and the demo can tell them apart. See [`../model-card.md`](../model-card.md).

### What will it refuse to do?

- **It will not draft a working paper with nothing to ground against.** Empty retrieval means
  `drafted=False` and an explicit "the corpus returned nothing", never an ungrounded narrative.
- **It will not serve another tenant's estate.** `authorize_estate_access` raises
  `CrossTenantError`, which the API maps to 403 and not 404, so the refusal names the fact that
  the estate exists rather than leaking through a probe.
- **It will not hand a finding to Aud3 without an approval.** `POST /v1/finding/handover` rejects
  an empty `approval_ref`, because a finding reaches the remediation tracker only after a human
  approved it in Hrz7.
- **It will not hold remediation state.** There is no CAPA store here, and
  `tests/contract/test_dependency_contracts.py` fails the build if a remediation store port or a
  control catalog store port is ever registered.
- **It will not auto-execute a consequential result.** A plan and a finding always set
  `requires_human_review` and are ROUTED to the Hrz7 console in the same call that produced them
  (rule R8).
- **It will not answer without provenance.** Every claim carries a `Citation`.

### Which surfaces expose it?

The FastAPI app (`POST /v1/plan`, `/v1/scope`, `/v1/workpaper`, `/v1/finding`,
`/v1/finding/handover`, plus the template's `/v1/triage`), the argparse CLI (`triage`, `plan`,
`finding`), the agent tools (`triage_case`, `draft_annual_plan`, `write_finding`,
`verify_audit_trail`, advertised on the A2A card at `/.well-known/agent-card.json`), the
embeddable `ui/` micro-frontend, and the eval harness. Each routes escalations in the same call,
so rule R8 does not hold on some surfaces and not others.

Note that `/v1/triage` and `domain/triage_service.py` are the template's generic triage service,
kept as the shared R8 review envelope the other engines project onto. The four audit engines are
the reason this system exists.

### What does this repo own, and what does it integrate?

| Concern | Owner | How this repo touches it |
|---|---|---|
| The annual plan, the engagement scope and sample, the working paper, the finding | **this repo (Aud1)** | it IS the system of record for the engagement lifecycle up to an approved finding. |
| The obligation, policy and control graph | **Rgc7** obligations and control mapping | read over `ObligationsReadPort` (`AUDIT_OBLIGATIONS_URL`). This repo scopes an engagement; it does not keep a register. |
| Control testing and effectiveness verdicts | **Aud2** control testing | read over `ControlResultsReadPort` (`AUDIT_CONTROL_RESULTS_URL`). Aud1 keeps NO control catalog, and a contract test fails the build if one appears. |
| The regulatory corpus and the change horizon | **Rsk1** compliance assistant | read over `HorizonReadPort` (`AUDIT_HORIZON_URL`); the count becomes the planner's `horizon_pressure` driver. |
| Issue remediation and CAPA to closure | **Aud3** issue remediation and CAPA | one-way emit over `FindingFeedPort` (`AUDIT_AUD3_FEED_URL`), only with an Hrz7 approval reference. Everything after handover is Aud3's. |
| Grounded retrieval over a governed corpus | **Hrz2** enterprise knowledge base | `KnowledgeBaseReadPort` is the seam; today it points at whatever store `AUDIT_KNOWLEDGE_BASE_URL` names. Binding it to Hrz2 is the rule R3 decision. |
| Agent discovery and entitlements | **Hrz3** agent registry | this agent publishes a card; the registry owns discovery. |
| Model and agent promotion | **Hrz4** AI quality and model risk | `eval/run_eval.py --mode gate` asks Hrz4; the offline smoke mode never promotes. |
| Traces and the immutable audit sink | **Hrz5** agent observability | `AuditSinkPort` and `ObservabilityTracerPort`. |
| Human review and maker-checker | **Hrz7** human review console | `ReviewRouterPort` over the shared `review-kit`. This repo produces escalations; it does not render a queue. |
| Prompt-injection defence and output filtering | **Hrz1** agent guardrail gateway | **not wired today.** It becomes mandatory the moment untrusted free text reaches the drafter (rule R1), and the retrieved passages already are that text. |

### Can I demo it without a cloud project?

Yes, and the demo is code rather than a deck. `make demo` runs a presenter-paced walkthrough over
nine steps (opened, routine, escalation, redaction, review queue, audit, tamper, annual plan,
portability) on its own loopback server; `make demo-selftest` runs the same arc headless and
asserts every narrated claim, so a claim that stops being true fails a build rather than a
meeting; `make demo-static` renders the same audit-first panels to static HTML for screenshots.

### What is not built yet?

The honest list is [`../practices-audit.md`](../practices-audit.md) and the `TODO (repo owner)`
rows in [`../../COMPLIANCE.md`](../../COMPLIANCE.md). The three that matter most for a production
decision: the managed read adapters' `_parse` response mappings, which are placeholders that make
`managed_readiness.py` refuse to start a `gcp` process at all; the Hrz1 guardrail binding; and
registering this repo's metric bundle with Hrz4 so `--mode gate` has an authority to ask.
