import datetime
from typing import Dict, List, Any

class GDPRComplianceChecker:
    """
    Evaluates current data retention and consent logs to ensure platform compliance
    with GDPR and CPRA regulations.
    """

    # Maximum retention period in days before anonymization is mandated
    MAX_RETENTION_DAYS = 730 # 2 years
    
    def enforce_retention(self, db_path: str = "eco_buddy.db") -> None:
        """Triggers the automated retention engine to resolve compliance violations."""
        from src.data.retention_engine import RetentionEnforcer
        enforcer = RetentionEnforcer(db_path)
        enforcer.run_daily_job()

    def __init__(self, users_data: List[Dict[str, Any]]):
        self.users = users_data

    def check_retention_violations(self) -> List[Dict[str, Any]]:
        """Identifies records that have exceeded the statutory retention period."""
        violations = []
        now = datetime.datetime.now()
        
        for user in self.users:
            if not user.get("last_active"):
                continue
                
            last_active = datetime.datetime.fromisoformat(user["last_active"])
            days_inactive = (now - last_active).days
            
            if days_inactive > self.MAX_RETENTION_DAYS:
                violations.append({
                    "user_id": user.get("user_id"),
                    "days_inactive": days_inactive,
                    "action_required": "Anonymize or Delete"
                })
        return violations

    def get_compliance_score(self) -> float:
        """
        Calculates a rough compliance health score (0-100) based on
        active consent logs and retention violations.
        """
        if not self.users:
            return 100.0
            
        violations = self.check_retention_violations()
        
        users_missing_consent = [
            u for u in self.users 
            if not u.get("consent_logs", {}).get("terms_accepted")
        ]
        
        penalty = (len(violations) * 5) + (len(users_missing_consent) * 10)
        score = 100.0 - penalty
        return max(0.0, float(score))

    def generate_audit_log(self) -> List[str]:
        """Provides a textual audit log for compliance officers."""
        logs = []
        logs.append(f"GDPR Audit Generated: {datetime.datetime.now().isoformat()}")
        
        v = self.check_retention_violations()
        logs.append(f"Retention Violations Detected: {len(v)}")
        for violation in v:
            logs.append(f" - {violation['user_id']} ({violation['days_inactive']} days inactive)")
            
        logs.append(f"Overall Compliance Score: {self.get_compliance_score():.1f}/100")
        return logs
