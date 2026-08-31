import sqlite3
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import src.core.database as database
from src.core.database_connection import database_connection

class UsageAggregator:
    @staticmethod
    def _calculate_percentiles(latencies: List[float]) -> dict:
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        
        sorted_l = sorted(latencies)
        n = len(sorted_l)
        return {
            "p50": sorted_l[int(n * 0.50)],
            "p95": sorted_l[int(n * 0.95)],
            "p99": sorted_l[int(n * 0.99)]
        }

    @staticmethod
    def aggregate_for_period(key_id: str, start_time: str, end_time: str) -> dict:
        """Aggregate metrics for a specific time period."""
        db_name = database.DB_NAME
        with database_connection(db_name) as conn:
            cursor = conn.cursor()
            
            # Get total requests and errors
            cursor.execute(
                """
                SELECT COUNT(*), SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END)
                FROM api_usage_records
                WHERE key_id = ? AND timestamp >= ? AND timestamp < ?
                """,
                (key_id, start_time, end_time)
            )
            row = cursor.fetchone()
            total_requests = row[0] or 0
            errors = row[1] or 0
            error_rate = (errors / total_requests) if total_requests > 0 else 0.0

            # Get latencies to calculate percentiles
            cursor.execute(
                """
                SELECT latency FROM api_usage_records
                WHERE key_id = ? AND timestamp >= ? AND timestamp < ?
                ORDER BY latency ASC
                """,
                (key_id, start_time, end_time)
            )
            latencies = [r[0] for r in cursor.fetchall()]
            
            percentiles = UsageAggregator._calculate_percentiles(latencies)
            
            return {
                "total_requests": total_requests,
                "error_rate": error_rate,
                "p50_latency": percentiles["p50"],
                "p95_latency": percentiles["p95"],
                "p99_latency": percentiles["p99"]
            }

    @staticmethod
    def aggregate_hourly(key_id: str) -> dict:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        return UsageAggregator.aggregate_for_period(key_id, start_time.isoformat(), end_time.isoformat())

    @staticmethod
    def aggregate_daily(key_id: str) -> dict:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)
        return UsageAggregator.aggregate_for_period(key_id, start_time.isoformat(), end_time.isoformat())

    @staticmethod
    def aggregate_monthly(key_id: str) -> dict:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=30)
        return UsageAggregator.aggregate_for_period(key_id, start_time.isoformat(), end_time.isoformat())
