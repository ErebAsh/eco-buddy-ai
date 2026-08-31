import sqlite3
import datetime
import hashlib
import logging
from src.core.database_connection import database_connection
from typing import Any

logger = logging.getLogger(__name__)

class DataAnonymizer:
    def __init__(self, db_path: str = "eco_buddy.db"):
        self.db_path = db_path
        
    def anonymize_archive_records(self, policy: Any, threshold: datetime.datetime) -> int:
        if not policy.anonymize_fields:
            return 0
            
        archive_table = f"{policy.table_name}_archive"
        
        with database_connection(self.db_path) as conn:
            threshold_iso = threshold.isoformat()
            
            cursor = conn.execute(f"SELECT id, {', '.join(policy.anonymize_fields)} FROM {archive_table} WHERE {policy.date_column} <= ?", (threshold_iso,))
            records = cursor.fetchall()
            
            updates = []
            for row in records:
                record_id = row[0]
                
                # Check if already anonymized (starts with ANON_)
                if any(isinstance(row[i], str) and row[i].startswith("ANON_") for i in range(1, len(row))):
                    continue
                    
                new_vals = []
                for i, field in enumerate(policy.anonymize_fields):
                    val = row[i+1]
                    if val:
                        salt = str(datetime.datetime.now().timestamp())
                        hashed = "ANON_" + hashlib.sha256((str(val) + salt).encode('utf-8')).hexdigest()[:16]
                        new_vals.append(hashed)
                    else:
                        new_vals.append(None)
                
                new_vals.append(record_id)
                updates.append(tuple(new_vals))
                
            if updates:
                set_clause = ", ".join([f"{f} = ?" for f in policy.anonymize_fields])
                conn.executemany(f"UPDATE {archive_table} SET {set_clause} WHERE id = ?", updates)
                
                conn.execute(
                    "INSERT INTO data_retention_audit_log (action, table_name, details) VALUES (?, ?, ?)",
                    ("ANONYMIZE", archive_table, f"Anonymized {len(updates)} records older than {threshold_iso}")
                )
                
            conn.commit()
            return len(updates)
