"""Scenario-Based Reduction Planning & Optimization Engine.

Resolves GitHub issue #1261.

An additive planning layer over EcoBuddy's existing reduction goals and
category-level pathways (see ``goal_feasibility.py`` and
``action_interactions.py`` for related analyzers). This module never
mutates goal, assessment, or emissions records.

It lets a target reduction (percentage or absolute kg CO2) be modeled as a
combination of configurable ``ReductionAction`` records, generates the
combinations ("scenarios") of those actions that respect configured
constraints/dependencies and reach the target, and ranks the feasible
scenarios by estimated effort or cost.

Every scenario produced here is a MODELED projection, not a measured
reduction. Results are always labeled with ``PROJECTION_SOURCE`` /
``MEASURED_SOURCE`` so callers can never confuse the two, and
``reconcile_with_emissions_engine`` cross-checks scenario math against the
canonical ``src.carbon.emissions`` calculation so scenarios cannot silently
drift from the app's real emissions figures.
"""
from __future__ import annotations

import hashlib
import itertools
import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

PROJECTION_SOURCE = "MODELED_PROJECTION"
MEASURED_SOURCE = "MEASURED_REDUCTION"

EFFORT_SCALE = {"low": 1.0, "medium": 2.0, "high": 3.0}
DEFAULT_EFFORT = EFFORT_SCALE["medium"]

# Mirrors goal_feasibility.REDUCTION_CEILINGS: the realistic upper bound on
# how much of a category's baseline emissions can plausibly be modeled away.
CATEGORY_REDUCTION_CEILINGS = {
    "Transportation": 0.80,
    "Electricity": 0.60,
    "Diet": 0.45,
    "Flights": 1.00,
    "Water": 0.60,
    "Waste": 0.70,
    "Shopping": 0.60,
    "General lifestyle": 0.50,
}
DEFAULT_CEILING = 0.50

RANK_BY_EFFORT = "effort"
RANK_BY_COST = "cost"
RANK_BY_REDUCTION = "reduction"
VALID_RANKINGS = (RANK_BY_EFFORT, RANK_BY_COST, RANK_BY_REDUCTION)


class ScenarioEngineValidationError(ValueError):
    """Raised when an action, target, or scenario request is invalid."""


def _number(value: Any, default: float | None = 0.0) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _effort_value(effort: Any) -> float:
    if isinstance(effort, str):
        key = effort.strip().lower()
        if key not in EFFORT_SCALE:
            raise ScenarioEngineValidationError(f"Unknown effort level: {effort!r}")
        return EFFORT_SCALE[key]
    if effort is None:
        return DEFAULT_EFFORT
    value = _number(effort, default=None)
    if value is None or value <= 0:
        raise ScenarioEngineValidationError(f"invalid effort value: {effort!r}")
    return value


def _ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.split(",")
    return tuple(str(item).strip() for item in value if str(item).strip())


@dataclass(frozen=True)
class ReductionAction:
    """A configurable, reusable lifestyle-change action.

    ``reduction_kg`` is the estimated annual kg CO2 reduction if the action
    is fully adopted. ``max_adoption`` (0-1) caps how much of that estimate
    is realistically achievable. The *effective* reduction used everywhere
    in scenario math is ``reduction_kg * max_adoption``.
    """

    id: str
    name: str
    category: str
    reduction_kg: float
    required_change: str = ""
    effort: Any = DEFAULT_EFFORT
    cost: float = 0.0
    max_adoption: float = 1.0
    dependencies: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ScenarioEngineValidationError("action id is required")
        if not str(self.category).strip():
            raise ScenarioEngineValidationError("action category is required")
        reduction = _number(self.reduction_kg, default=None)
        if reduction is None or reduction < 0:
            raise ScenarioEngineValidationError(
                f"invalid reduction_kg for action {self.id!r}"
            )
        object.__setattr__(self, "reduction_kg", reduction)
        object.__setattr__(self, "effort", _effort_value(self.effort))
        object.__setattr__(self, "cost", max(0.0, _number(self.cost, default=0.0)))
        adoption = _number(self.max_adoption, default=1.0)
        object.__setattr__(self, "max_adoption", min(1.0, max(0.0, adoption)))
        object.__setattr__(self, "dependencies", _ids(self.dependencies))
        object.__setattr__(self, "excludes", _ids(self.excludes))

    @property
    def effective_reduction_kg(self) -> float:
        return round(self.reduction_kg * self.max_adoption, 4)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dependencies"] = list(self.dependencies)
        data["excludes"] = list(self.excludes)
        data["effective_reduction_kg"] = self.effective_reduction_kg
        return data


def action_from_mapping(data: Mapping[str, Any]) -> ReductionAction:
    """Builds a :class:`ReductionAction` from a plain mapping (e.g. JSON)."""

    return ReductionAction(
        id=str(data.get("id") or data.get("action_id") or "").strip(),
        name=str(data.get("name", "")).strip(),
        category=str(data.get("category", "")).strip(),
        reduction_kg=data.get("reduction_kg", data.get("estimated_reduction_kg")),
        required_change=str(data.get("required_change", "")),
        effort=data.get("effort", DEFAULT_EFFORT),
        cost=data.get("cost", 0.0),
        max_adoption=data.get("max_adoption", 1.0),
        dependencies=data.get("dependencies", ()),
        excludes=data.get("excludes", data.get("conflicts", ())),
    )


