"""
Unit tests for Daily Commute Optimizer and Transit Carbon Tracker.
"""

import pytest
from src.services.daily_commute_optimizer import DailyCommuteOptimizer
from src.services.transit_carbon_tracker import TransitCarbonTracker


def test_optimizer_evaluation():
    optimizer = DailyCommuteOptimizer(
        distance_km=10.0, weather="sunny", traffic="light"
    )
    results = optimizer.evaluate_modes()

    # Should return 5 modes
    assert len(results) == 5

    # Biking and walking should have 0 carbon
    assert results[0]["carbon_kg"] == 0.0
    assert results[1]["carbon_kg"] == 0.0

    # Driving gas should be higher than EV
    gas_result = next(r for r in results if r["mode_key"] == "driving_gas")
    ev_result = next(r for r in results if r["mode_key"] == "driving_ev")
    assert gas_result["carbon_kg"] > ev_result["carbon_kg"]


def test_optimizer_weather_impact():
    sunny_opt = DailyCommuteOptimizer(distance_km=10.0, weather="sunny")
    rainy_opt = DailyCommuteOptimizer(distance_km=10.0, weather="rainy")

    sunny_bike = next(
        r for r in sunny_opt.evaluate_modes() if r["mode_key"] == "biking"
    )
    rainy_bike = next(
        r for r in rainy_opt.evaluate_modes() if r["mode_key"] == "biking"
    )

    # Rain should increase biking time and slightly increase carbon (e.g., due to gear/inefficiency mock)
    assert rainy_bike["time_minutes"] > sunny_bike["time_minutes"]


def test_optimizer_traffic_impact():
    light_opt = DailyCommuteOptimizer(distance_km=10.0, traffic="light")
    heavy_opt = DailyCommuteOptimizer(distance_km=10.0, traffic="heavy")

    light_car = next(
        r for r in light_opt.evaluate_modes() if r["mode_key"] == "driving_gas"
    )
    heavy_car = next(
        r for r in heavy_opt.evaluate_modes() if r["mode_key"] == "driving_gas"
    )

    assert heavy_car["time_minutes"] > light_car["time_minutes"]
    assert heavy_car["carbon_kg"] > light_car["carbon_kg"]  # Idling increases carbon


def test_tracker_logging():
    tracker = TransitCarbonTracker()
    entry = tracker.log_commute("2023-10-25", 10.0, "biking", "driving_gas")

    assert entry["chosen_mode"] == "biking"
    assert entry["carbon_saved_kg"] > 0.0
    assert len(tracker.logs) == 1


def test_tracker_savings_summary():
    tracker = TransitCarbonTracker()
    tracker.log_commute("2023-10-25", 10.0, "biking", "driving_gas")  # Saves ~1.92 kg
    tracker.log_commute(
        "2023-10-25", 10.0, "public_transit", "driving_gas"
    )  # Saves ~0.87 kg

    summary = tracker.get_savings_summary()
    assert summary["total_kg"] > 2.0
    assert (
        summary["today_kg"] == 0.0
    )  # Unless today is 2023-10-25 in the test environment
