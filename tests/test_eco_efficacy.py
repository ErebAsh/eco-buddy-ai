"""
Unit tests for Eco-Efficacy Tracker and Micro-Action Therapy.
"""

import pytest
from src.services.eco_efficacy_tracker import EcoEfficacyTracker
from src.services.micro_action_therapy import MicroActionTherapy


def test_tracker_score_calculation():
    tracker = EcoEfficacyTracker()

    # High agency (10), Low anxiety (2) -> Should be high score
    result_good = tracker.administer_check_in(
        anxiety_level=2, agency_level=10, action_taken_today=True
    )
    assert result_good["efficacy_score"] > 80.0
    assert "High Efficacy" in result_good["interpretation"]

    # Low agency (3), High anxiety (9) -> Should be low score
    result_bad = tracker.administer_check_in(
        anxiety_level=9, agency_level=3, action_taken_today=False
    )
    assert result_bad["efficacy_score"] < 50.0
    assert (
        "Building Efficacy" in result_bad["interpretation"]
        or "Support Needed" in result_bad["interpretation"]
    )


def test_tracker_action_bonus():
    tracker = EcoEfficacyTracker()

    score_no_action = tracker.administer_check_in(
        anxiety_level=5, agency_level=5, action_taken_today=False
    )["efficacy_score"]
    score_with_action = tracker.administer_check_in(
        anxiety_level=5, agency_level=5, action_taken_today=True
    )["efficacy_score"]

    # Action bonus is 10 points
    assert score_with_action == score_no_action + 10.0


def test_therapy_action_generation():
    therapy = MicroActionTherapy()

    # Low score should yield low effort action
    action_low = therapy.generate_daily_action(current_efficacy_score=30.0)
    assert action_low["effort_level"] == "Low Effort"
    assert "Start small" in action_low["encouragement"]

    # High score should yield high effort action
    action_high = therapy.generate_daily_action(current_efficacy_score=85.0)
    assert action_high["effort_level"] == "High Effort"
    assert "ripple effects" in action_high["encouragement"]


def test_therapy_no_repetition():
    therapy = MicroActionTherapy()

    # Force generation of multiple actions
    actions = []
    for _ in range(5):
        actions.append(
            therapy.generate_daily_action(current_efficacy_score=50.0)["action_text"]
        )

    # All 5 actions should be unique
    assert len(set(actions)) == 5


def test_therapy_log_completion():
    therapy = MicroActionTherapy()
    test_action = "Test action string"

    therapy.log_completion(test_action)
    assert test_action in therapy.completed_actions

    # Logging again shouldn't duplicate
    therapy.log_completion(test_action)
    assert therapy.completed_actions.count(test_action) == 1
