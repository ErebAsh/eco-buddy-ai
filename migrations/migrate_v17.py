import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
    """Apply migration version 17: Add data retention and archival tables."""
    
    # Add deleted_at to users
    try:
        conn.execute("ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise

    # Add deleted_at to assessments
    try:
        conn.execute("ALTER TABLE assessments ADD COLUMN deleted_at TIMESTAMP")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise

    # Create users_archive table (matching users)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users_archive (
            id INTEGER PRIMARY KEY,
            username TEXT,
            email TEXT,
            password_hash TEXT,
            anonymous_leaderboard INTEGER,
            created_at TIMESTAMP,
            deleted_at TIMESTAMP
        )
        """
    )
    
    # Create assessments_archive table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assessments_archive (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            date TIMESTAMP,
            created_at TIMESTAMP,
            transport TEXT,
            distance REAL,
            electricity REAL,
            diet TEXT,
            flights INTEGER,
            footprint REAL,
            eco_score INTEGER,
            trip_id TEXT,
            factor_version TEXT,
            updated_at TIMESTAMP,
            client_uuid TEXT,
            source_device TEXT,
            deleted_at TIMESTAMP
        )
        """
    )

    # Create soft_deleted_users table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS soft_deleted_users (
            user_id INTEGER PRIMARY KEY,
            deleted_at TIMESTAMP NOT NULL
        )
        """
    )

    # Create data_retention_audit_log table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_retention_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            table_name TEXT NOT NULL,
            record_id TEXT,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
