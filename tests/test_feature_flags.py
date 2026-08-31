import pytest
import json
from src.core.feature_flags import FeatureFlag, FeatureFlagStore, feature_flag
from src.core.flag_evaluator import FlagEvaluator
from src.core.database_integrity import inspect_database

def test_flag_evaluator_boolean_state():
    flag_disabled = {"name": "test", "enabled": False}
    flag_enabled = {"name": "test", "enabled": True}
    
    assert FlagEvaluator.evaluate(flag_disabled, "user1")["enabled"] is False
    assert FlagEvaluator.evaluate(flag_enabled, "user1")["enabled"] is True

def test_flag_evaluator_targeting_rules():
    flag = {
        "name": "test", 
        "enabled": True, 
        "target_rules": json.dumps({"beta_tester": True})
    }
    
    # Missing property -> False
    assert FlagEvaluator.evaluate(flag, "user1")["enabled"] is False
    
    # Wrong property -> False
    assert FlagEvaluator.evaluate(flag, "user1", {"beta_tester": False})["enabled"] is False
    
    # Correct property -> True
    assert FlagEvaluator.evaluate(flag, "user1", {"beta_tester": True})["enabled"] is True

def test_flag_evaluator_rollout():
    flag = {
        "name": "test",
        "enabled": True,
        "rollout_percentage": 50.0
    }
    
    # Due to hashing, we don't strictly know if user1 will be True or False without running it, 
    # but we can ensure it's deterministic for the same user.
    result1 = FlagEvaluator.evaluate(flag, "user1")
    result2 = FlagEvaluator.evaluate(flag, "user1")
    
    assert result1["enabled"] == result2["enabled"]
    assert result1["variant"] == result2["variant"]

def test_flag_evaluator_variants():
    flag = {
        "name": "test",
        "enabled": True,
        "variants": json.dumps(["A", "B", "C"])
    }
    
    result = FlagEvaluator.evaluate(flag, "user1")
    assert result["enabled"] is True
    assert result["variant"] in ["A", "B", "C"]

def test_feature_flag_decorator():
    # Set up a test flag in DB
    test_flag = FeatureFlag(
        name="decorator_test",
        enabled=True,
        variants=json.dumps(["variant1"])
    )
    FeatureFlagStore.upsert_flag(test_flag)
    
    def fallback(user_id=None):
        return "fallback"

    @feature_flag("decorator_test", fallback_func=fallback)
    def test_func(user_id=None, _flag_variant=None):
        return _flag_variant
        
    # With flag enabled, should return the variant
    res = test_func(user_id="user1")
    assert res == "variant1"
    
    # Disable flag
    test_flag.enabled = False
    FeatureFlagStore.upsert_flag(test_flag)
    
    res = test_func(user_id="user1")
    assert res == "fallback"
    
    # Cleanup
    FeatureFlagStore.delete_flag("decorator_test")


