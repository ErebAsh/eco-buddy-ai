from typing import List, Optional
import time
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from src.core.background_tasks import submit_background_task
from src.core.database_connection import database_connection
import src.core.database as database

@dataclass
class UsageRecord:
    key_id: str
    endpoint: str
    method: str
    status_code: int
    latency: float
    payload_size: int
    timestamp: str

def flush_usage_records_task(records_dict: List[dict]) -> None:
    """Background task to flush usage records to SQLite."""
    db_name = database.DB_NAME
    with database_connection(db_name) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO api_usage_records
            (key_id, endpoint, method, status_code, latency, payload_size, timestamp)
            VALUES (:key_id, :endpoint, :method, :status_code, :latency, :payload_size, :timestamp)
            """,
            records_dict
        )
        conn.commit()

class UsageMeter:
    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self._buffer: List[UsageRecord] = []
        self._lock = threading.Lock()

    def record_usage(self, record: UsageRecord) -> None:
        """Add a usage record to the in-memory buffer, flush if necessary."""
        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self.batch_size:
                self._flush_locked()

    def flush(self) -> None:
        """Manually trigger a flush of all pending usage records."""
        with self._lock:
            if self._buffer:
                self._flush_locked()

    def _flush_locked(self) -> None:
        """Internal flush without acquiring the lock."""
        records_to_flush = self._buffer[:]
        self._buffer.clear()
        if not records_to_flush:
            return
        
        records_dict = [asdict(r) for r in records_to_flush]
        submit_background_task(
            task_key=f"flush_usage_records_{time.time()}_{len(records_to_flush)}",
            func=flush_usage_records_task,
            records_dict=records_dict,
            task_name=f"Flush {len(records_to_flush)} API usage records",
            task_type="api_metering"
        )

# Global singleton meter to be used across the application
usage_meter = UsageMeter()
