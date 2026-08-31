from dataclasses import dataclass, field
from typing import List
import datetime
import logging
from src.data.data_archiver import DataArchiver
from src.data.data_anonymizer import DataAnonymizer
from src.core.database_connection import database_connection

logger = logging.getLogger(__name__)

@dataclass
class RetentionPolicy:
    table_name: str
    active_days: int
    archive_days: int
    purge_days: int
    anonymize_fields: List[str] = field(default_factory=list)
    date_column: str = "created_at"
    has_deleted_at: bool = False

class RetentionEnforcer:
    def __init__(self, db_path: str = "eco_buddy.db"):
        self.db_path = db_path
        self.archiver = DataArchiver(db_path)
        self.anonymizer = DataAnonymizer(db_path)
        
        self.policies = [
            RetentionPolicy("users", 730, 730, 1095, ["email", "username"], "created_at", has_deleted_at=True),
            RetentionPolicy("assessments", 730, 730, 1095, [], "created_at", has_deleted_at=True),
        ]
        
    def run_daily_job(self) -> None:
        logger.info("Starting daily retention job")
        now = datetime.datetime.now()
        
        # 1. Purge expired soft deletes
        soft_delete_manager = SoftDeleteManager(self.db_path)
        soft_delete_manager.purge_expired_soft_deletes()
        
        for policy in self.policies:
            # 2. Archive
            archive_threshold = now - datetime.timedelta(days=policy.active_days)
            self.archiver.archive_old_records(policy, archive_threshold)
            
            # 3. Anonymize in archive
            anonymize_threshold = now - datetime.timedelta(days=policy.archive_days)
            if policy.anonymize_fields:
                self.anonymizer.anonymize_archive_records(policy, anonymize_threshold)
            
            # 4. Purge
            purge_threshold = now - datetime.timedelta(days=policy.purge_days)
            self.archiver.purge_archived_records(policy, purge_threshold)
            
        logger.info("Completed daily retention job")

class SoftDeleteManager:
    def __init__(self, db_path: str = "eco_buddy.db"):
        self.db_path = db_path
        self.cool_down_days = 30
        
    def soft_delete_user(self, user_id: str) -> None:
        with database_connection(self.db_path) as conn:
            now_iso = datetime.datetime.now().isoformat()
            
            # Check if table has deleted_at before updating
            # We assume users has it (via migration)
            conn.execute("UPDATE users SET deleted_at = ? WHERE id = ?", (now_iso, user_id))
            
            # Insert into soft_deleted_users
            conn.execute(
                "INSERT INTO soft_deleted_users (user_id, deleted_at) VALUES (?, ?) ON CONFLICT DO NOTHING",
                (user_id, now_iso)
            )
            
            conn.execute(
                "INSERT INTO data_retention_audit_log (action, table_name, record_id, details) VALUES (?, ?, ?, ?)",
                ("SOFT_DELETE", "users", str(user_id), "User soft deleted")
            )
            conn.commit()

    def purge_expired_soft_deletes(self) -> None:
        with database_connection(self.db_path) as conn:
            threshold = (datetime.datetime.now() - datetime.timedelta(days=self.cool_down_days)).isoformat()
            
            cursor = conn.execute("SELECT user_id FROM soft_deleted_users WHERE deleted_at <= ?", (threshold,))
            expired_users = [row[0] for row in cursor.fetchall()]
            
            for user_id in expired_users:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.execute("DELETE FROM assessments WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM soft_deleted_users WHERE user_id = ?", (user_id,))
                
                conn.execute(
                    "INSERT INTO data_retention_audit_log (action, table_name, record_id, details) VALUES (?, ?, ?, ?)",
                    ("PURGE", "users", str(user_id), "User permanently purged after soft delete cool-down")
                )
            
            conn.commit()
