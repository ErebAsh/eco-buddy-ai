"""
Flag evaluation logic for the Feature Flag system.
"""
from typing import Dict, Any, Optional
import hashlib
import json

class FlagEvaluator:
    @staticmethod
    def evaluate(
        flag: Dict[str, Any],
        user_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a feature flag against a user context.
        Returns a dict: {"enabled": bool, "variant": str or None}
        """
        user_context = user_context or {}
        
        # 1. Check boolean state
        if not flag.get("enabled", False):
            return {"enabled": False, "variant": None}
            
        # 2. Process targeting rules
        target_rules = flag.get("target_rules")
        if target_rules:
            if isinstance(target_rules, str):
                try:
                    target_rules = json.loads(target_rules)
                except json.JSONDecodeError:
                    target_rules = {}
                    
            for key, expected_value in target_rules.items():
                actual_value = user_context.get(key)
                if actual_value != expected_value:
                    return {"enabled": False, "variant": None}

        # 3. Evaluate rollout percentage using user hash
        rollout_percentage = flag.get("rollout_percentage", 100.0)
        flag_name = flag.get("name", "")
        if rollout_percentage < 100.0:
            hash_input = f"{user_id}:{flag_name}".encode('utf-8')
            hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
            # Map hash to 0-9999 for two decimal places of precision (100.00%)
            hash_mod = (hash_val % 10000) / 100.0
            if hash_mod >= rollout_percentage:
                return {"enabled": False, "variant": None}
                
        # 4. Determine variant if A/B testing
        variants = flag.get("variants")
        assigned_variant = None
        if variants:
            if isinstance(variants, str):
                try:
                    variants = json.loads(variants)
                except json.JSONDecodeError:
                    variants = []
            
            if variants and isinstance(variants, list):
                # Pick variant deterministically based on user hash
                # Reuse the same hash input but add a salt for variant distribution
                variant_hash_input = f"{user_id}:{flag_name}:variant".encode('utf-8')
                variant_hash_val = int(hashlib.md5(variant_hash_input).hexdigest(), 16)
                assigned_variant = variants[variant_hash_val % len(variants)]
                
        return {"enabled": True, "variant": assigned_variant}
