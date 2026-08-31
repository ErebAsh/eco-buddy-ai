import sqlite3
import datetime
import logging
from src.core.database_connection import database_connection
from typing import Any

logger = logging.getLogger(__name__)

class DataArchiver:
    def __init__(self, db_path: str = "eco_buddy.db"):
        self.db_path = db_path
        
    def archive_old_records(self, policy: Any, threshold: datetime.datetime) -> int:
        table_name = policy.table_name
        archive_table = f"{table_name}_archive"
        date_col = policy.date_column
        
        with database_connection(self.db_path) as conn:
            threshold_iso = threshold.isoformat()
            
            # Ensure we only archive records that are not soft-deleted
            where_clause = f"{date_col} <= ?"
            if policy.has_deleted_at:
                where_clause += " AND deleted_at IS NULL"
            
            cursor = conn.execute(
                f"SELECT * FROM {table_name} WHERE {where_clause}", 
                (threshold_iso,)
            )
            records = cursor.fetchall()
            
            if not records:
                return 0
                
            columns = [description[0] for description in cursor.description]
            placeholders = ", ".join(["?"] * len(columns))
            
            conn.executemany(
                f"INSERT OR IGNORE INTO {archive_table} ({', '.join(columns)}) VALUES ({placeholders})",
                records
            )
            
            conn.execute(
                f"DELETE FROM {table_name} WHERE {where_clause}", 
                (threshold_iso,)
            )
            
            conn.execute(
                "INSERT INTO data_retention_audit_log (action, table_name, details) VALUES (?, ?, ?)",
                ("ARCHIVE", table_name, f"Archived {len(records)} records older than {threshold_iso}")
            )
            
            conn.commit()
            return len(records)
            
    def purge_archived_records(self, policy: Any, threshold: datetime.datetime) -> int:
        archive_table = f"{policy.table_name}_archive"
        
        with database_connection(self.db_path) as conn:
            threshold_iso = threshold.isoformat()
            
            cursor = conn.execute(f"DELETE FROM {archive_table} WHERE {policy.date_column} <= ?", (threshold_iso,))
            deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                conn.execute(
                    "INSERT INTO data_retention_audit_log (action, table_name, details) VALUES (?, ?, ?)",
                    ("PURGE_ARCHIVE", archive_table, f"Purged {deleted_count} records older than {threshold_iso}")
                )
            conn.commit()
            return deleted_count
