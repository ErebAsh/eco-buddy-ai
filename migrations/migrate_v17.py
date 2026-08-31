import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
    """Apply migration version 17: Add api_rate_limits table for sliding window rate limiter."""
    
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_rate_limits (
            key_id INTEGER NOT NULL,
            window_start INTEGER NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (key_id, window_start),
            FOREIGN KEY (key_id) REFERENCES api_keys (id) ON DELETE CASCADE
        );
        """
    )
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_rate_limits_key_window ON api_rate_limits (key_id, window_start);")
    
    conn.commit()
