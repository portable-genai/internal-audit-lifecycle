"""Slice 1: the risk-based annual audit-planning engine (pure, replayable).

The consequential judgement (which entities in the audit universe rank highest for the annual
plan, and in what band) is PURE CODE over a frozen, config-owned policy object, cribbing the
additive named-driver shape of Rsk1's horizon materiality engine: each entity's score is the sum
of named :class:`PlanDriver` contributions (inherent risk, the age of the last assurance, the
Aud2 control-effectiveness trend, and Rsk1 horizon pressure), clamped and banded by config-owned
thresholds. The same universe always yields the same ranked plan; an LLM may draft the plan
NARRATIVE (see ``narration.py``) but never produces a score, a band or a rank.

``AuditPlanConfig`` holds the numbers (B4: bank-owned policy in config, defaults are the
reference policy). Nothing here imports a framework, a cloud SDK or a port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .kernel import Citation, Decision, Severity

__all__ = [
    "AuditEntity",
    "AuditPlanConfig",
    "AnnualPlan",
    "AnnualPlanner",
    "HorizonSignal",
    "PlanDriver",
    "PlanEntry",
    "enrich_universe",
    "seed_universe",
    "worst_plan_severity",
]

#: The band order low..critical, so a "reaches this band" comparison is an index comparison.
_BAND_ORDER: tuple[Severity, ...] = (
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)

#: Reference control-effectiveness trend points (from Aud2). A declining trend is the strongest
#: single signal that an area needs an audit; an improving one earns a discount.
_DEFAULT_TREND_POINTS: dict[str, int] = {
    "declining": 26,
    "stable": 8,
    "improving": -6,
    "unknown": 12,
}

#: Reference band floors, evaluated strongest-first against the clamped score.
_DEFAULT_BAND_THRESHOLDS: dict[str, int] = {
    Severity.CRITICAL.value: 78,
    Severity.HIGH.value: 56,
    Severity.MEDIUM.value: 32,
    Severity.LOW.value: 0,
}


@dataclass(frozen=True, slots=True)
class AuditEntity:
    """One entity in the audit universe (obviously fictional in the seed).

    The fields are the named-driver INPUTS, sourced from: the firm's inherent-risk register
    (``inherent_factor``), prior audit findings (``prior_finding_age_days``), Aud2's
    control-effectiveness trend (``control_trend``) and Rsk1's horizon change-feed
    (``horizon_signals``). The engine, not the model, turns them into a score.
    """

    id: str
    name: str
    category: str
    inherent_factor: int
    prior_finding_age_days: int
    control_trend: str
    horizon_signals: int
    citation: Citation


@dataclass(frozen=True, slots=True)
class HorizonSignal:
    """A per-entity horizon-pressure count read from Rsk1's change-feed (the ``horizon`` port).

    Rsk1 is the SINGLE source of regulatory-horizon change; Aud1 never recomputes it. The count
    is the number of open change items touching the entity's area, and the planner overlays it
    onto the universe row (see :func:`enrich_universe`) rather than trusting a stale stored value.
    """

    entity_id: str
    signals: int
    citation: Citation


def enrich_universe(
    entities: tuple[AuditEntity, ...], signals: tuple[HorizonSignal, ...]
) -> tuple[AuditEntity, ...]:
    """Overlay the freshly-read Rsk1 horizon signal counts onto the universe rows.

    An entity with a matching :class:`HorizonSignal` takes the read count; one with none keeps
    its stored value. This is where the Rsk1 dependency enters the deterministic engine, through
    the ``horizon`` port, so the planner never has to reach a feed itself.
    """
    by_id = {s.entity_id: s for s in signals}
    out: list[AuditEntity] = []
    for entity in entities:
        signal = by_id.get(entity.id)
        if signal is None:
            out.append(entity)
            continue
        out.append(
            AuditEntity(
                id=entity.id,
                name=entity.name,
                category=entity.category,
                inherent_factor=entity.inherent_factor,
                prior_finding_age_days=entity.prior_finding_age_days,
                control_trend=entity.control_trend,
                horizon_signals=max(0, signal.signals),
                citation=entity.citation,
            )
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class PlanDriver:
    """One named, additive contribution to an entity's plan score (Rsk1's driver shape)."""

    name: str
    points: int
    detail: str


@dataclass(frozen=True, slots=True)
class PlanEntry:
    """One ranked entity in the annual plan: its score, band, rank and the drivers behind them."""

    entity_id: str
    name: str
    score: int
    band: Severity
    rank: int
    drivers: tuple[PlanDriver, ...]
    citation: Citation


@dataclass(frozen=True, slots=True)
class AnnualPlan:
    """The consequential annual plan: a ranked universe, escalated for lead-auditor sign-off.

    The field set overlaps the R8 review envelope on purpose (``subject`` / ``severity`` /
    ``decision`` / ``summary`` / ``requires_human_review`` / ``citations``) so a surface can route
    it to Hrz7 without the pure domain importing a surface type. Approving an annual plan is
    consequential, so ``requires_human_review`` is always True.
    """

    scope: str
    as_of: str
    entries: tuple[PlanEntry, ...]
    subject: str
    severity: Severity
    decision: Decision
    summary: str
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditPlanConfig:
    """Bank-owned annual-planning policy numbers (B4). Defaults equal the reference policy."""

    inherent_weight_pct: int = 45  # percent of the inherent factor carried into the score
    max_inherent_points: int = 45
    prior_finding_days_floor: int = 365  # a finding older than a year starts to age the plan
    prior_finding_points_per_year: int = 9
    max_prior_finding_points: int = 27
    trend_points: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_TREND_POINTS))
    horizon_points: int = 7  # per open Rsk1 horizon signal on the entity's area
    max_horizon_points: int = 21
    band_thresholds: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_BAND_THRESHOLDS))
    #: Band at or above which the plan flags the entity for priority scheduling in the narrative.
    priority_band: str = Severity.HIGH.value


def worst_plan_severity(entries: tuple[PlanEntry, ...]) -> Severity:
    """The plan's overall severity is the highest band any entity reached (low if empty)."""
    worst = Severity.LOW
    for entry in entries:
        if _BAND_ORDER.index(entry.band) > _BAND_ORDER.index(worst):
            worst = entry.band
    return worst


