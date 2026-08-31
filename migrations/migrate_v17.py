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
