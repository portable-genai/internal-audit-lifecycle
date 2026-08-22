# Portability FAQ

For architecture, cloud governance and exit planning. The question underneath all of these is
"how do we leave, and how do we know the answer is true today rather than on the day it was
written?"

### What is the lock-in surface?

Every outbound dependency is a `@runtime_checkable` Protocol in `ports/`, bound per profile from
`config/settings.yaml`. There are eleven of them: `audit`, `identity`, `review_router`,
`generation`, `obligations`, `control_results`, `horizon`, `knowledge_base`, `finding_feed`,
`tracer` and `evaluation`. There is no cloud SDK import anywhere in `domain/`, and the managed
adapters import their SDK LAZILY inside the method, so the other two families import with no SDK
installed at all. The planning, sampling and severity arithmetic is stdlib, not a managed service.

### What are the three profiles?

| Profile | What it is | Who it is for |
|---|---|---|
| `local` | SDK-free offline stack: seeded dev personas, a hash-chained SQLite WORM audit log, fixture feeds for the Rgc7, Aud2, Rsk1 and workpaper reads, an in-memory Aud3 outbox, a deterministic stub narrator | dev, test, CI, and the offline demo |
| `gcp` | the managed stack: IAP identity, Cloud Logging WORM, Gemini narration, authenticated HTTPS clients to the sibling services and to the Hrz7 console | a managed deployment |
| `onprem` | fail-fast `NotImplementedError` placeholders | the sovereign exit: a client binds its own in-country implementations here |

`AUDIT_PROFILE` selects the family. Unset means the offline adapters bind but nobody chose them,
which withdraws every relaxation rather than granting one.

### Is the portability claim tested, or just documented?

Tested, three ways, all in the offline gate or one command:

- `tests/contract/test_port_parity.py` asserts set equality across all five homes of a port (the
  `PORT_PROTOCOLS` map, `config.DEFAULT_BINDINGS`, the `Container` accessor, `settings.yaml` and
  the canonical-call table), so a port cannot be added in four places and run unenforced.
- `tests/contract/test_behavioral_parity.py` proves the offline family ANSWERS, the on-premises
  family RAISES and the managed family REFUSES rather than silently succeeding. This matters most
  on the narration and read seams: a placeholder that quietly returned an empty note or an empty
  obligation list would look exactly like a working adapter.
- `make portability` is the executable claim: eight named checks with a pass or fail each (port
  map completeness, adapter construction and Protocol conformance, the offline family answering,
  the exit family refusing, rewritten-record detection, anchored truncation detection, the trail
  leaving this codebase intact, and no cloud SDK imported), exiting non-zero on any failure. The
  stronger SDK-free proof lives in `tests/contract/_sdk_free_probe.py`, which BLOCKS the `google`
  import in a fresh interpreter rather than hoping the machine has none installed.

### Where does the audit universe live, and can we take it with us?

Today `seed_universe()` builds it in process and the four upstream reads are answered by fixture
adapters, so the audit trail is the durable artefact. That is honest rather than ideal: a
deployment needs a store bound behind a port of its own, and choosing it is adoption step 3 in
[`../ADOPTING.md`](../ADOPTING.md). What already exports cleanly is the audit trail, which
round-trips to and from JSON Lines, so the record of every plan, sample and finding is a file
copy. The universe itself is plain frozen dataclasses, so serialising it is a schema decision
rather than a vendor extraction.

### How do we actually exit?

[`../onprem-migration.md`](../onprem-migration.md) is the path. The short version: the domain is
pure stdlib and moves unchanged; what you implement is one adapter per port under
`adapters/onprem/`, each of which currently raises with a message naming what to bind. Nothing in
`domain/` has to change, which is the point of the split.

### Can it run with no model at all?

Yes, and that is the load-bearing property rather than a convenience. Every consequential figure
is produced by the deterministic engines, so with the stub generation adapter bound the plan
scores, bands and ranks, the sample selection, the finding severity and every escalation are
identical. The model changes one plan narrative and one working-paper draft, and both have a
deterministic fallback that is used whenever the model's text fails its grounding check. See
[`../model-card.md`](../model-card.md).

### Is the data residency claim portable too?

The region is chosen once and shared by the runtime and Terraform:
`config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region`, and the Terraform
`region` / `allowed_regions` pair, which refuses an unapproved region at plan time. Changing
jurisdiction is a configuration change in those three places plus a re-run of
`infra/terraform/production_edge.tftest.hcl`, not a code change.
