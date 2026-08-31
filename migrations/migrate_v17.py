"""
Migration to add feature flags and experiment tracking tables.
"""
import sqlite3

def migrate(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    # Create feature flags table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feature_flags (
            name TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT 0,
            rollout_percentage REAL NOT NULL DEFAULT 100.0,
            target_rules TEXT NOT NULL DEFAULT '{}',
            variants TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create flag overrides table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS flag_overrides (
            flag_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            enabled BOOLEAN NOT NULL,
            variant TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (flag_name, user_id)
        )
    ''')

    # Create experiment assignments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experiment_assignments (
            flag_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            variant TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (flag_name, user_id)
        )
    ''')

    # Create experiment metrics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experiment_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flag_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            variant TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL DEFAULT 1.0,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes for fast querying
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_experiment_metrics_flag 
        ON experiment_metrics (flag_name, variant)
    ''')
