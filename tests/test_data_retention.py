import pytest
import sqlite3
import datetime
from src.data.retention_engine import RetentionEnforcer, RetentionPolicy, SoftDeleteManager
from src.data.data_archiver import DataArchiver
from src.data.data_anonymizer import DataAnonymizer
from src.core.database_connection import database_connection
import tempfile
import os

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    with database_connection(path) as conn:
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                email TEXT,
                created_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE assessments (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                created_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE users_archive (
                id INTEGER PRIMARY KEY,
                username TEXT,
                email TEXT,
                created_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE assessments_archive (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                created_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE soft_deleted_users (
                user_id INTEGER PRIMARY KEY,
                deleted_at TIMESTAMP NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE data_retention_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                table_name TEXT NOT NULL,
                record_id TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        
    yield path
    os.remove(path)

def test_archive_and_anonymize(db_path):
    now = datetime.datetime.now()
    old_date = (now - datetime.timedelta(days=800)).isoformat()
    recent_date = (now - datetime.timedelta(days=100)).isoformat()
    
    with database_connection(db_path) as conn:
        conn.execute("INSERT INTO users (id, username, email, created_at) VALUES (?, ?, ?, ?)", (1, "old_user", "old@test.com", old_date))
        conn.execute("INSERT INTO users (id, username, email, created_at) VALUES (?, ?, ?, ?)", (2, "new_user", "new@test.com", recent_date))
        conn.commit()
        
    enforcer = RetentionEnforcer(db_path)
    enforcer.run_daily_job()
    
    with database_connection(db_path) as conn:
        # old_user should be moved to archive and anonymized
        cursor = conn.execute("SELECT * FROM users_archive WHERE id = 1")
        archived_user = cursor.fetchone()
        assert archived_user is not None
        assert archived_user["username"].startswith("ANON_")
        assert archived_user["email"].startswith("ANON_")
        
        # old_user should be deleted from users
        cursor = conn.execute("SELECT * FROM users WHERE id = 1")
        assert cursor.fetchone() is None
        
        # new_user should still be in users
        cursor = conn.execute("SELECT * FROM users WHERE id = 2")
        assert cursor.fetchone() is not None

def test_soft_delete_and_purge(db_path):
    now = datetime.datetime.now()
    
    with database_connection(db_path) as conn:
        conn.execute("INSERT INTO users (id, username, email, created_at) VALUES (?, ?, ?, ?)", (1, "del_user", "del@test.com", now.isoformat()))
        conn.commit()
        
    manager = SoftDeleteManager(db_path)
    manager.soft_delete_user(1)
    
    with database_connection(db_path) as conn:
        cursor = conn.execute("SELECT deleted_at FROM users WHERE id = 1")
        assert cursor.fetchone()["deleted_at"] is not None
        
        cursor = conn.execute("SELECT * FROM soft_deleted_users WHERE user_id = 1")
        assert cursor.fetchone() is not None
        
    # Fake time passed
    old_delete_date = (now - datetime.timedelta(days=40)).isoformat()
    with database_connection(db_path) as conn:
        conn.execute("UPDATE soft_deleted_users SET deleted_at = ? WHERE user_id = 1", (old_delete_date,))
        conn.commit()
        
    manager.purge_expired_soft_deletes()
    
    with database_connection(db_path) as conn:
        cursor = conn.execute("SELECT * FROM users WHERE id = 1")
        assert cursor.fetchone() is None
        
        cursor = conn.execute("SELECT * FROM soft_deleted_users WHERE user_id = 1")
        assert cursor.fetchone() is None