class AnnualPlanner:
    """Pure decision logic for risk-based annual planning. No I/O, no model, no side effects."""

    MIN_SCORE = 0
    MAX_SCORE = 100

    def __init__(self, config: AuditPlanConfig | None = None) -> None:
        self.config = config or AuditPlanConfig()

    def score_entity(self, entity: AuditEntity) -> tuple[int, tuple[PlanDriver, ...]]:
        """Compute an entity's clamped score from named, additive drivers."""
        cfg = self.config
        drivers: list[PlanDriver] = []

        inherent = min(
            cfg.max_inherent_points,
            (max(0, entity.inherent_factor) * cfg.inherent_weight_pct) // 100,
        )
        drivers.append(
            PlanDriver(
                name="inherent_risk",
                points=inherent,
                detail=(
                    f"inherent factor {entity.inherent_factor} at {cfg.inherent_weight_pct}%, "
                    f"capped at {cfg.max_inherent_points}"
                ),
            )
        )

        years_stale = max(0, entity.prior_finding_age_days - cfg.prior_finding_days_floor) // 365
        prior = min(cfg.max_prior_finding_points, years_stale * cfg.prior_finding_points_per_year)
        drivers.append(
            PlanDriver(
                name="prior_finding_age",
                points=prior,
                detail=(
                    f"last assurance {entity.prior_finding_age_days} days ago; "
                    f"{years_stale} year(s) past the {cfg.prior_finding_days_floor}-day floor"
                ),
            )
        )

        trend_points = int(cfg.trend_points.get(entity.control_trend, cfg.trend_points["unknown"]))
        drivers.append(
            PlanDriver(
                name="control_trend",
                points=trend_points,
                detail=f"Aud2 trend '{entity.control_trend}' scored {trend_points} by policy",
            )
        )

        signals = max(0, entity.horizon_signals)
        horizon = min(cfg.max_horizon_points, signals * cfg.horizon_points)
        drivers.append(
            PlanDriver(
                name="horizon_pressure",
                points=horizon,
                detail=(
                    f"{signals} open Rsk1 horizon signal(s) at {cfg.horizon_points} each, "
                    f"capped at {cfg.max_horizon_points}"
                ),
            )
        )

        raw = sum(d.points for d in drivers)
        score = max(self.MIN_SCORE, min(self.MAX_SCORE, raw))
        return score, tuple(drivers)

    def band_for(self, score: int) -> Severity:
        """Band a clamped score against the config-owned floors, strongest first."""
        thresholds = self.config.band_thresholds
        for band in reversed(_BAND_ORDER):
            floor = thresholds.get(band.value)
            if floor is not None and score >= int(floor):
                return band
        return Severity.LOW

    def rank(self, entities: tuple[AuditEntity, ...], *, as_of: date, scope: str) -> AnnualPlan:
        """Rank the whole universe into the annual plan.

        Sorted by score DESC then entity id ASC, so ties break deterministically and the same
        universe always produces byte-identical ranking. Entities carry their own citation, so
        every ranked line is traceable to the universe row that produced it.
        """
        scored = [
            (score, entity, drivers)
            for entity in entities
            for score, drivers in [self.score_entity(entity)]
        ]
        scored.sort(key=lambda row: (-row[0], row[1].id))
        entries = tuple(
            PlanEntry(
                entity_id=entity.id,
                name=entity.name,
                score=score,
                band=self.band_for(score),
                rank=index + 1,
                drivers=drivers,
                citation=entity.citation,
            )
            for index, (score, entity, drivers) in enumerate(scored)
        )
        severity = worst_plan_severity(entries)
        top = ", ".join(f"{e.entity_id}={e.score}({e.band.value})" for e in entries[:3])
        summary = f"{scope}: {len(entries)} entities ranked as of {as_of.isoformat()}; top: {top}"
        return AnnualPlan(
            scope=scope,
            as_of=as_of.isoformat(),
            entries=entries,
            subject=scope,
            severity=severity,
            decision=Decision.ESCALATED,
            summary=summary,
            requires_human_review=True,
            citations=tuple(e.citation for e in entries[:6]),
        )


