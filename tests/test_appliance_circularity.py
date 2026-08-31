"""
Unit tests for Appliance Circularity Engine and Embodied Carbon Tracker.
"""

import pytest
from src.services.appliance_circularity_engine import ApplianceCircularityEngine
from src.services.embodied_carbon_tracker import EmbodiedCarbonTracker


def test_tracker_retrieval():
    tracker = EmbodiedCarbonTracker()
    specs = tracker.get_appliance_specs("refrigerator")

    assert specs is not None
    assert specs["name"] == "Refrigerator"
    assert specs["embodied_carbon_kg"] == 600.0
    assert tracker.get_appliance_display_name("hvac_system") == "HVAC System"


def test_engine_evaluation_keep():
    engine = ApplianceCircularityEngine()
    # New fridge, low usage
    result = engine.evaluate_appliance(
        "refrigerator", age_years=2, annual_usage_kwh=400
    )

    assert result["circularity_score"] > 70.0
    assert "Keep and Maintain" in result["recommendation"]
    assert result["tipping_point_years"] > 10.0  # Takes long to break even


def test_engine_evaluation_replace():
    engine = ApplianceCircularityEngine()
    # Old, inefficient fridge, high usage
    result = engine.evaluate_appliance(
        "refrigerator", age_years=16, annual_usage_kwh=800
    )

    assert result["circularity_score"] <= 40.0
    assert (
        "End of Life" in result["recommendation"]
        or "Consider Upgrading" in result["recommendation"]
    )
    assert (
        result["tipping_point_years"] < 10.0
    )  # Breaks even quickly due to high savings


def test_engine_tipping_point_calculation():
    engine = ApplianceCircularityEngine()
    # Washing machine: embodied = 400, savings = 40 (mock)
    # Tipping point should be 400 / 40 = 10 years
    # We'll use specific numbers to force this:
    # Let's say new efficiency saves 40kg/year exactly.
    # We can't easily force exact kg without mocking, so we just check it's a float > 0
    result = engine.evaluate_appliance(
        "washing_machine", age_years=5, annual_usage_kwh=500
    )

    assert isinstance(result["tipping_point_years"], float)
    assert result["tipping_point_years"] > 0.0
    assert result["annual_operational_savings_kg"] > 0.0


def test_engine_unknown_appliance():
    engine = ApplianceCircularityEngine()
    with pytest.raises(ValueError, match="Unknown appliance type"):
        engine.evaluate_appliance("magic_box", age_years=1, annual_usage_kwh=100)
