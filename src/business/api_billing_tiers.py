from dataclasses import dataclass
from typing import Optional

@dataclass
class BillingTier:
    name: str
    monthly_request_limit: int
    overage_allowed: bool

class BillingTierCalculator:
    TIERS = {
        "free": BillingTier("free", 1000, False),
        "basic": BillingTier("basic", 10000, True),
        "pro": BillingTier("pro", 100000, True),
        "enterprise": BillingTier("enterprise", 10000000, True)
    }

    @classmethod
    def get_tier_for_key(cls, key_id: str) -> BillingTier:
        import src.core.database as database
        from src.core.database_connection import database_connection
        
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tier_name FROM api_billing_tiers WHERE key_id = ?", (key_id,))
            row = cursor.fetchone()
            if row and row[0] in cls.TIERS:
                return cls.TIERS[row[0]]
            return cls.TIERS["free"]

    @classmethod
    def check_billing_status(cls, key_id: str, current_month_requests: int) -> dict:
        tier = cls.get_tier_for_key(key_id)
        is_over_limit = current_month_requests > tier.monthly_request_limit
        overage_count = max(0, current_month_requests - tier.monthly_request_limit)
        
        return {
            "tier": tier.name,
            "monthly_limit": tier.monthly_request_limit,
            "current_usage": current_month_requests,
            "is_over_limit": is_over_limit,
            "overage_allowed": tier.overage_allowed,
            "overage_count": overage_count,
            "status": "blocked" if is_over_limit and not tier.overage_allowed else "active"
        }
