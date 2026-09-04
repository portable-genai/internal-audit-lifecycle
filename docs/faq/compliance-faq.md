# Compliance FAQ

For compliance, model risk and the second line. The mapping table with a file reference on every
row is [`../../COMPLIANCE.md`](../../COMPLIANCE.md); this page answers the questions that come
back after reading it.

### Is a plan rank or a finding severity from this system defensible?

That is the reason the arithmetic is pure code. `domain/planning.py` and `domain/findings.py`
produce every number, and four rules make those numbers mean something:

- **Every score is decomposed.** A `PlanEntry` carries its `PlanDriver` list, each driver naming
  its points and the calculation behind them, so a challenge lands on a specific driver rather
  than on an opaque total.
- **The inputs belong to the systems that own them.** The control-effectiveness trend is `continuous-controls-monitoring`'s
  verdict and the horizon count is `compliance-advisory`'s, both read through ports. `internal-audit-lifecycle` recomputes neither, so
  three systems cannot disagree about the same fact.
- **The sample is replayable.** The same population, seed and `as_of` yield a byte-identical
  selection, because each stratum's RNG is seeded from a SHA-256 of those three values rather than
  from a per-process salted hash.
- **The severity is computed.** Impact and likelihood are clamped to the configured scale,
  multiplied, and banded against config-owned floors.

The model plays no part in any of it, and the same inputs always produce the same result, so a
figure quoted to a regulator or an audit committee can be replayed from the audit record.

### Who signs off a plan or a finding?

A human, always. Approving an annual plan and raising a finding are both consequential by
construction: `AnnualPlan.requires_human_review` and `Finding.requires_human_review` are always
True, and the flag plus the call to `ReviewRouterPort.route` are one act, not a flag plus an
intention. The API, the CLI and the agent tools all route in the same call that produced the
result, and `tests/unit/test_review_routing.py` asserts the routing rather than the flag. Under
the managed profile the router REFUSES when no console is configured, so a deployment cannot
swallow an escalation silently.

The handover to `issue-remediation-capa` is the second gate: `POST /v1/finding/handover` rejects an empty
`approval_ref`, so a finding reaches the remediation tracker only after the `human-review-console` review that
authorised it.

### Where does the data live, and is residency enforced or just documented?

Enforced at deploy time. The region is chosen once (`asia-southeast1`) and shared by the runtime
and Terraform: `infra/terraform/variables.tf` validates the region against the residency allowlist
at plan, `org_policy.tf` pins `gcp.resourceLocations` to that region's location group, and every
regional resource (the CMEK key ring, the WORM log bucket, the Cloud Run service) is created in
it. `infra/terraform/production_edge.tftest.hcl` is the standing proof: its
`reject_region_outside_the_residency_allowlist` and `residency_defaults_are_in_country` runs fail
if the allowlist stops refusing or a resource drifts off region, and they run against a mocked
provider so they need no project and no credentials.

### What about key management and least privilege?

One REGIONAL CMEK key with a 90-day rotation (`rotation_period = "7776000s"`), and an explicit key
binding for EACH service agent that encrypts under it, because CMEK does not cascade
(`infra/terraform/kms.tf`). One serving identity holding only the roles a request needs, each
traceable to a bound adapter, with `logging.logWriter` write only so the process cannot read back
the WORM trail it writes (`iam.tf`). Exportable service-account keys are forbidden by org policy
rather than merely avoided, and a key creation raises an alert if one happens anyway
(`org_policy.tf`, `monitoring.tf`).

### How long is the audit trail kept, and can it be edited?

180 days by default, and the variable refuses anything below 180, refuses to reduce an existing
locked retention, and is proved to refuse both (`reject_retention_below_six_months`,
`reject_reducing_existing_locked_retention`). The Cloud Logging bucket is LOCKED by default, which
is irreversible: once applied, retention cannot be reduced and the bucket cannot be deleted for
the full window, not even with project-owner rights. Confirm `retention_days` before the first
apply. DATA_READ audit logging is enabled too, so a read of the estate is itself recorded.

Offline the same guarantee is earned differently: the log is hash-chained AND externally anchored,
because a truncated tail leaves a shorter chain that verifies perfectly. The retention schedule
and the legal basis for the trail are adopter-owned.

### What personal data does this system process?

Very little by design: it reasons over auditable entities, obligations, control results and
workpaper extracts rather than customer records. Whatever does appear is masked before every
boundary (the audit write, the outbound review payload, and any tool result that could enter a
model's context), with the jurisdiction rows and their ORDER chosen in `domain/pii.py`. The
`pii_safety` metric holds this at `>= 0.99`, is scored two ways, and is proved able to go red.
Trace spans are held to structural attributes only, because a trace backend has no redaction
stage and a wider read audience than the WORM trail.

### Can one business unit see another's audit estate?

No. `authorize_estate_access` compares the verified principal's tenant against the estate's owning
tenant and raises rather than returning an empty result, and the tenant comes from the verified
principal rather than from the request body. The API answers 403 and not 404, deliberately: the
estate exists. Note the honest limit: offline the seed IS the demo bank's estate, so multi-tenant
isolation at the STORE level is part of binding a durable store, which this repo has not done yet.

### What model-risk evidence exists?

[`../model-card.md`](../model-card.md) records the model boundary as built: the model writes one
plan narrative and one working-paper draft, each schema-validated and grounding-checked and
discarded on failure, with a deterministic fallback used instead. The offline eval scores eight
metrics on every change, two of which (`plan_narration_groundedness` and `workpaper_grounding`)
measure raw model output rather than filtered output so they can go red. What is NOT yet in place:
the managed model id is a pinned default rather than a confirmed deployment decision, there is no
token budget, rate limit or kill switch, no live-model eval run has been registered with the `model-quality-gate`
promotion gate, and prompt-injection screening through `agent-guardrail-gateway` is not bound. Until those close, the
managed narrator is not production-cleared and the deterministic path is what should be relied on.

### Which regulations does this claim to satisfy?

None, on your behalf. The mapping in `COMPLIANCE.md` is to the CATALOG's own principles (P-01 to
P-13) and platform rules (R1 to R8). The crosswalk from those to MAS TRM, CPS 234, CPS 230, HKMA
or PDPA control ids, and the judgement that a control is SUFFICIENT for a regulation, is
explicitly adopter-owned. No row in that document should be quoted as regulatory assurance, and
the second-line review of the deterministic policy in `domain/` is bank-owned logic rather than a
vendor default to inherit unexamined. That applies most sharply to `AuditPlanConfig`: the driver
weights and band floors decide which parts of the bank get audited this year.

### What is still open at go-live?

The `Partial` and `TODO (repo owner)` rows in `COMPLIANCE.md`, each of which names exactly what is
missing. The ones that need a risk acceptance if you go live without them: the managed `_parse`
response mappings and the durable estate store with its object-level authorisation, rule R1 (the
`agent-guardrail-gateway` binding), rule R5 and P-08 (the `model-quality-gate` metric bundle), P-10 (timeouts, circuit
breaker and a documented kill switch), and P-01's private-egress rule, which depends on your own
network rather than on this repo.