# --------------------------------------------------------------------------- #
# The seed audit universe (obviously fictional; the offline "file" store)
# --------------------------------------------------------------------------- #
def _cit(source_id: str, title: str) -> Citation:
    return Citation(source_id=source_id, title=title, snippet="audit-universe row")


def seed_universe() -> tuple[AuditEntity, ...]:
    """The offline audit universe: fictional auditable entities exercising every band.

    Deliberately spans a critical, a high, a medium and a low entity so a surface, the eval
    oracle and the demo all have each band to show. All parties are fictional.
    """
    return (
        AuditEntity(
            id="ent-payments",
            name="Retail Payments Operations (FICTIONAL)",
            category="Operations",
            inherent_factor=90,
            prior_finding_age_days=1200,
            control_trend="declining",
            horizon_signals=3,
            citation=_cit("universe/ent-payments", "Retail Payments Operations"),
        ),
        AuditEntity(
            id="ent-treasury",
            name="Treasury and Liquidity (FICTIONAL)",
            category="Finance",
            inherent_factor=80,
            prior_finding_age_days=800,
            control_trend="stable",
            horizon_signals=2,
            citation=_cit("universe/ent-treasury", "Treasury and Liquidity"),
        ),
        AuditEntity(
            id="ent-onboarding",
            name="Customer Onboarding and KYC (FICTIONAL)",
            category="Compliance",
            inherent_factor=70,
            prior_finding_age_days=520,
            control_trend="unknown",
            horizon_signals=1,
            citation=_cit("universe/ent-onboarding", "Customer Onboarding and KYC"),
        ),
        AuditEntity(
            id="ent-facilities",
            name="Facilities and Premises (FICTIONAL)",
            category="Corporate Services",
            inherent_factor=25,
            prior_finding_age_days=200,
            control_trend="improving",
            horizon_signals=0,
            citation=_cit("universe/ent-facilities", "Facilities and Premises"),
        ),
    )
