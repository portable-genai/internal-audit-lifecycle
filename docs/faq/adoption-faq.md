# Adoption FAQ

For an engineering lead forking this repo as their institution's internal-audit copilot. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?"
questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`internal_audit_lifecycle`, which is also the
console script), the `AUDIT_` env prefix (including the bare token that
`infra/terraform/render.tf.json` carries, so Terraform sets the same variable names on the
service), the Terraform `name_prefix` resource stem (`aud1-svc`) and the distribution / git id in
one pass. Preview with `--dry-run`, apply with `--yes`, then recreate the venv, `make install`,
and run `make gate`. The catalog id `Aud1` is left alone unless you pass `--catalog-id`, so a fork
stays traceable to the entry it descends from. The script does the mechanical rename; the human
decisions (region, IdP, the audit universe, the managed response mappings, the planning and
finding policy, the eval golden set) are the checklist in `ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via **git tags**. The repo declares a core-vs-adopter-owned boundary
(`ADOPTING.md` section 2): upstream owns `domain/kernel.py`, `ports/`, `tests/contract/`, the eval
harness mechanics, CI and the Terraform stack; you own `config/settings.yaml` values, the seed
universe and the fixture feeds, the policy objects, `adapters/onprem/*`, the managed `_parse`
mappings, UI theming and `terraform.tfvars`. The commons packages are pinned by commit, so you
take their fixes by bumping the pin rather than by merging code. Rebase your adopter-owned changes
onto each release rather than merging `main` continuously.

### What do we have to supply that is not in this repo?

Four things, and two of them are code here:

1. **The audit universe and the upstream feeds.** `seed_universe()` builds an obviously fictional
   four-entity universe, and the `obligations`, `control_results`, `horizon` and `knowledge_base`
   local adapters are fixtures that freeze the contracts Aud1 expects. Yours replace them.
2. **The managed response mappings.** Every managed read adapter reaches its real surface and then
   calls a `_parse` that raises, because the payload shape of a system that is not deployed yet
   cannot be guessed. `managed_readiness.py` names those five operations and refuses to start a
   `gcp` process while any of them is bound, so this is not something a fork can forget.
3. **A durable store for the estate.** Offline the universe lives in process. A deployment needs a
   store bound behind a port of its own, carrying each estate's owning tenant on its rows.
4. **The review console.** An Hrz7 deployment reachable at `HUMAN_REVIEW_URL`. The managed
   router REFUSES to swallow an escalation when this is empty, so a fork cannot ship rule R8
   unwired and green.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and a contract test that enforces it. A port must be registered in
FIVE places or it runs with no enforcement at all: `ports/__init__.py` (`PORT_PROTOCOLS`),
`config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`. Then bind it in all three families.
`tests/contract/test_port_parity.py` asserts set equality across the five. The durable estate
store is exactly this job, and it is the port a real deployment adds first. See
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

Two ports you may NOT add: a control catalog store and a remediation store.
`tests/contract/test_dependency_contracts.py` fails the build on either, because the first would
duplicate Aud2 and the second would duplicate Aud3, and the control-triad boundary is what keeps
the three systems from each holding a different version of the truth.

### Can I retune the planning and finding policy without touching code?

Partly, and this is stated honestly. `AuditPlanConfig` and `FindingConfig` are already frozen
dataclasses with reference defaults, so retuning is a constructor argument rather than an edit
scattered through the engine. What does not exist yet is a `policy:` block in
`config/settings.yaml` with a `from_policy(...)` constructor, which is the open B4 item in
[`../practices-audit.md`](../practices-audit.md). If your audit function must own these numbers as
configuration rather than as code, plan that addition as part of adoption. The template's triage
keyword bands in `domain/triage_service.py` are still bare module constants.

### Why is there a generic triage service in here?

Because the render started from the template's triage vertical and the four Aud1 engines were
built alongside it. `domain/triage_service.py` (with `/v1/triage`, the CLI `triage` command and
the `triage_case` agent tool) is also the shared R8 review envelope: `TriageResult` is what a
plan or a finding is projected onto before it is routed, so the review path speaks one shape
across the fleet. A fork that wants only the audit engines can delete the triage ROUTE, but
should keep the envelope type.

### Does the gate run for my fork out of the box?

Yes. `make gate` is offline, credential-free and network-free (ruff, ruff format, mypy strict, the
whole suite except integration, and the eval), and the CI workflow references no `secrets.`, so a
fork's build is green immediately. You add secrets only when you wire the `gcp` profile. Note the
eval measures the REFERENCE seed universe until you rebuild the golden set and both oracles for
your own; that is an explicit adoption step, not a silent pass.

### The eval reports high scores. Should we believe them?

Only because each metric is proved able to report something else.
`tests/unit/test_metrics_go_red.py` scores each engine against a dataset's OWN expected outcome
rather than the engine's own verdict, and proves that a disagreeing expectation drops the metric
below its threshold; `tests/unit/test_not_falsely_green.py` does the same for the safety metric.
The two grounding metrics in particular measure the RAW model output through the same pure
functions the service enforces, so they can actually go red; a metric that watched only the
already-filtered service output would be green by construction.

### Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate. A demo step lives in `demo.STEPS` and in
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal, so a claim the
demo makes but nobody verifies cannot exist. `make demo-selftest` runs the whole nine-step arc
headless over the real loopback server and exits non-zero when a claim stops being true. If you
diverge, keep the step keys and the `facts` dict the checks read.

### What is still open?

[`../practices-audit.md`](../practices-audit.md) carries the per-check verdict and the work list.
The four that matter most before production: the managed `_parse` response mappings (until they
land, the `gcp` profile refuses to boot at all), a durable estate store behind a port, binding the
Hrz1 guardrail gateway before untrusted retrieved text reaches the drafter, and registering this
repo's metric bundle with Hrz4 so `eval/run_eval.py --mode gate` has an authority to ask. The
Terraform stack is written, validated and tested against a mocked provider; it has never been
applied.