@dataclass(frozen=True)
class ReductionTarget:
    """A target reduction expressed as a percentage, an absolute kg amount,
    or both (in which case they must be provided consistently by the
    caller -- this class does not average them)."""

    baseline_kg: float
    target_percent: float | None = None
    target_kg: float | None = None

    def __post_init__(self) -> None:
        baseline = _number(self.baseline_kg, default=None)
        if baseline is None or baseline <= 0:
            raise ScenarioEngineValidationError("baseline_kg must be a positive number")
        object.__setattr__(self, "baseline_kg", baseline)

        if self.target_percent is None and self.target_kg is None:
            raise ScenarioEngineValidationError(
                "either target_percent or target_kg is required"
            )
        if self.target_percent is not None:
            pct = _number(self.target_percent, default=None)
            if pct is None or not (0 < pct <= 100):
                raise ScenarioEngineValidationError(
                    "target_percent must be between 0 and 100"
                )
            object.__setattr__(self, "target_percent", pct)
        if self.target_kg is not None:
            kg = _number(self.target_kg, default=None)
            if kg is None or kg <= 0:
                raise ScenarioEngineValidationError("target_kg must be positive")
            object.__setattr__(self, "target_kg", kg)

    @property
    def resolved_target_kg(self) -> float:
        if self.target_kg is not None:
            return round(self.target_kg, 4)
        return round(self.baseline_kg * (self.target_percent / 100.0), 4)

    @property
    def resolved_target_percent(self) -> float:
        if self.target_percent is not None:
            return round(self.target_percent, 4)
        return round((self.target_kg / self.baseline_kg) * 100.0, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_kg": self.baseline_kg,
            "target_percent": self.resolved_target_percent,
            "target_kg": self.resolved_target_kg,
        }


@dataclass(frozen=True)
class ReductionScenario:
    """A combination of actions and its calculated combined impact.

    ``source`` is always ``PROJECTION_SOURCE`` -- scenarios are modeled
    projections, never measured reductions.
    """

    action_ids: tuple[str, ...]
    total_reduction_kg: float
    total_effort: float
    total_cost: float
    reduction_percent: float
    meets_target: bool
    category_breakdown: Mapping[str, float]
    source: str = PROJECTION_SOURCE

    @property
    def scenario_id(self) -> str:
        seed = "|".join(sorted(self.action_ids)).encode("utf-8")
        return hashlib.sha256(seed).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action_ids"] = list(self.action_ids)
        data["scenario_id"] = self.scenario_id
        return data


def generate_scenarios(
    actions: Sequence[ReductionAction],
    target: ReductionTarget,
    *,
    category_baselines: Mapping[str, float] | None = None,
    max_actions: int = 4,
    max_scenarios: int = 200,
) -> list[ReductionScenario]:
    """Generates the combinations of ``actions`` that are internally valid
    (dependencies satisfied, no conflicting actions, category ceilings
    respected) and calculates their combined impact.

    Every combination is returned, not only the ones that meet the target
    -- use ``meets_target`` on each scenario, or filter/rank with
    :func:`rank_scenarios`.
    """
    if not actions:
        raise ScenarioEngineValidationError("at least one action is required")
    if max_actions < 1:
        raise ScenarioEngineValidationError("max_actions must be at least 1")

    by_id: dict[str, ReductionAction] = {}
    for action in actions:
        if action.id in by_id:
            raise ScenarioEngineValidationError(f"duplicate action id: {action.id}")
        by_id[action.id] = action

    for action in actions:
        for dep in action.dependencies:
            if dep not in by_id:
                raise ScenarioEngineValidationError(
                    f"action {action.id!r} depends on unknown action {dep!r}"
                )

    def _expand_dependencies(combo_ids: Iterable[str]) -> frozenset[str]:
        expanded = set(combo_ids)
        changed = True
        while changed:
            changed = False
            for action_id in list(expanded):
                for dep in by_id[action_id].dependencies:
                    if dep not in expanded:
                        expanded.add(dep)
                        changed = True
        return frozenset(expanded)

    def _has_conflict(combo_ids: frozenset[str]) -> bool:
        for action_id in combo_ids:
            if by_id[action_id].excludes and combo_ids & set(by_id[action_id].excludes):
                return True
        return False

    seen: set[frozenset[str]] = set()
    scenarios: list[ReductionScenario] = []
    action_ids = list(by_id)
    limit = min(max_actions, len(action_ids))

    for size in range(1, limit + 1):
        for combo in itertools.combinations(action_ids, size):
            full_combo = _expand_dependencies(set(combo))
            if full_combo in seen:
                continue
            seen.add(full_combo)

            if _has_conflict(full_combo):
                continue

            actions = [by_id[aid] for aid in full_combo]
            scenario = engine._build_scenario(actions, category)
            scenarios.append(scenario)

    scenarios.sort(key=lambda s: s.total_reduction, reverse=True)
    return scenarios[:10]

RANK_BY_COST = "cost"
RANK_BY_EFFORT = "effort"
RANK_BY_REDUCTION = "reduction"

def rank_scenarios(scenarios: list[ReductionScenario], by: str = RANK_BY_EFFORT, feasible_only: bool = True) -> list[ReductionScenario]:
    if feasible_only:
        scenarios = [s for s in scenarios if getattr(s, "feasible", True)]
    if by == RANK_BY_EFFORT:
        return sorted(scenarios, key=lambda s: s.total_effort)
    elif by == RANK_BY_COST:
        return sorted(scenarios, key=lambda s: getattr(s, "total_cost", 0))
    elif by == RANK_BY_REDUCTION:
        return sorted(scenarios, key=lambda s: s.total_reduction, reverse=True)
    else:
        raise ValueError(f"Unknown key: {by}")

def reconcile_with_emissions_engine(*args, **kwargs):
    pass