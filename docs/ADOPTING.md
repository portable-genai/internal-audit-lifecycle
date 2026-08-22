# Adopting this repo as your base

This repository (Aud1, Internal Audit Lifecycle Copilot) is a **common base** that a bank or other
regulated institution forks to build its own **internal-audit engagement lifecycle service**: the
risk-based annual plan, the engagement scope and its replayable sample, the grounded working
paper, and the finding write-up that hands over to the issue and CAPA tracker. It ships a reusable
hexagonal core (a pure-stdlib domain, typed ports, three swappable adapter profiles, a green
offline gate) plus four worked audit engines you can keep, reseed or retune.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and topology),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an adapter, adding a port), the
> [`faq/`](faq/) directory, [`model-card.md`](model-card.md) (the model boundary),
> [`practices-audit.md`](practices-audit.md) (the per-check verdict).

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and this vertical is a
physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` owns the vertical-neutral contracts and imports nothing from the vertical;
`domain/models.py` holds this service's own request and result types.

| Layer | Where | For your own audit function |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py` (`Citation`, `AuditEvent`, `Severity`, `Decision`, `utcnow`), every Protocol in `ports/`, the container wiring in `config.py` | keep untouched |
| **The four engines** | `domain/planning.py` (additive named drivers, clamp, band, rank), `domain/scoping.py` (`ScopingService` plus `stratified_sample`), `domain/fieldwork.py` (retrieve, draft, validate citations), `domain/findings.py` (impact x likelihood banded, then the Aud3 handover envelope) | keep the shapes, retune the numbers |
| **Policy (your numbers and rules)** | `AuditPlanConfig` in `domain/planning.py` (driver weights and caps, the Aud2 trend points, the band floors, the priority band), `FindingConfig` in `domain/findings.py` (the scale bounds and the severity floors), the jurisdiction list in `domain/pii.py`, the metric thresholds in `eval/run_eval.py` | change deliberately (see section 4) |
| **Vertical (the estate content)** | `seed_universe()` in `domain/planning.py`, the fixture feeds in `adapters/local/{obligations,control_results,horizon,knowledge_base}.py`, the vertical models in `domain/models.py`, the prompts in `domain/narration.py` and `domain/fieldwork.py`, the eval golden set and its two oracles | reseed and rewrite for your estate |

