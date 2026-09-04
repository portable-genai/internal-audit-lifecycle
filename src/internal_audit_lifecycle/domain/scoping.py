"""Slice 2: engagement scoping and deterministic seeded sampling (pure, replayable).

Scoping pulls the obligations for the audited area from obligations-control-mapping (the SINGLE
SYSTEM OF RECORD, read through the ``obligations`` port) and the current control-effectiveness
results from continuous-controls-monitoring (read through the ``control_results`` port), and
assembles a cited :class:`EngagementScope`. This repo holds NO parallel control catalog: every
control id in a scope came from a read, never from a store of internal-audit-lifecycle's own (the
control-triad boundary; the no-catalog contract test enforces it).

Sampling is deterministic: a stratified-plus-random selection seeded from ``seed`` and ``as_of``,
so the SAME population and seed always yield byte-identical samples that an auditor can replay and
a reviewer can reproduce. The LLM plays no part in either; both are pure stdlib.

The read-port DTOs (:class:`ObligationRef`, :class:`ControlResult`) live here, next to the engine
that consumes them, and the ports import them from this module.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .kernel import Citation

__all__ = [
    "ControlResult",
    "EngagementScope",
    "ObligationRef",
    "SampleUnit",
    "SampleResult",
    "ScopingService",
    "stratified_sample",
]


@dataclass(frozen=True, slots=True)
class ObligationRef:
    """One obligation read from obligations-control-mapping for an audited area (the ``obligations``
    port return).
    """

    id: str
    title: str
    area: str
    owner: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class ControlResult:
    """One control-effectiveness result read from continuous-controls-monitoring (the
    ``control_results`` port return).

    ``effectiveness`` is continuous-controls-monitoring's deterministic verdict (``pass`` /
    ``partial`` / ``fail``); this
    repo reads it and never recomputes or restates a control catalog of its own.
    """

    control_id: str
    area: str
    effectiveness: str
    as_of: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class EngagementScope:
    """The assembled scope for one engagement area: obligations, control results and coverage."""

    area: str
    obligations: tuple[ObligationRef, ...]
    control_results: tuple[ControlResult, ...]
    failing_controls: tuple[str, ...]
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class SampleUnit:
    """One sampleable item (e.g. a transaction or control instance) with its stratum."""

    id: str
    stratum: str


@dataclass(frozen=True, slots=True)
class SampleResult:
    """A replayable sample: the seed, the per-stratum allocation and the selected ids."""

    seed: int
    as_of: str
    size: int
    strata: tuple[tuple[str, int], ...]
    selected: tuple[str, ...]


class ScopingService:
    """Assemble an engagement scope from read-only obligations-control-mapping and
    continuous-controls-monitoring inputs (no local catalog).
    """

    def build_scope(
        self,
        area: str,
        obligations: tuple[ObligationRef, ...],
        control_results: tuple[ControlResult, ...],
    ) -> EngagementScope:
        """Filter the read inputs to the audited area and flag the failing controls.

        A control counts as failing (and therefore worth sampling) when
        continuous-controls-monitoring's verdict is not a
        clean ``pass``. The result is cited by the obligations and controls it drew from.
        """
        in_area_obl = tuple(o for o in obligations if o.area == area)
        in_area_ctrl = tuple(c for c in control_results if c.area == area)
        failing = tuple(c.control_id for c in in_area_ctrl if c.effectiveness.lower() != "pass")
        citations = tuple(o.citation for o in in_area_obl) + tuple(c.citation for c in in_area_ctrl)
        return EngagementScope(
            area=area,
            obligations=in_area_obl,
            control_results=in_area_ctrl,
            failing_controls=failing,
            citations=citations,
        )


def _seed_int(seed: int, as_of: str, stratum: str) -> int:
    """A stable per-stratum seed derived from (seed, as_of, stratum) with no global RNG state.

    ``random.Random`` seeded from a machine-independent hash keeps the selection replayable
    across processes and Python builds (``hash()`` is salted per-process, so it is never used).
    """
    digest = hashlib.sha256(f"{seed}:{as_of}:{stratum}".encode()).hexdigest()
    return int(digest[:16], 16)


def stratified_sample(
    population: tuple[SampleUnit, ...], *, seed: int, as_of: str, size: int
) -> SampleResult:
    """Select ``size`` items, allocated across strata proportionally, deterministically.

    The population is sorted by id first, then each stratum draws its proportional share using a
    stratum-specific seeded RNG. Same population, seed and ``as_of`` -> byte-identical selection.
    Largest strata are topped up first when integer allocation leaves a remainder, so the total
    is exactly ``min(size, len(population))``.
    """
    import random

    if size <= 0 or not population:
        return SampleResult(seed=seed, as_of=as_of, size=0, strata=(), selected=())

    ordered = sorted(population, key=lambda u: u.id)
    target = min(size, len(ordered))

    buckets: dict[str, list[str]] = {}
    for unit in ordered:
        buckets.setdefault(unit.stratum, []).append(unit.id)

    total = len(ordered)
    # Proportional integer allocation; distribute the remainder to the largest strata first.
    raw_alloc = {stratum: (len(ids) * target) // total for stratum, ids in buckets.items()}
    allocated = sum(raw_alloc.values())
    remainder = target - allocated
    for stratum in sorted(buckets, key=lambda s: (-len(buckets[s]), s)):
        if remainder <= 0:
            break
        if raw_alloc[stratum] < len(buckets[stratum]):
            raw_alloc[stratum] += 1
            remainder -= 1

    selected: list[str] = []
    strata_alloc: list[tuple[str, int]] = []
    for stratum in sorted(buckets):
        ids = buckets[stratum]
        take = min(raw_alloc[stratum], len(ids))
        rng = random.Random(_seed_int(seed, as_of, stratum))
        picks = sorted(rng.sample(ids, take)) if take else []
        selected.extend(picks)
        strata_alloc.append((stratum, take))

    return SampleResult(
        seed=seed,
        as_of=as_of,
        size=len(selected),
        strata=tuple(strata_alloc),
        selected=tuple(sorted(selected)),
    )
