import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
    """Create API usage metering tables."""
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            latency REAL NOT NULL,
            payload_size INTEGER NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_api_usage_key_id_timestamp
        ON api_usage_records(key_id, timestamp)
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage_rollups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id TEXT NOT NULL,
            period TEXT NOT NULL,
            period_start TEXT NOT NULL,
            total_requests INTEGER NOT NULL,
            error_rate REAL NOT NULL,
            p50_latency REAL NOT NULL,
            p95_latency REAL NOT NULL,
            p99_latency REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_api_usage_rollups_key_period
        ON api_usage_rollups(key_id, period, period_start)
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_billing_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id TEXT NOT NULL UNIQUE,
            tier_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')

    conn.commit()
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
    """
    Migration v17: Create domain_events table for EventStore audit log.
    """
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            payload TEXT NOT NULL,
            source_module TEXT,
            correlation_id TEXT
        )
    ''')
    
    # Create indexes for efficient querying
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_domain_events_type ON domain_events(event_type)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_domain_events_timestamp ON domain_events(timestamp)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_domain_events_correlation ON domain_events(correlation_id)
    ''')
