"""Tests for the Scenario-Based Reduction Planning & Optimization Engine."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.scenario_reduction_engine import (
    CATEGORY_REDUCTION_CEILINGS,
    MEASURED_SOURCE,
    PROJECTION_SOURCE,
    RANK_BY_COST,
    RANK_BY_EFFORT,
    RANK_BY_REDUCTION,
    ReductionAction,
    ReductionScenario,
    ReductionTarget,
    ScenarioEngineValidationError,
    action_from_mapping,
    generate_scenarios,
    rank_scenarios,
    reconcile_with_emissions_engine,
)


# ---------------------------------------------------------------------------
# ReductionAction
# ---------------------------------------------------------------------------

def test_action_effective_reduction_applies_max_adoption():
    action = ReductionAction(
        id="a1", name="Bike commute", category="Transportation",
        reduction_kg=1000, max_adoption=0.5,
    )
    assert action.effective_reduction_kg == 500.0


def test_action_rejects_negative_reduction():
    with pytest.raises(ScenarioEngineValidationError):
        ReductionAction(id="a1", name="x", category="Transportation", reduction_kg=-5)


def test_action_rejects_missing_id():
    with pytest.raises(ScenarioEngineValidationError):
        ReductionAction(id="  ", name="x", category="Transportation", reduction_kg=5)


def test_action_effort_accepts_string_scale():
    action = ReductionAction(
        id="a1", name="x", category="Diet", reduction_kg=100, effort="high",
    )
    assert action.effort == 3.0


def test_action_effort_rejects_unknown_string():
    with pytest.raises(ScenarioEngineValidationError):
        ReductionAction(id="a1", name="x", category="Diet", reduction_kg=100, effort="extreme")


def test_action_from_mapping_parses_conflicts_alias():
    action = action_from_mapping({
        "id": "a1", "name": "x", "category": "Waste", "reduction_kg": 50,
        "conflicts": ["a2"],
    })
    assert action.excludes == ("a2",)


# ---------------------------------------------------------------------------
# ReductionTarget
# ---------------------------------------------------------------------------

def test_target_resolves_percent_to_kg():
    target = ReductionTarget(baseline_kg=10000, target_percent=10)
    assert target.resolved_target_kg == 1000.0


def test_target_resolves_kg_to_percent():
    target = ReductionTarget(baseline_kg=10000, target_kg=2000)
    assert target.resolved_target_percent == 20.0


def test_target_requires_percent_or_kg():
    with pytest.raises(ScenarioEngineValidationError):
        ReductionTarget(baseline_kg=10000)


def test_target_rejects_invalid_baseline():
    with pytest.raises(ScenarioEngineValidationError):
        ReductionTarget(baseline_kg=0, target_percent=10)


# ---------------------------------------------------------------------------
# generate_scenarios
# ---------------------------------------------------------------------------

def _sample_actions():
    return [
        ReductionAction(id="bike", name="Bike commute", category="Transportation",
                         reduction_kg=600, effort="medium", cost=50, max_adoption=1.0),
        ReductionAction(id="ev", name="Switch to EV", category="Transportation",
                         reduction_kg=1200, effort="high", cost=5000, max_adoption=1.0,
                         excludes=("bike",)),
        ReductionAction(id="led", name="LED bulbs", category="Electricity",
                         reduction_kg=150, effort="low", cost=30, max_adoption=1.0),
        ReductionAction(id="solar", name="Rooftop solar", category="Electricity",
                         reduction_kg=900, effort="high", cost=8000, max_adoption=1.0,
                         dependencies=("led",)),
        ReductionAction(id="diet", name="Reduce red meat", category="Diet",
                         reduction_kg=400, effort="medium", cost=0, max_adoption=0.5),
    ]


def test_generate_scenarios_meets_target_and_matches_sum():
    target = ReductionTarget(baseline_kg=10000, target_percent=10)  # 1000 kg
    scenarios = generate_scenarios(_sample_actions(), target)
    feasible = [s for s in scenarios if s.meets_target]
    assert feasible
    for scenario in feasible:
        assert scenario.total_reduction_kg >= target.resolved_target_kg
        assert scenario.total_reduction_kg == pytest.approx(
            sum(scenario.category_breakdown.values())
        )
        assert scenario.source == PROJECTION_SOURCE


def test_generate_scenarios_respects_conflicts():
    target = ReductionTarget(baseline_kg=100000, target_percent=1)
    scenarios = generate_scenarios(_sample_actions(), target)
    for scenario in scenarios:
        assert not ({"bike", "ev"} <= set(scenario.action_ids))


def test_generate_scenarios_auto_expands_dependencies():
    target = ReductionTarget(baseline_kg=100000, target_percent=1)
    scenarios = generate_scenarios(_sample_actions(), target, max_actions=1)
    solar_scenarios = [s for s in scenarios if "solar" in s.action_ids]
    assert solar_scenarios
    for scenario in solar_scenarios:
        assert "led" in scenario.action_ids


def test_generate_scenarios_rejects_duplicate_ids():
    actions = [
        ReductionAction(id="a1", name="x", category="Diet", reduction_kg=10),
        ReductionAction(id="a1", name="y", category="Diet", reduction_kg=20),
    ]
    target = ReductionTarget(baseline_kg=1000, target_percent=10)
    with pytest.raises(ScenarioEngineValidationError):
        generate_scenarios(actions, target)


def test_generate_scenarios_rejects_unknown_dependency():
    actions = [
        ReductionAction(id="a1", name="x", category="Diet", reduction_kg=10,
                         dependencies=("missing",)),
    ]
    target = ReductionTarget(baseline_kg=1000, target_percent=10)
    with pytest.raises(ScenarioEngineValidationError):
        generate_scenarios(actions, target)


def test_generate_scenarios_enforces_category_ceiling():
    # A single action modeled to remove more than the category's realistic
    # ceiling (60% for Electricity) of the category baseline should be
    # excluded once category_baselines are supplied.
    actions = [
        ReductionAction(id="solar_only", name="Rooftop solar", category="Electricity",
                         reduction_kg=900, max_adoption=1.0),
    ]
    target = ReductionTarget(baseline_kg=10000, target_percent=1)
    scenarios = generate_scenarios(
        actions, target, category_baselines={"Electricity": 1000}
    )
    assert scenarios == []  # 900 > 1000 * 0.60 ceiling

    # Raising the category baseline so the same reduction falls under the
    # ceiling should let the scenario through.
    scenarios = generate_scenarios(
        actions, target, category_baselines={"Electricity": 2000}
    )
    assert len(scenarios) == 1


# ---------------------------------------------------------------------------
# rank_scenarios
# ---------------------------------------------------------------------------

def test_rank_scenarios_by_effort_orders_ascending():
    target = ReductionTarget(baseline_kg=10000, target_percent=5)  # 500 kg
    scenarios = generate_scenarios(_sample_actions(), target)
    ranked = rank_scenarios(scenarios, by=RANK_BY_EFFORT)
    efforts = [s.total_effort for s in ranked]
    assert efforts == sorted(efforts)
    assert all(s.meets_target for s in ranked)


def test_rank_scenarios_by_cost_orders_ascending():
    target = ReductionTarget(baseline_kg=10000, target_percent=5)
    scenarios = generate_scenarios(_sample_actions(), target)
    ranked = rank_scenarios(scenarios, by=RANK_BY_COST)
    costs = [s.total_cost for s in ranked]
    assert costs == sorted(costs)


def test_rank_scenarios_by_reduction_orders_descending():
    target = ReductionTarget(baseline_kg=10000, target_percent=5)
    scenarios = generate_scenarios(_sample_actions(), target)
    ranked = rank_scenarios(scenarios, by=RANK_BY_REDUCTION)
    reductions = [s.total_reduction_kg for s in ranked]
    assert reductions == sorted(reductions, reverse=True)


def test_rank_scenarios_feasible_only_false_includes_short_scenarios():
    target = ReductionTarget(baseline_kg=10000, target_percent=90)  # very high bar
    scenarios = generate_scenarios(_sample_actions(), target)
    assert not any(s.meets_target for s in scenarios)
    ranked_all = rank_scenarios(scenarios, feasible_only=False)
    assert ranked_all  # non-feasible scenarios are still returned


def test_rank_scenarios_rejects_unknown_key():
    with pytest.raises(ScenarioEngineValidationError):
        rank_scenarios([], by="fastest")


# ---------------------------------------------------------------------------
# reconcile_with_emissions_engine (must reconcile with the real engine)
# ---------------------------------------------------------------------------

def test_reconcile_matches_underlying_emissions_engine():
    with patch("src.carbon.emissions.os.environ.get", return_value=None):
        from src.carbon.emissions import calculate_footprint, fetch_emission_factors

        fetch_emission_factors.clear()
        total, contributors = calculate_footprint(
            transport="Car", distance=20, electricity=250,
            diet="Non-Vegetarian", flights=2, region="US",
        )

    actions = [
        ReductionAction(id="ev", name="Switch to EV", category="Transport",
                         reduction_kg=contributors["Transport"] * 0.3),
        ReductionAction(id="led", name="LED bulbs", category="Electricity",
                         reduction_kg=contributors["Electricity"] * 0.2),
    ]
    target = ReductionTarget(baseline_kg=total, target_percent=10)
    scenario = generate_scenarios(actions, target, max_actions=2)[-1]

    report = reconcile_with_emissions_engine(scenario, total, contributors=contributors)

    assert report["source"] == PROJECTION_SOURCE
    assert report["baseline_total_kg"] == round(total, 4)
    assert report["projected_total_kg"] == pytest.approx(
        total - scenario.total_reduction_kg
    )
    for category, check in report["category_checks"].items():
        assert check["status"] == "OK"
        assert check["projected_category_kg"] == pytest.approx(
            contributors[category] - scenario.category_breakdown[category]
        )


def test_reconcile_flags_reduction_exceeding_category_baseline():
    scenario = ReductionScenario(
        action_ids=("a1",), total_reduction_kg=500, total_effort=1,
        total_cost=0, reduction_percent=5, meets_target=True,
        category_breakdown={"Diet": 500},
    )
    report = reconcile_with_emissions_engine(
        scenario, 10000, contributors={"Diet": 300}
    )
    assert report["category_checks"]["Diet"]["status"] == "EXCEEDS_BASELINE"


def test_reconcile_labels_projection_vs_measured_distinctly():
    scenario = ReductionScenario(
        action_ids=("a1",), total_reduction_kg=100, total_effort=1,
        total_cost=0, reduction_percent=1, meets_target=False,
        category_breakdown={"Diet": 100},
    )
    report = reconcile_with_emissions_engine(scenario, 10000)
    assert report["source"] == PROJECTION_SOURCE
    assert report["source"] != MEASURED_SOURCE


def test_reconcile_rejects_invalid_baseline():
    scenario = ReductionScenario(
        action_ids=(), total_reduction_kg=0, total_effort=0, total_cost=0,
        reduction_percent=0, meets_target=False, category_breakdown={},
    )
    with pytest.raises(ScenarioEngineValidationError):
        reconcile_with_emissions_engine(scenario, 0)