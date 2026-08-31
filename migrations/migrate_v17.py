import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
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