If your product is another *engagement lifecycle* service, the hexagon, the three profiles, the
deterministic-verdict pattern, the eval gate and the Hrz7 review routing transfer directly; you
replace the audit universe and the upstream feeds and retune the planning and severity policy.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, `ports/`, `tests/contract/`, the
  eval harness mechanics (`eval/run_eval.py`), the CI workflows, the hexagon wiring (`config.py`
  `Container`) and the deploy stack in `infra/terraform/`.
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, the seed universe
  and every fixture, the planning and finding policy objects, `adapters/onprem/*`, the managed
  `_parse` response mappings (section 4 item 4), UI theming and branding, the golden eval dataset
  and both oracles, `infra/terraform/terraform.tfvars`, and the regulator crosswalk section of
  `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name (`internal_audit_lifecycle`, which is also the
console script), the `AUDIT_` env prefix (including the bare token that
`infra/terraform/render.tf.json` carries as `render_env_prefix`, so Terraform sets the same
variable names on the service), the cloud resource stem (`aud1-svc`, the Terraform `name_prefix`)
and the distribution / git id (`internal-audit-lifecycle`) in one pass. Preview first, then
apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_audit_copilot --env-prefix ACME \
    --resource acme-audit --dry-run

# Apply:
python scripts/rename_fork.py --package acme_audit_copilot --env-prefix ACME \
    --resource acme-audit --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the `--resource` value; pass it explicitly when your git id differs from
your resource stem. `--resource` is validated against the same `^[a-z][a-z0-9-]{2,18}$` regex the
Terraform `name_prefix` variable enforces, so a stem the stack would refuse fails here instead of
at plan time. Add `--include-docs` to sweep Markdown prose too. The script skips itself, so the
renamer is never left half-rewritten. The catalog id `Aud1` is left alone unless you pass
`--catalog-id`, so a fork stays traceable to the entry it descends from. The script deliberately
does NOT touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** The build defaults to `asia-southeast1` (MAS / Singapore), chosen once
   and shared: `config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region` and
   the Terraform `region` / `allowed_regions` pair. Set all of them to your in-country region and
   re-run `infra/terraform/production_edge.tftest.hcl`, which refuses a region outside the
   allowlist at plan time. See [`runbook.md`](runbook.md).
2. **Identity / IdP.** This repo owns no login flow: the `gcp` profile verifies the IAP-injected
   assertion at the edge, `local` uses seeded dev personas, and `onprem` is a client IdP
   placeholder. Wire your issuer on the deployed service (auth is configured ON the service, not
   in this code) and set `AUDIT_IAP_AUDIENCE`. An unset or emptied audience refuses every caller
   rather than verifying without one.
3. **The audit universe and the upstream feeds.** `seed_universe()` in `domain/planning.py` builds
   an obviously fictional four-entity universe, and the local adapters for the `obligations`,
   `control_results`, `horizon` and `knowledge_base` ports are fixtures that freeze the contracts
   Aud1 expects from Rgc7, Aud2, Rsk1 and the governed workpaper store. That seed is a shape, not
   your estate. Replace it, and decide where the universe lives in a deployment: the offline
   profile holds it in process, so a deployment needs a durable store bound behind a port of its
   own.
4. **The managed response mappings, which are placeholders on purpose.** Each managed read adapter
   reaches its real surface but leaves `_parse` raising, because nobody can write the payload
   mapping for a system that is not deployed yet. Those five operations are listed in
   `managed_readiness.py`, and `assert_managed_profile_ready` REFUSES to start a `gcp` process
   while any of them is on an active binding. The Dockerfile `CMD` runs that preflight before
   uvicorn, and `infra/terraform/managed_readiness.tf` refuses `production_edge_enabled` for the
   same reason. Implementing and integration-testing those mappings is the largest single piece of
   adoption work, and the stack is designed to fail loudly until you do.
5. **The audit policy your audit function owns.** `AuditPlanConfig` decides how much each driver
   contributes and where the bands fall, so it decides which entities get audited this year;
   `FindingConfig` decides the impact x likelihood floors, and the band is what makes a finding
   consequential. The sampling seed, the `as_of` and the sample size are the caller's, and the
   same three always reproduce the same selection, which is the property that makes a sample
   defensible to a reviewer. These are frozen dataclasses with reference defaults rather than a
   `policy:` settings section (practices-audit check B4); change them deliberately and add a test
   that pins your values.
6. **Tenancy.** `ESTATE_TENANT` and `authorize_estate_access` enforce that a caller may only read
   its own estate, and a cross-tenant read raises 403 rather than returning an empty result or a
   404. Offline the seed IS the demo bank's estate. Decide how your deployment carries the owning
   tenant on universe, engagement and finding rows before you serve a second one.
7. **Reference data is fictional.** Every fixture, the seed universe and the eval datasets use
   obviously fake parties and `.example` domains. Replace them with your own synthetic data.
   **Do not run against a real audit estate without your own security and model-risk sign-off.**
8. **Eval golden set.** Rebuild the golden dataset and both oracles for your estate: a fork
   inherits a green gate that measures the WRONG universe until you do. The eight metrics
   (`decision_accuracy`, `pii_safety`, `plan_ranking_accuracy`, `severity_accuracy`,
   `sample_stratification`, `sample_determinism`, `plan_narration_groundedness`,
   `workpaper_grounding`) and their thresholds are generic; the golden cases in
   `eval/datasets/golden_cases.jsonl`, `plan_oracle.jsonl` and `finding_oracle.jsonl` are yours.
9. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001, the
   managed-readiness preflight in `CMD`), `infra/terraform/` (Org Policy, CMEK, a dry-run-first
   VPC-SC perimeter, the locked WORM log bucket) and the loopback-by-default binding before you
   expose anything. The WORM lock is irreversible: confirm `retention_days` before the first apply.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. It is deliberately the OWNER of
the audit engagement lifecycle up to an approved finding, and of nothing after that. What it
integrates rather than rebuilds (see [`faq/features-faq.md`](faq/features-faq.md) for the full
map):

- **Rgc7** obligations and control mapping: the obligation register a scope is built from, read
  through `ObligationsReadPort` (`AUDIT_OBLIGATIONS_URL`). Aud1 keeps no register.
- **Aud2** control testing and effectiveness: the pass / partial / fail verdicts a scope reads,
  through `ControlResultsReadPort` (`AUDIT_CONTROL_RESULTS_URL`). Aud1 keeps NO control catalog,
  and `tests/contract/test_dependency_contracts.py::test_no_control_catalog_store_port_is_registered`
  fails the build if one appears.
- **Rsk1** compliance assistant: the regulatory change horizon that feeds the planner's
  `horizon_pressure` driver, through `HorizonReadPort` (`AUDIT_HORIZON_URL`). Aud1 never
  recomputes the horizon.
- **Aud3** issue remediation and CAPA: everything AFTER an approved finding. `FindingFeedPort`
  (`AUDIT_AUD3_FEED_URL`) is a one-way emit that requires an Hrz7 approval reference, and
  `test_no_remediation_store_port_is_registered` fails the build if this repo ever grows a
  remediation store.
- **Hrz7** human-review / maker-checker console: every consequential plan, finding and escalated
  triage is routed to it over the shared `review-kit` (rule R8); you wire your endpoint
  (`HRZ_HUMAN_REVIEW_URL`), you do not re-implement the console.
- **Hrz5** observability plus immutable WORM audit: audit events and trace spans go to it through
  `AuditSinkPort` and `ObservabilityTracerPort`.
- **Hrz4** AI-quality / model-risk gate: owns promotion. `eval/run_eval.py --mode gate` is the
  client half and refuses to run off the managed profile.
- **Hrz3** agent registry: this agent publishes its A2A card at
  `/.well-known/agent-card.json`; register it rather than inventing a discovery mechanism.
- **Hrz2** enterprise knowledge base: `KnowledgeBaseReadPort` is the retrieval seam fieldwork
  grounds against. Today the managed adapter points at whatever governed workpaper store
  `AUDIT_KNOWLEDGE_BASE_URL` names; binding it to Hrz2 instead is the rule R3 decision, and it is
  the one your corpus governance probably wants.

The guardrail gateway (Hrz1) is **not** integrated today. It becomes mandatory the moment
untrusted free text reaches the drafter, which the fieldwork path already carries in its retrieved
passages: see rule R1 in [`../COMPLIANCE.md`](../COMPLIANCE.md).

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set the region in all three places (settings, `render.tf.json`, tfvars) and re-ran the
      Terraform residency tests.
- [ ] Wired your IdP audience on the deployed service (this repo owns no login flow).
- [ ] Replaced the seed universe and the four fixture feeds with your own, and bound a durable
      store for the universe.
- [ ] Implemented and integration-tested the five managed `_parse` response mappings, so
      `managed_readiness.py` stops refusing the `gcp` profile.
- [ ] Owned the planning and finding policy (`AuditPlanConfig`, `FindingConfig`) with your audit
      function, and pinned your numbers in a test.
- [ ] Decided how the owning tenant is carried on estate rows before serving a second tenant.
- [ ] Replaced every synthetic fixture.
- [ ] Rebuilt the eval golden set and both oracles for your estate.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, `retention_days`, bind address).
- [ ] Wired your Hrz7 review endpoint and decided which sibling services you integrate vs stub.
- [ ] Read [`model-card.md`](model-card.md) and closed its remaining controls before enabling the
      managed narrator.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
