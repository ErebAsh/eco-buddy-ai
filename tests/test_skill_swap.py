"""
Unit tests for Skill Swap Engine and Knowledge Marketplace.
"""

import pytest
from src.services.skill_swap_engine import SkillSwapEngine
from src.services.knowledge_marketplace import KnowledgeMarketplace


def test_engine_user_registration():
    engine = SkillSwapEngine()
    engine.register_user("user1", initial_karma=100)

    user = engine.get_user("user1")
    assert user is not None
    assert user["eco_karma"] == 100
    assert user["completed_swaps"] == 0


def test_engine_add_offering():
    engine = SkillSwapEngine()
    engine.register_user("user1")
    success = engine.add_skill_offering(
        "user1", "Composting", "gardening", "beginner", 20
    )

    assert success is True
    assert len(engine.listings) == 1
    assert engine.listings[0]["skill_name"] == "Composting"
    assert "Composting" in engine.get_user("user1")["skills_offered"]


def test_engine_find_matches():
    engine = SkillSwapEngine()
    engine.register_user("teacher", initial_karma=50)
    engine.register_user("learner", initial_karma=30)

    engine.add_skill_offering("teacher", "Bike Repair", "repair", "intermediate", 25)
    engine.add_skill_offering(
        "teacher", "Advanced Coding", "technology", "advanced", 50
    )

    # Learner can afford Bike Repair (30 >= 25) but not Advanced Coding (30 < 50)
    matches = engine.find_matches("learner", "Bike Repair")
    assert len(matches) == 1
    assert matches[0]["skill_name"] == "Bike Repair"

    matches_expensive = engine.find_matches("learner", "Advanced Coding")
    assert len(matches_expensive) == 0


def test_engine_execute_swap():
    engine = SkillSwapEngine()
    engine.register_user("teacher", initial_karma=50)
    engine.register_user("learner", initial_karma=30)

    engine.add_skill_offering("teacher", "Yoga", "crafts", "beginner", 20)
    listing_id = engine.listings[0]["listing_id"]

    result = engine.execute_swap("learner", listing_id)

    assert result["success"] is True
    assert engine.get_user("learner")["eco_karma"] == 10  # 30 - 20
    assert engine.get_user("teacher")["eco_karma"] == 70  # 50 + 20
    assert engine.get_user("learner")["completed_swaps"] == 1
    assert engine.listings[0]["status"] == "fulfilled"


def test_marketplace_search():
    engine = SkillSwapEngine()
    engine.register_user("user1")
    engine.add_skill_offering("user1", "Vegan Baking", "cooking", "intermediate", 30)
    engine.add_skill_offering("user1", "Garden Composting", "gardening", "beginner", 20)

    marketplace = KnowledgeMarketplace(engine)

    # Search by query
    results = marketplace.search_listings(query="baking")
    assert len(results) == 1
    assert results[0]["skill_name"] == "Vegan Baking"

    # Search by category
    results_cat = marketplace.search_listings(category="gardening")
    assert len(results_cat) == 1
    assert results_cat[0]["category"] == "gardening"
