"""
Experiment Tracker for A/B testing analysis.
"""
from typing import Optional, Dict, Any
from src.core.database_connection import database_connection
import src.core.database as database

class ExperimentTracker:
    
    @staticmethod
    def record_assignment(flag_name: str, user_id: str, variant: str) -> None:
        """Record that a user was assigned a specific variant."""
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO experiment_assignments (flag_name, user_id, variant)
                VALUES (?, ?, ?)
                ON CONFLICT(flag_name, user_id) DO UPDATE SET
                    variant=excluded.variant,
                    assigned_at=CURRENT_TIMESTAMP
                """,
                (flag_name, user_id, variant)
            )
            conn.commit()

    @staticmethod
    def record_metric(flag_name: str, user_id: str, metric_name: str, metric_value: float = 1.0) -> None:
        """Record an outcome/metric tied to a flag and user."""
        with database_connection(database.DB_NAME) as conn:
            cursor = conn.cursor()
            # Find variant
            cursor.execute(
                "SELECT variant FROM experiment_assignments WHERE flag_name = ? AND user_id = ?",
                (flag_name, user_id)
            )
            row = cursor.fetchone()
            variant = row["variant"] if row else "unknown"
            
            cursor.execute(
                """
                INSERT INTO experiment_metrics (flag_name, user_id, variant, metric_name, metric_value)
                VALUES (?, ?, ?, ?, ?)
                """,
                (flag_name, user_id, variant, metric_name, metric_value)
            )
            conn.commit()
