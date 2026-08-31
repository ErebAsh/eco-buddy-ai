"""
Feature Flag system with SQLite-backed CRUD and in-memory cache.
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List, Callable, Union
import json
import functools

from src.core.database_connection import database_connection
import src.core.database as database
from src.core.cache import cached
from src.core.cache_config import CACHE_CATEGORY_FEATURE_FLAGS
from src.core.flag_evaluator import FlagEvaluator

@dataclass
class FeatureFlag:
    name: str
    enabled: bool
    rollout_percentage: float = 100.0
    target_rules: str = "{}"
    variants: str = "[]"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FeatureFlag':
        return cls(
            name=data["name"],
            enabled=bool(data.get("enabled", False)),
            rollout_percentage=float(data.get("rollout_percentage", 100.0)),
            target_rules=data.get("target_rules", "{}"),
            variants=data.get("variants", "[]")
        )

class FeatureFlagStore:
    
    @staticmethod
    @cached(category=CACHE_CATEGORY_FEATURE_FLAGS, ttl=300)
    def get_flag(name: str) -> Optional[Dict[str, Any]]:
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, enabled, rollout_percentage, target_rules, variants "
                "FROM feature_flags WHERE name = ?", 
                (name,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "name": row["name"],
                    "enabled": bool(row["enabled"]),
                    "rollout_percentage": row["rollout_percentage"],
                    "target_rules": row["target_rules"],
                    "variants": row["variants"]
                }
            return None
            
    @staticmethod
    def upsert_flag(flag: FeatureFlag) -> None:
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO feature_flags (name, enabled, rollout_percentage, target_rules, variants)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    enabled=excluded.enabled,
                    rollout_percentage=excluded.rollout_percentage,
                    target_rules=excluded.target_rules,
                    variants=excluded.variants,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (flag.name, flag.enabled, flag.rollout_percentage, flag.target_rules, flag.variants)
            )
            conn.commit()
        # Invalidate cache
        FeatureFlagStore.get_flag.clear(name=flag.name)
        
    @staticmethod
    def delete_flag(name: str) -> bool:
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM feature_flags WHERE name = ?", (name,))
            deleted = cursor.rowcount > 0
            conn.commit()
        FeatureFlagStore.get_flag.clear(name=name)
        return deleted

    @staticmethod
    def list_flags() -> List[Dict[str, Any]]:
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, enabled, rollout_percentage, target_rules, variants FROM feature_flags")
            return [
                {
                    "name": row["name"],
                    "enabled": bool(row["enabled"]),
                    "rollout_percentage": row["rollout_percentage"],
                    "target_rules": row["target_rules"],
                    "variants": row["variants"]
                } for row in cursor.fetchall()
            ]

def feature_flag(flag_name: str, fallback_func: Optional[Callable] = None):
    """
    Decorator to conditionally wrap endpoints/functions.
    Requires `user_id` in kwargs or as an attribute of the first argument if it's a request.
    For simplicity, expects `user_id` to be passed as a keyword argument to the function.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user_id = kwargs.get("user_id", "default_user")
            
            flag_data = FeatureFlagStore.get_flag(flag_name)
            is_enabled = False
            variant = None
            
            if flag_data:
                # Optionally pass kwargs as user_context
                eval_result = FlagEvaluator.evaluate(flag_data, user_id, user_context=kwargs)
                is_enabled = eval_result["enabled"]
                variant = eval_result["variant"]
                
            if is_enabled:
                if variant:
                    kwargs["_flag_variant"] = variant
                return func(*args, **kwargs)
            else:
                if fallback_func:
                    return fallback_func(*args, **kwargs)
                return None
        return wrapper
    return decorator
